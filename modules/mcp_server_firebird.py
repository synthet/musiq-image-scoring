"""
Firebird Database MCP Server

Provides low-level database administration and introspection tools for the Firebird database.
Intended for use alongside the main application MCP server.

Tools:
- list_tables: List all user tables
- get_table_schema: Get columns and details for a table
- run_sql: Execute raw SQL queries (READ/WRITE)
- get_firebird_version: Get database engine version
"""
import sys
import os
import contextlib
import json
import logging
from typing import Any, List, Dict, Optional

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import mcp sdk (TypeError: some pydantic/mcp combinations break MRO at import time)
try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except (ImportError, TypeError):
    MCP_AVAILABLE = False


# Helper to suppress stdout from imported modules (like db.py)
@contextlib.contextmanager
def suppress_stdout():
    """Context manager to suppress stdout/stderr to keep MCP channel clean."""
    # MCP uses stdin/stdout for communication. 
    # Any print() from imported modules will corrupt the protocol.
    with open(os.devnull, 'w') as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout

# Import app modules safely
with suppress_stdout():
    try:
        from modules import db
    except ImportError:
        # Fallback if run from wrong directory
        pass

# Initialize FastMCP
if MCP_AVAILABLE:
    mcp = FastMCP("firebird-admin")
else:
    # Fallback mock for syntax checking
    class MockMCP:
        def tool(self):
            return lambda x: x
        def run(self):
            print("MCP not available")
    mcp = MockMCP()


@mcp.tool()
def list_tables() -> List[str]:
    """List all user tables in the database."""
    with suppress_stdout():
        try:
            with db.connection() as conn:
                c = conn.cursor()
                # RDB$SYSTEM_FLAG = 0 means user table
                # RDB$VIEW_BLR IS NULL filters out views
                query = """
                    SELECT RDB$RELATION_NAME
                    FROM RDB$RELATIONS
                    WHERE RDB$SYSTEM_FLAG = 0 AND RDB$VIEW_BLR IS NULL
                    ORDER BY RDB$RELATION_NAME
                """
                c.execute(query)
                rows = c.fetchall()
                return [str(row[0]).strip() for row in rows]
        except Exception as e:
            return [f"Error: {str(e)}"]

@mcp.tool()
def get_table_schema(table_name: str) -> List[Dict[str, Any]]:
    """Get schema information for a specific table."""
    with suppress_stdout():
        try:
            with db.connection() as conn:
                c = conn.cursor()

                # 1. Get Column details
                # Queries RDB$RELATION_FIELDS joined with RDB$FIELDS
                # Note: Firebird system tables can be complex.
                # RDB$FIELD_SOURCE links to domain definition in RDB$FIELDS
                query = """
                    SELECT
                        rf.RDB$FIELD_NAME,
                        f.RDB$FIELD_TYPE,
                        f.RDB$FIELD_LENGTH,
                        rf.RDB$NULL_FLAG
                    FROM RDB$RELATION_FIELDS rf
                    JOIN RDB$FIELDS f ON rf.RDB$FIELD_SOURCE = f.RDB$FIELD_NAME
                    WHERE rf.RDB$RELATION_NAME = ?
                    ORDER BY rf.RDB$FIELD_POSITION
                """
                c.execute(query, (table_name.upper(),))
                rows = c.fetchall()

                # Basic Type Mapping (Approximate for Firebird)
                type_map = {
                    7: 'SMALLINT', 8: 'INTEGER', 10: 'FLOAT', 12: 'DATE',
                    13: 'TIME', 14: 'CHAR', 16: 'BIGINT', 27: 'DOUBLE',
                    35: 'TIMESTAMP', 37: 'VARCHAR', 261: 'BLOB'
                }

                schema = []
                for row in rows:
                    # Handle varying row formats (tuple vs obj)
                    field_name = str(row[0]).strip()
                    field_type_code = row[1]
                    field_length = row[2]
                    null_flag = row[3]

                    type_name = type_map.get(field_type_code, f"UNKNOWN({field_type_code})")

                    schema.append({
                        "name": field_name,
                        "type": type_name,
                        "length": field_length,
                        "nullable": (null_flag != 1)
                    })

                return schema
        except Exception as e:
            return [{"error": str(e)}]

@mcp.tool()
def run_sql(query: str, params: List[Any] = None) -> Dict[str, Any]:
    """Execute a raw SQL query.

    WARNING: This tool allows ANY query, including modifications. Use with caution.
    """
    # Params needs to be a list if provided
    if params is None:
        params = []

    with suppress_stdout():
        try:
            with db.connection() as conn:
                c = conn.cursor()

                # Check if it's a SELECT query for returning results
                is_select = query.strip().upper().startswith("SELECT") or query.strip().upper().startswith("WITH")

                # Execute
                if params:
                    c.execute(query, tuple(params))
                else:
                    c.execute(query)

                result = {}
                if is_select:
                    rows = c.fetchall()

                    # Try to get column names from description
                    cols = []
                    if c.description:
                        cols = [d[0] for d in c.description]

                    # Convert rows
                    data = []
                    for row in rows:
                        if hasattr(row, 'keys'):
                            # Dict-like row (sqlite3.Row or similar from db.py wrapper)
                            row_dict = dict(row)
                            # Fix bytes/blob for JSON serialization if needed?
                            # For now assume simple types
                            data.append(row_dict)
                        else:
                            # Tuple row
                            if cols:
                                data.append(dict(zip(cols, row)))
                            else:
                                data.append(list(row))

                    result = {
                        "columns": cols,
                        "row_count": len(rows),
                        "data": data[:500] # Limit to prevent overwhelming MCP
                    }
                else:
                    conn.commit()
                    result = {"status": "success", "message": "Query executed successfully."}

                return result
        except Exception as e:
            return {"status": "error", "message": str(e)}

@mcp.tool()
def get_firebird_version() -> str:
    """Get the Firebird database version."""
    with suppress_stdout():
        try:
            with db.connection() as conn:
                c = conn.cursor()
                # Classic way to get version in FB 2.1+
                c.execute("SELECT rdb$get_context('SYSTEM', 'ENGINE_VERSION') as ver FROM rdb$database")
                row = c.fetchone()
                if row:
                    return str(row[0])
                return "Unknown"
        except Exception as e:
            return f"Error: {str(e)}"

if __name__ == "__main__":
    if not MCP_AVAILABLE:
        print("Error: 'mcp' package not installed. Please install it with 'pip install mcp'", file=sys.stderr)
        sys.exit(1)
    
    # Run server
    mcp.run()
