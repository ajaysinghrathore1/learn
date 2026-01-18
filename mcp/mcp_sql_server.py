# server_sql.py
import os
import re
import pyodbc
from fastmcp import FastMCP
from langchain_community.utilities.sql_database import SQLDatabase

import pandas as pd
from sqlalchemy import create_engine
import urllib



mcp = FastMCP("MSSQL-MCP-Server", json_response=True)

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def qident(name: str) -> str:
    # strict identifier allowlist; prevents SQL injection via table/column names
    if not IDENT_RE.match(name):
        raise ValueError(f"Invalid identifier: {name}")
    return f"[{name}]"

def get_conn():
    # Example: use env var like:
    # MSSQL_CONN="Driver={ODBC Driver 18 for SQL Server};Server=...;Database=...;UID=...;PWD=...;Encrypt=yes;TrustServerCertificate=no;"
    database = "northwind"  #"demo"
    # database="AdventureWorks"
    table = "dbo.orders"
    # table = "SalesLT.Product"
    username = "ajay"
    password = "callme123"
    DB_SERVER  = r"localhost:1433"

    conn_str = f"mssql+pyodbc://{username}:{password}@{DB_SERVER }/{database}?driver=ODBC+Driver+17+for+SQL+Server"

    _DB = SQLDatabase.from_uri(conn_str)        
    return _DB   ##pyodbc.connect(os.environ["MSSQL_CONN"])

def get_odbc_conn():
    # 1. Your existing connection details
    params = urllib.parse.quote_plus(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost;"
        "DATABASE=northwind;"
        "UID=ajay;"
        "PWD=callme123;"
        "Encrypt=no;"  # Required for modern drivers like version 18
        "TrustServerCertificate=yes;"
    )

    # 2. Create a SQLAlchemy engine
    # The 'mssql+pyodbc://' prefix tells SQLAlchemy to use pyodbc as the driver
    engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
    return engine

@mcp.tool()
def get_table_data(sql : str) -> str:
    " return the table list from schema"
    # and OBJECT_NAME(p.object_id) not like 'spGetPermission%' 

    engine = get_odbc_conn()
    # 3. Use the engine with pd.read_sql
    df = pd.read_sql(sql, engine)

    # Common options for a cleaner string
    df_str = df.to_string(
        index=False,          # Remove the row numbers
        # max_rows=None,        # Show all rows without truncation
        na_rep='N/A',         # Custom string for missing values
        float_format="%.2f"   # Format decimals to 2 places
    )
     # Return as JSON string to preserve the structure over MCP
    return df.to_json(orient="records")
    # df_str
    # return {"ok": True, "table data": df_str}


@mcp.tool()
def describe_table(schema: str, table: str) -> dict:
    """Return columns, types, nullability, PK and FK info for a table."""
    s, t = qident(schema), qident(table)
    with get_conn() as conn:
        cur = conn.cursor()

        # columns
        cur.execute(f"""
            SELECT c.name, ty.name AS type_name, c.max_length, c.precision, c.scale, c.is_nullable
            FROM sys.columns c
            JOIN sys.types ty ON c.user_type_id = ty.user_type_id
            JOIN sys.tables tb ON c.object_id = tb.object_id
            JOIN sys.schemas sc ON tb.schema_id = sc.schema_id
            WHERE sc.name = ? AND tb.name = ?
            ORDER BY c.column_id
        """, (schema, table))
        cols = [
            dict(name=r[0], type=r[1], max_length=r[2], precision=r[3], scale=r[4], nullable=bool(r[5]))
            for r in cur.fetchall()
        ]

        # primary key columns
        cur.execute("""
            SELECT col.name
            FROM sys.indexes i
            JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            JOIN sys.columns col ON ic.object_id = col.object_id AND ic.column_id = col.column_id
            JOIN sys.tables tb ON i.object_id = tb.object_id
            JOIN sys.schemas sc ON tb.schema_id = sc.schema_id
            WHERE i.is_primary_key = 1 AND sc.name = ? AND tb.name = ?
            ORDER BY ic.key_ordinal
        """, (schema, table))
        pk = [r[0] for r in cur.fetchall()]

        # foreign keys (outgoing)
        cur.execute("""
            SELECT
              fk.name AS fk_name,
              sc_from.name AS from_schema, t_from.name AS from_table, c_from.name AS from_column,
              sc_to.name   AS to_schema,   t_to.name   AS to_table,   c_to.name   AS to_column
            FROM sys.foreign_key_columns fkc
            JOIN sys.foreign_keys fk ON fkc.constraint_object_id = fk.object_id
            JOIN sys.tables t_from ON fkc.parent_object_id = t_from.object_id
            JOIN sys.schemas sc_from ON t_from.schema_id = sc_from.schema_id
            JOIN sys.columns c_from ON c_from.object_id = t_from.object_id AND c_from.column_id = fkc.parent_column_id
            JOIN sys.tables t_to ON fkc.referenced_object_id = t_to.object_id
            JOIN sys.schemas sc_to ON t_to.schema_id = sc_to.schema_id
            JOIN sys.columns c_to ON c_to.object_id = t_to.object_id AND c_to.column_id = fkc.referenced_column_id
            WHERE sc_from.name = ? AND t_from.name = ?
        """, (schema, table))
        fks = [
            dict(
                fk_name=r[0],
                from_schema=r[1], from_table=r[2], from_column=r[3],
                to_schema=r[4],   to_table=r[5],   to_column=r[6],
            )
            for r in cur.fetchall()
        ]

    return {"schema": schema, "table": table, "columns": cols, "primary_key": pk, "foreign_keys": fks}

