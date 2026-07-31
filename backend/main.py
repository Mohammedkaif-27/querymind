"""
Phase 5 — FastAPI Backend
REST API that wraps the TextToSQLAgent.
Run: uvicorn backend.main:app --reload --port 8000
"""

import os
import io
import uuid
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime

import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.agent import TextToSQLAgent
from backend.db_connector import DatabaseConnector
from backend.config import config
from backend.auth import get_current_user, get_optional_user, AuthenticatedUser
from backend.supabase_client import get_supabase_client
from backend.logger import setup_logging, set_request_id, get_request_id
from backend.schema_retriever import (
    build_schema_index,
    delete_collection,
    health_check_chroma,
    NORTHWIND_COLLECTION,
)

setup_logging()
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# App lifecycle — init agent once at startup
# ──────────────────────────────────────────────

agent: TextToSQLAgent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    logger.info("Starting up — initializing TextToSQLAgent...")
    agent = TextToSQLAgent()
    logger.info("Agent ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="QueryMind",
    description="Natural language to SQL using Groq Llama 3.3 70B",
    version="2.0.0",
    lifespan=lifespan,
)

# Allow configurable CORS origins for frontend (dev + production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Request logging & request_id middleware
# ──────────────────────────────────────────────

@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):
    # Pass OPTIONS preflight requests directly to CORS middleware
    if request.method == "OPTIONS":
        return await call_next(request)

    # Extract existing X-Request-ID or generate new UUID
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_request_id(req_id)
    request.state.request_id = req_id

    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    response.headers["X-Request-ID"] = req_id
    logger.info(
        f"{request.method} {request.url.path} → {response.status_code} ({duration_ms:.1f}ms)",
        extra={"method": request.method, "path": request.url.path, "status_code": response.status_code, "duration_ms": duration_ms}
    )
    return response


# ──────────────────────────────────────────────
# Global exception handler with error sanitization
# ──────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", get_request_id() or "unknown")
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={"request_id": req_id}
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": req_id,
        },
        headers={"X-Request-ID": req_id},
    )


# ──────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=5,
        max_length=500,
        examples=["Which country had the most orders in 1997?"],
    )
    source_id: Optional[str] = Field(
        None,
        description="UUID of the data source to query. Defaults to Northwind if not provided.",
    )


class QueryResponse(BaseModel):
    question: str
    sql: str
    result: list[dict]
    columns: list[str]
    narration: str
    chart_type: str
    error: str
    retries: int
    latency_ms: float
    row_count: int


# -- Dashboards --

class DashboardCreate(BaseModel):
    name: str = Field(..., max_length=100)

class WidgetCreate(BaseModel):
    source_id: Optional[str] = None
    question: str
    sql: str
    chart_type: str = "table"

class DashboardResponse(BaseModel):
    id: str
    user_id: str
    name: str
    created_at: datetime

class WidgetResponse(BaseModel):
    id: str
    dashboard_id: str
    source_id: Optional[str]
    question: str
    sql: str
    chart_type: str
    created_at: datetime


class DataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(csv|xlsx|postgres|mysql)$")
    connection_info: dict = Field(default_factory=dict)


class DataSourceResponse(BaseModel):
    id: str
    name: str
    type: str
    chroma_collection_name: str
    table_count: int
    created_at: str


class QueryHistoryItem(BaseModel):
    id: str
    source_id: Optional[str]
    question: str
    generated_sql: str
    success: bool
    latency_ms: float
    row_count: int
    error: str
    created_at: str


