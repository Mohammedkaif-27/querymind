"""
Phase 2 — Schema Retriever (ChromaDB)
Embeds database table schemas using sentence-transformers and indexes them
in ChromaDB for fast semantic similarity search, namespaced per data source.

When a user asks "total sales by country", this module finds that the
Orders and OrderDetails tables are most relevant — without hard-coding
any keyword rules.

Migration note: Replaces FAISS with ChromaDB for vector storage.
Each data source gets its own Chroma collection, preventing cross-source
contamination.
"""

import os
import json
import hashlib
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Lazy imports to avoid slow startup when not needed
_SentenceTransformer = None
_chroma_client = None

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

# Default collection name for the built-in Northwind database
NORTHWIND_COLLECTION = "src_northwind"


def _get_transformer(model_name: str = "all-MiniLM-L6-v2"):
    """Lazy-load the SentenceTransformer model.

    Args:
        model_name: HuggingFace model name.

    Returns:
        Loaded SentenceTransformer instance.
    """
    global _SentenceTransformer
    if _SentenceTransformer is None:
        from sentence_transformers import SentenceTransformer
        _SentenceTransformer = SentenceTransformer
    # Cache models by name to avoid reloading
    if not hasattr(_get_transformer, "_models"):
        _get_transformer._models = {}
    if model_name not in _get_transformer._models:
        logger.info(f"Loading embedding model: {model_name}")
        _get_transformer._models[model_name] = _SentenceTransformer(model_name)
    return _get_transformer._models[model_name]


def _get_chroma_client():
    """Get or create the ChromaDB client.

    Uses persistent storage in the embeddings/ directory for local dev.
    For production, configure CHROMA_URL env var to point to a Chroma server.

    Returns:
        ChromaDB client instance.
    """
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    import chromadb

    chroma_url = os.getenv("CHROMA_URL", "")

    if chroma_url:
        # Production: connect to a Chroma server
        logger.info(f"Connecting to Chroma server at {chroma_url}")
        _chroma_client = chromadb.HttpClient(host=chroma_url)
    else:
        # Local dev: persistent storage in embeddings/ directory
        persist_dir = os.path.join(_PROJECT_ROOT, "embeddings", "chroma_db")
        os.makedirs(persist_dir, exist_ok=True)
        logger.info(f"Using persistent Chroma at {persist_dir}")
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def health_check_chroma() -> dict:
    """Check ChromaDB health status.

    Returns:
        Dict with status ('ok' or 'error') and collection count.
    """
    try:
        client = _get_chroma_client()
        collections = client.list_collections()
        return {"status": "ok", "collections": len(collections)}
    except Exception as e:
        logger.error(f"Chroma health check failed: {e}")
        return {"status": "error", "error": str(e)}


def compute_schema_hash(schemas: dict[str, str]) -> str:
    """Compute a hash of all table schemas for change detection.

    Args:
        schemas: Dict mapping table_name -> schema_string.

    Returns:
        SHA-256 hex digest of the combined schema.
    """
    combined = json.dumps(schemas, sort_keys=True)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def get_sample_rows(db_connector, table_name: str, n: int = 3) -> str:
    """Get sample rows from a table as a formatted string.

    Args:
        db_connector: DatabaseConnector instance.
        table_name: Exact name of the table.
        n: Number of sample rows to retrieve.

    Returns:
        Formatted string of sample rows, or empty string on error.
    """
    try:
        df = db_connector.run_query(
            f'SELECT * FROM "{table_name}" LIMIT {n}'
        )
        if df.empty:
            return ""
        return df.to_string(index=False)
    except Exception as e:
        logger.warning(f"Could not get sample rows for {table_name}: {e}")
        return ""


