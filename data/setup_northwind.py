"""
Phase 1 — Database Setup
Downloads the Northwind SQLite database and verifies all tables exist.
Run: python data/setup_northwind.py
"""

import os
import sys
import sqlite3
import urllib.request

DB_URL = "https://raw.githubusercontent.com/jpwhite3/northwind-SQLite3/main/dist/northwind.db"
DB_PATH = os.path.join(os.path.dirname(__file__), "northwind.db")

EXPECTED_TABLES = [
    "Categories", "Customers", "Employees",
    "Order Details", "Orders", "Products",
    "Shippers", "Suppliers",
]


def download_northwind():
    """Download the Northwind SQLite database from GitHub."""
    if os.path.exists(DB_PATH):
        print(f"✅ Database already exists at {DB_PATH}")
        return

    print(f"⬇️  Downloading Northwind database...")
    try:
        urllib.request.urlretrieve(DB_URL, DB_PATH)
        print(f"✅ Downloaded to {DB_PATH}")
    except Exception as e:
        print(f"❌ Download failed: {e}")
        print("   Try manually downloading from:")
        print(f"   {DB_URL}")
        sys.exit(1)


def verify_tables():
    """Check all expected tables exist and print row counts."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cursor.fetchall()]

    print(f"\n{'Table':<25} {'Rows':>8}")
    print("-" * 35)

    for table in tables:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cursor.fetchone()[0]
            print(f"{table:<25} {count:>8,}")
        except Exception as e:
            print(f"{table:<25} {'ERROR':>8}  ({e})")

    conn.close()

    missing = [t for t in EXPECTED_TABLES if t not in tables]
    if missing:
        print(f"\n⚠️  Missing tables: {missing}")
        return False

    print(f"\n✅ All {len(EXPECTED_TABLES)} expected tables verified.")
    return True


def run_sample_query():
    """Run a quick sanity check query."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.CompanyName, COUNT(o.OrderID) AS TotalOrders
        FROM Customers c
        JOIN Orders o ON c.CustomerID = o.CustomerID
        GROUP BY c.CustomerID
        ORDER BY TotalOrders DESC
        LIMIT 5
    """)
    rows = cursor.fetchall()
    conn.close()

    print("\n🔍 Sample query — Top 5 customers by order count:")
    print(f"  {'Company':<35} {'Orders':>8}")
    print("  " + "-" * 45)
    for company, count in rows:
        print(f"  {company:<35} {count:>8}")
    print("\n✅ Sample query executed successfully.\n")


if __name__ == "__main__":
    download_northwind()
    ok = verify_tables()
    if ok:
        run_sample_query()