# ──────────────────────────────────────────────
# System endpoints (no auth required)
# ──────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """Check API, database, ChromaDB, and Supabase connectivity."""
    components = {}
    is_healthy = True

    # 1. API & Model config check
    components["api"] = {"status": "ok", "version": "2.0.0"}
    components["llm"] = {
        "status": "configured" if config.groq_api_key else "missing_key",
        "model": config.groq_model,
    }
    if not config.groq_api_key:
        is_healthy = False

    # 2. Local DB check (if configured)
    if config.db_path:
        try:
            db = DatabaseConnector(config.db_path)
            components["database"] = db.health_check()
        except Exception as e:
            components["database"] = {"status": "error", "error": str(e)}
    else:
        components["database"] = {"status": "no_local_db"}

    # 3. Supabase check
    try:
        sb = get_supabase_client()
        sb.table("data_sources").select("id").limit(1).execute()
        components["supabase"] = {"status": "ok"}
    except Exception as e:
        logger.error(f"Supabase health check failed: {e}")
        components["supabase"] = {"status": "error", "error": str(e)}
        is_healthy = False

    # 4. ChromaDB check
    chroma_health = health_check_chroma()
    components["chroma"] = chroma_health
    if chroma_health.get("status") != "ok":
        is_healthy = False

    overall_status = "healthy" if is_healthy else "degraded"
    status_code = 200 if is_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "components": components,
        },
    )


@app.get("/tables", tags=["System"])
def list_tables():
    """Return all table names and their row counts (Northwind)."""
    if not config.db_path:
        return {"tables": {}, "note": "No local database configured."}
    db = DatabaseConnector(config.db_path)
    tables = db.get_all_table_names()
    result = {}
    for table in tables:
        try:
            result[table] = db.get_table_row_count(table)
        except Exception:
            result[table] = -1
    return {"tables": result}


def _get_db_connector(source_id: str) -> Optional[DatabaseConnector]:
    sb = get_supabase_client()
    result = (
        sb.table("data_sources")
        .select("type, connection_info")
        .eq("id", source_id)
        .execute()
    )
    if not result.data:
        return None
        
    src = result.data[0]
    conn_info = src["connection_info"] or {}
    
    if src["type"] in ("csv", "xlsx"):
        try:
            return DatabaseConnector.from_uri(config.supabase_db_url, schema="user_data")
        except Exception:
            local_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "user_data.db")
            return DatabaseConnector(local_db_path)
    elif src["type"] in ("postgres", "mysql"):
        uri = conn_info.get("uri", "")
        if uri:
            return DatabaseConnector.from_uri(uri)
    return None

@app.get("/sample-questions", tags=["Agent"])
def sample_questions(source_id: Optional[str] = None):
    """Return sample questions. If source_id is provided, generate dynamically."""
    if source_id:
        try:
            db_conn = _get_db_connector(source_id)
            if db_conn:
                agent = TextToSQLAgent()
                questions = agent.generate_sample_questions(db_conn)
                if questions:
                    return {"questions": questions}
        except Exception as e:
            logger.error(f"Failed to generate dynamic questions for {source_id}: {e}")
            
    # Fallback to defaults
    return {
        "questions": [
            "Which country had the most orders in 1997?",
            "Show me the top 10 products by total revenue",
            "What is the average order value per customer?",
            "Which employee processed the most orders?",
            "List all suppliers from the USA",
            "What are the monthly sales totals for 1997?",
            "Which product category generates the highest revenue?",
            "How many orders were shipped late (ShippedDate > RequiredDate)?",
        ]
    }