@mcp.tool()
def add_row(schema: str, table: str, data: dict) -> dict:
    """Insert one row using parameterized SQL."""
    if not data:
        raise ValueError("data is empty")

    cols = list(data.keys())
    vals = list(data.values())

    col_sql = ", ".join(qident(c) for c in cols)
    ph_sql = ", ".join("?" for _ in cols)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {qident(schema)}.{qident(table)} ({col_sql}) VALUES ({ph_sql});",
            vals,
        )
        conn.commit()
        return {"ok": True, "rows_affected": cur.rowcount}

@mcp.tool()
def update_row(schema: str, table: str, where: dict, set: dict) -> dict:
    """Update rows safely (requires a WHERE)."""
    if not where:
        raise ValueError("Refusing to update without WHERE conditions")
    if not set:
        raise ValueError("set is empty")

    set_cols = list(set.keys())
    where_cols = list(where.keys())

    set_sql = ", ".join(f"{qident(c)}=?" for c in set_cols)
    where_sql = " AND ".join(f"{qident(c)}=?" for c in where_cols)

    params = list(set.values()) + list(where.values())

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {qident(schema)}.{qident(table)} SET {set_sql} WHERE {where_sql};",
            params,
        )
        conn.commit()
        return {"ok": True, "rows_affected": cur.rowcount}

@mcp.tool()
def get_erd(schema: str, tables: list[str]) -> dict:
    """Return Mermaid ERD text for given tables (simple FK edges)."""
    # You’d call a relationship query like in describe_table for each table,
    # then emit mermaid lines.
    # Keeping it minimal here:
    return {"format": "mermaid", "erd": "erDiagram\n  A ||--o{ B : relates_to\n"}


@mcp.prompt(
    name="get_query_prompt",          # Custom prompt name
    description="return a prompt for llm",  # Custom description
    tags={"query", "prompt"},            # Optional categorization tags
    meta={"version": "1.1", "author": "data-team"}  # Custom metadata
)
def get_query_prompt(db_dialect : str , top_rows : int  = 5) -> dict :
        # If you get an error while  executing a query, rewrite the query and try again.

        system_prompt = """
        You are an agent designed to interact with a SQL database.
        Given an input question, create a syntactically correct {dialect} query,
        RETURN ONLY THE  SQL STATEMENT ONLY with limiting scope most {top_k}.

        Never query for all the columns from a specific table,
        only ask for the relevant columns given the question.

        You MUST double check your query before responding back ONLY QUERY. 

        Make any DML statements (INSERT, UPDATE, DELETE ) to the
        database ONLY if a filter condition provided by User. If no Filter condition, ask user or suggest the filter condition.

        To start you should ALWAYS look at the tables in the database to see what you
        can query. Do NOT skip this step.

        Note: suggest 3-5 distinct user input base on data.
        """.format(
            dialect=db_dialect,
            top_k=top_rows,
        )   
        return  {'system_prompt' :system_prompt}


if __name__ == "__main__":
    # Streamable HTTP is the current transport in the spec; SDK supports it. :contentReference[oaicite:5]{index=5}
    # mcp.run(transport="streamable-http")
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8085,path="/mcp" , )