def build_schema_index(
    db_connector,
    collection_name: str = NORTHWIND_COLLECTION,
    embedding_model: str = "all-MiniLM-L6-v2",
    include_samples: bool = True,
) -> str:
    """Embed all table schemas and store in a ChromaDB collection.

    Each table schema becomes one document in the collection. The metadata
    stores the table name and raw schema string for retrieval.

    Args:
        db_connector: DatabaseConnector instance.
        collection_name: Name of the Chroma collection (unique per source).
        embedding_model: HuggingFace sentence-transformers model name.
        include_samples: Whether to include sample rows in metadata.

    Returns:
        Schema hash string for the indexed schema.
    """
    client = _get_chroma_client()
    model = _get_transformer(embedding_model)

    schemas = db_connector.get_all_schemas()
    table_names = list(schemas.keys())
    schema_strings = list(schemas.values())
    schema_hash = compute_schema_hash(schemas)

    # Enrich each schema string with table name context before embedding.
    # Pure schema strings like "Orders(OrderID INTEGER, ...)" carry less
    # semantic signal than "Orders table: OrderID INTEGER, CustomerID TEXT...".
    enriched = []
    metadata_list = []
    for name, schema in zip(table_names, schema_strings):
        enriched_text = f"{name} table: {schema}"

        meta = {"table": name, "schema": schema}
        if include_samples:
            samples = get_sample_rows(db_connector, name)
            if samples:
                enriched_text += f"\nSample data:\n{samples}"
                meta["sample_rows"] = samples

        enriched.append(enriched_text)
        metadata_list.append(meta)

    logger.info(f"Embedding {len(enriched)} table schemas for collection '{collection_name}'...")
    embeddings = model.encode(enriched, normalize_embeddings=True, show_progress_bar=True)
    embeddings_list = [emb.tolist() for emb in embeddings]

    # Delete existing collection if it exists, then recreate
    try:
        client.delete_collection(name=collection_name)
        logger.info(f"Deleted existing collection '{collection_name}' for rebuild.")
    except Exception:
        pass  # Collection doesn't exist yet — that's fine

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    # Add all embeddings at once
    collection.add(
        ids=[f"{collection_name}_{name}" for name in table_names],
        embeddings=embeddings_list,
        documents=enriched,
        metadatas=metadata_list,
    )

    logger.info(
        f"✅ Chroma collection '{collection_name}' built with "
        f"{len(table_names)} tables (hash={schema_hash})"
    )

    return schema_hash


def retrieve_relevant_schemas(
    query: str,
    collection_name: str = NORTHWIND_COLLECTION,
    embedding_model: str = "all-MiniLM-L6-v2",
    top_k: int = 3,
) -> str:
    """Find the top-K most relevant table schemas for a given user query.

    Uses semantic similarity — "employee hire dates" retrieves the Employees
    table even though "hire" isn't in the column names.

    Args:
        query: User's natural language question.
        collection_name: Name of the Chroma collection to search.
        embedding_model: Must match the model used during build_schema_index.
        top_k: Number of most relevant tables to return.

    Returns:
        Multi-line string of relevant schemas, one per line:
        "Orders(OrderID INTEGER, CustomerID TEXT, ...)\\nCustomers(...)\\n..."

    Raises:
        ValueError: If the collection doesn't exist.
    """
    client = _get_chroma_client()
    model = _get_transformer(embedding_model)

    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        raise ValueError(
            f"Chroma collection '{collection_name}' not found. "
            "Build the schema index first."
        )

    # Ensure we don't request more results than documents in the collection
    actual_k = min(top_k, collection.count())
    if actual_k == 0:
        return ""

    query_embedding = model.encode([query], normalize_embeddings=True)
    results = collection.query(
        query_embeddings=[query_embedding[0].tolist()],
        n_results=actual_k,
        include=["metadatas", "distances"],
    )

    retrieved = []
    for rank, (meta, distance) in enumerate(
        zip(results["metadatas"][0], results["distances"][0])
    ):
        retrieved.append(meta["schema"])
        logger.debug(
            f"  Rank {rank+1}: {meta['table']} (distance={distance:.4f})"
        )

    logger.info(
        f"Schema retrieval for '{query[:60]}' → "
        f"{[m['table'] for m in results['metadatas'][0]]}"
    )

    return "\n".join(retrieved)


def ensure_index_exists(
    db_connector,
    collection_name: str = NORTHWIND_COLLECTION,
    embedding_model: str = "all-MiniLM-L6-v2",
):
    """Build the schema index if it doesn't already exist.

    Call this at application startup so the first query isn't slow.

    Args:
        db_connector: DatabaseConnector instance.
        collection_name: Name of the Chroma collection.
        embedding_model: Model name for embeddings.
    """
    client = _get_chroma_client()
    try:
        col = client.get_collection(name=collection_name)
        if col.count() > 0:
            logger.info(
                f"Chroma collection '{collection_name}' exists with "
                f"{col.count()} documents — skipping rebuild."
            )
            return
    except Exception:
        pass

    logger.info(f"Chroma collection '{collection_name}' not found — building now...")
    build_schema_index(db_connector, collection_name, embedding_model)


def delete_collection(collection_name: str):
    """Delete a Chroma collection (e.g., when a data source is removed).

    Args:
        collection_name: Name of the collection to delete.
    """
    client = _get_chroma_client()
    try:
        client.delete_collection(name=collection_name)
        logger.info(f"Deleted Chroma collection '{collection_name}'.")
    except Exception as e:
        logger.warning(f"Could not delete collection '{collection_name}': {e}")