# ──────────────────────────────────────────────
# Query endpoint (auth optional for now, required after Node H)
# ──────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse, tags=["Agent"])
def query(
    body: QueryRequest,
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """Convert a natural language question to SQL and return results.

    The agent will:
    1. Find relevant tables via semantic search
    2. Generate SQL using Groq Llama 3.3 70B
    3. Validate + execute the SQL
    4. Narrate the result in plain English

    Returns structured response including SQL, data, and chart type hint.
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized yet.")

    logger.info(f"Query received: {body.question} (user={user.id if user else 'anonymous'})")

    # Resolve source_id to a db_connector and collection_name
    db_connector = None
    collection_name = NORTHWIND_COLLECTION

    if body.source_id:
        sb = get_supabase_client()
        source_row = (
            sb.table("data_sources")
            .select("id, type, connection_info, chroma_collection_name")
            .eq("id", body.source_id)
            .execute()
        )
        if not source_row.data:
            raise HTTPException(status_code=404, detail="Data source not found.")

        src = source_row.data[0]
        collection_name = src["chroma_collection_name"]
        conn_info = src.get("connection_info", {})

        if src["type"] in ("csv", "xlsx"):
            # Uploaded data lives in Supabase Postgres or local fallback SQLite
            try:
                db_connector = DatabaseConnector.from_uri(
                    config.supabase_db_url, schema="user_data"
                )
            except Exception:
                local_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "user_data.db")
                db_connector = DatabaseConnector(local_db_path)
        elif src["type"] in ("postgres", "mysql"):
            uri = conn_info.get("uri", "")
            if not uri:
                raise HTTPException(status_code=400, detail="No connection URI for this source.")
            db_connector = DatabaseConnector.from_uri(uri)

    response = agent.answer(
        body.question,
        db_connector=db_connector,
        collection_name=collection_name,
    )

    if response.error:
        logger.warning(f"Agent returned error: {response.error}")

    # Persist to query_history if user is authenticated
    if user:
        try:
            sb = get_supabase_client()
            sb.table("query_history").insert({
                "user_id": user.id,
                "source_id": body.source_id,
                "question": body.question,
                "generated_sql": response.sql,
                "success": not bool(response.error),
                "latency_ms": response.latency_ms,
                "row_count": len(response.result_df),
                "error": response.error or "",
            }).execute()
        except Exception as e:
            logger.error(f"Failed to persist query history: {e}")

    return QueryResponse(**response.to_dict())


# ──────────────────────────────────────────────
# Data Sources endpoints (auth required)
# ──────────────────────────────────────────────

@app.get("/api/sources", tags=["Sources"], response_model=list[DataSourceResponse])
def list_sources(user: AuthenticatedUser = Depends(get_current_user)):
    """List all data sources owned by the current user."""
    sb = get_supabase_client()
    result = (
        sb.table("data_sources")
        .select("id, name, type, chroma_collection_name, table_count, created_at")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return [DataSourceResponse(**row) for row in result.data]


@app.post("/api/sources", tags=["Sources"], response_model=DataSourceResponse, status_code=201)
def create_source(
    body: DataSourceCreate,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Register a new data source for the current user.

    This creates the metadata record. For CSV/XLSX uploads, use /api/upload instead
    which handles file upload + source creation together.
    """
    import uuid

    source_id = str(uuid.uuid4())
    collection_name = f"src_{source_id.replace('-', '_')}"

    sb = get_supabase_client()
    result = (
        sb.table("data_sources")
        .insert({
            "id": source_id,
            "user_id": user.id,
            "name": body.name,
            "type": body.type,
            "connection_info": body.connection_info,
            "chroma_collection_name": collection_name,
            "table_count": 0,
        })
        .execute()
    )

    row = result.data[0]
    return DataSourceResponse(**row)


@app.delete("/api/sources/{source_id}", tags=["Sources"], status_code=204)
def delete_source(
    source_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a data source and its associated data."""
    sb = get_supabase_client()

    # Verify ownership and get details for cleanup
    existing = (
        sb.table("data_sources")
        .select("id, type, chroma_collection_name")
        .eq("id", source_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Data source not found.")

    src = existing.data[0]

    # Clean up Chroma collection
    try:
        delete_collection(src["chroma_collection_name"])
    except Exception as e:
        logger.warning(f"Failed to delete Chroma collection: {e}")

    # Clean up uploaded table in Supabase Postgres if it was a CSV/XLSX
    if src["type"] in ("csv", "xlsx"):
        try:
            table_name = f"src_{source_id.replace('-', '_')}"
            db = DatabaseConnector.from_uri(config.supabase_db_url, schema="user_data")
            db.drop_table(table_name, schema="user_data")
        except Exception as e:
            logger.warning(f"Failed to drop uploaded table: {e}")

    sb.table("data_sources").delete().eq("id", source_id).execute()
    logger.info(f"Deleted data source {source_id} for user {user.id}")


# ──────────────────────────────────────────────
# Query History endpoint (auth required)
# ──────────────────────────────────────────────

@app.get("/api/history", tags=["History"], response_model=list[QueryHistoryItem])
def get_history(
    limit: int = 50,
    source_id: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieve query history for the current user.

    Optionally filter by source_id. Returns most recent queries first.
    """
    sb = get_supabase_client()
    query = (
        sb.table("query_history")
        .select("id, source_id, question, generated_sql, success, latency_ms, row_count, error, created_at")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .limit(min(limit, 200))
    )

    if source_id:
        query = query.eq("source_id", source_id)

    result = query.execute()
    return [QueryHistoryItem(**row) for row in result.data]


# ──────────────────────────────────────────────
# Upload & Connect endpoints (auth required)
# ──────────────────────────────────────────────

@app.post("/api/upload", tags=["Ingestion"], response_model=DataSourceResponse, status_code=201)
def upload_file(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Upload a CSV or XLSX file as a new data source.

    The file is:
    1. Parsed in-memory with pandas
    2. Written to Supabase Postgres (user_data schema)
    3. Backed up to Supabase Storage (raw-uploads bucket)
    4. Schema-embedded in a ChromaDB collection
    5. Registered in data_sources
    """
    # Validate file type
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "xlsx", "xls"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Upload a CSV or XLSX file.",
        )

    source_type = "xlsx" if ext in ("xlsx", "xls") else "csv"
    source_name = name or filename.rsplit(".", 1)[0]

    # Read file into memory
    try:
        raw_bytes = file.file.read()
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(raw_bytes))
        else:
            df = pd.read_excel(io.BytesIO(raw_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="File is empty or has no valid data.")

    # Generate IDs
    source_id = str(uuid.uuid4())
    table_name = f"src_{source_id.replace('-', '_')}"
    collection_name = f"src_{source_id.replace('-', '_')}"

    # 1. Write data to Supabase Postgres (with local SQLite fallback if network/IPv6 times out)
    used_local_fallback = False
    try:
        db = DatabaseConnector.from_uri(config.supabase_db_url, schema="user_data")
        db.create_table_from_dataframe(df, table_name, schema="user_data")
    except Exception as e:
        logger.warning(f"Remote Supabase Postgres unavailable ({e}), using local SQLite storage fallback.")
        local_db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(local_db_dir, exist_ok=True)
        local_db_path = os.path.join(local_db_dir, "user_data.db")
        db = DatabaseConnector(local_db_path)
        db.create_table_from_dataframe(df, table_name)
        used_local_fallback = True

    # 2. Upload raw file to Supabase Storage
    try:
        sb = get_supabase_client()
        storage_path = f"{user.id}/{source_id}/{filename}"
        sb.storage.from_("raw-uploads").upload(
            path=storage_path,
            file=raw_bytes,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
        logger.info(f"Uploaded raw file to storage: {storage_path}")
    except Exception as e:
        logger.warning(f"Failed to upload raw file to storage (non-fatal): {e}")

    # 3. Build Chroma index for this source
    try:
        schema_hash = build_schema_index(
            db,
            collection_name=collection_name,
            embedding_model=config.embedding_model,
        )
    except Exception as e:
        logger.error(f"Failed to build Chroma index: {e}")
        try:
            db.drop_table(table_name)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to index schema. Please try again.")

    # 4. Register in data_sources
    try:
        sb = get_supabase_client()
        result = (
            sb.table("data_sources")
            .insert({
                "id": source_id,
                "user_id": user.id,
                "name": source_name,
                "type": source_type,
                "connection_info": {"table_name": table_name, "schema": "user_data"},
                "chroma_collection_name": collection_name,
                "schema_hash": schema_hash,
                "table_count": 1,
            })
            .execute()
        )
        row = result.data[0]
        logger.info(f"Created data source '{source_name}' (id={source_id}) for user {user.id}")
        return DataSourceResponse(**row)
    except Exception as e:
        logger.error(f"Failed to register data source: {e}")
        raise HTTPException(status_code=500, detail="Failed to register source. Please try again.")


class ConnectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    uri: str = Field(..., min_length=10, description="SQLAlchemy connection URI")
    type: str = Field(..., pattern="^(postgres|mysql)$")


@app.post("/api/connect", tags=["Ingestion"], response_model=DataSourceResponse, status_code=201)
def connect_external_db(
    body: ConnectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Connect an external database (Postgres or MySQL) as a data source.

    Tests the connection, introspects schema, builds Chroma index.
    """
    # Test connection
    try:
        db = DatabaseConnector.from_uri(body.uri)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not connect to database: {e}",
        )

    source_id = str(uuid.uuid4())
    collection_name = f"src_{source_id.replace('-', '_')}"

    # Build Chroma index
    try:
        schema_hash = build_schema_index(
            db,
            collection_name=collection_name,
            embedding_model=config.embedding_model,
        )
    except Exception as e:
        logger.error(f"Failed to build Chroma index for external DB: {e}")
        raise HTTPException(status_code=500, detail="Failed to index schema.")

    table_count = len(db.get_all_table_names())

    # Register in data_sources
    sb = get_supabase_client()
    result = (
        sb.table("data_sources")
        .insert({
            "id": source_id,
            "user_id": user.id,
            "name": body.name,
            "type": body.type,
            "connection_info": {"uri": body.uri},
            "chroma_collection_name": collection_name,
            "schema_hash": schema_hash,
            "table_count": table_count,
        })
        .execute()
    )

    row = result.data[0]
    logger.info(f"Connected external DB '{body.name}' (id={source_id}) for user {user.id}")
    return DataSourceResponse(**row)


# ──────────────────────────────────────────────
# Dashboard Endpoints
# ──────────────────────────────────────────────

@app.get("/api/dashboards", tags=["Dashboards"], response_model=list[DashboardResponse])
def list_dashboards(user: AuthenticatedUser = Depends(get_current_user)):
    """List all dashboards for the current user."""
    sb = get_supabase_client()
    result = sb.table("dashboards").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
    return result.data

@app.post("/api/dashboards", tags=["Dashboards"], response_model=DashboardResponse, status_code=201)
def create_dashboard(body: DashboardCreate, user: AuthenticatedUser = Depends(get_current_user)):
    """Create a new dashboard."""
    sb = get_supabase_client()
    result = sb.table("dashboards").insert({"user_id": user.id, "name": body.name}).execute()
    return result.data[0]

@app.get("/api/dashboards/{dashboard_id}/widgets", tags=["Dashboards"], response_model=list[WidgetResponse])
def get_dashboard_widgets(dashboard_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Get all widgets for a specific dashboard."""
    # RLS will ensure the user can only fetch widgets for their own dashboards
    sb = get_supabase_client()
    result = sb.table("dashboard_widgets").select("*").eq("dashboard_id", dashboard_id).order("created_at", desc=False).execute()
    return result.data

@app.post("/api/dashboards/{dashboard_id}/widgets", tags=["Dashboards"], response_model=WidgetResponse, status_code=201)
def add_dashboard_widget(dashboard_id: str, body: WidgetCreate, user: AuthenticatedUser = Depends(get_current_user)):
    """Add a new widget (saved chart/query) to a dashboard."""
    sb = get_supabase_client()
    
    # Verify the dashboard belongs to the user
    dash = sb.table("dashboards").select("id").eq("id", dashboard_id).eq("user_id", user.id).execute()
    if not dash.data:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    result = sb.table("dashboard_widgets").insert({
        "dashboard_id": dashboard_id,
        "source_id": body.source_id,
        "question": body.question,
        "sql": body.sql,
        "chart_type": body.chart_type
    }).execute()
    
    return result.data[0]

@app.delete("/api/dashboards/{dashboard_id}", tags=["Dashboards"], status_code=204)
def delete_dashboard(dashboard_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Delete a dashboard and all its widgets."""
    sb = get_supabase_client()
    result = sb.table("dashboards").delete().eq("id", dashboard_id).eq("user_id", user.id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Dashboard not found or not owned by user")
    return

@app.delete("/api/dashboards/{dashboard_id}/widgets/{widget_id}", tags=["Dashboards"], status_code=204)
def remove_dashboard_widget(dashboard_id: str, widget_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Remove a widget from a dashboard."""
    sb = get_supabase_client()
    # Verify dashboard ownership first
    dash = sb.table("dashboards").select("id").eq("id", dashboard_id).eq("user_id", user.id).execute()
    if not dash.data:
        raise HTTPException(status_code=404, detail="Dashboard not found")
        
    result = sb.table("dashboard_widgets").delete().eq("id", widget_id).eq("dashboard_id", dashboard_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Widget not found")
    return
