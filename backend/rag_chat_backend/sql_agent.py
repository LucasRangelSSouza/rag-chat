"""SQL agent for structured research bases.

For a base made of well-typed analytical tables (for example education finance), retrieval over text
chunks is the wrong tool: the answer is a number or a ranking. This module lets the model write ONE
read-only SELECT over an allow-listed set of tables, validates it, runs it with a read-only role and a
statement timeout, and returns the SQL with its result rows so the answer can show its evidence.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any

MAX_ROWS = 50
_FORBIDDEN_WORDS = re.compile(r"\b(insert|update|delete|drop|alter|create|grant|revoke|copy|call|do|vacuum|truncate|listen|notify|set|reset)\b", re.I)


class UnsafeSql(ValueError):
    pass


def validate_sql(sql: str, allowed: set[str]) -> str:
    """Return a single SELECT statement over allowed tables, or raise UnsafeSql."""
    import sqlglot
    from sqlglot import exp

    text = sql.strip().rstrip(";").strip()
    if not text or len(text) > 4000:
        raise UnsafeSql("empty or too long")
    try:
        statements = sqlglot.parse(text, read="postgres")
    except sqlglot.errors.ParseError as error:
        raise UnsafeSql(f"not valid SQL: {str(error)[:120]}") from error
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeSql("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.With)) and not tree.find(exp.Select):
        raise UnsafeSql("only SELECT is allowed")
    if isinstance(tree, exp.Command) or tree.find(exp.Into) or tree.find(exp.Lock):
        raise UnsafeSql("only SELECT is allowed")
    for node in tree.walk():
        node = node[0] if isinstance(node, tuple) else node
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create, exp.Command)):
            raise UnsafeSql("only SELECT is allowed")
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        qualified = f"{table.db.lower()}.{name}" if table.db else name
        if name in cte_names and not table.db:
            continue
        if qualified not in allowed and name not in {a.split(".")[-1] for a in allowed}:
            raise UnsafeSql(f"table not allowed: {qualified}")
    if re.search(r"\bpg_\w+|information_schema", text, re.I):
        raise UnsafeSql("system catalogs are not allowed")
    return text


SYSTEM = ("You write one PostgreSQL SELECT statement that answers the user's question over the tables described below. "
          "Rules: one statement, SELECT only, use only the listed tables and columns, qualify tables with their schema, "
          "aggregate and ORDER BY when the question asks for a ranking or total, and add LIMIT 50 at most. "
          "Whenever a result has several rows, order them by the main measure, largest first, so the rows read as a ranking. "
          "When the question asks for several numbers at once (for example a count, a total and a top three), return all of "
          "them in one result: one row per ranked item with the overall totals repeated as extra columns (window functions "
          "such as SUM(...) OVER () or a CTE). "
          "Use the statistic the question names: PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col) for a median, AVG only for an average. "
          "PostgreSQL does not allow PERCENTILE_CONT with OVER (): compute a median in its own CTE and join it back. "
          "Keep queries short: use at most four LIKE patterns for a topic, chosen from its most common words. "
          "Answer with JSON only: {\"sql\": \"...\", \"explanation\": \"one sentence about what the query measures\"}. "
          "A question can have several parts and other sources answer the rest: write the query for the part these tables "
          "can answer and ignore the other parts. Only when no part can be answered from these tables, answer "
          "{\"sql\": null, \"explanation\": \"why\"}.")


class SqlStore:
    is_sql = True

    def __init__(self, dsn: str, tables: list[str], cutoff: str = "n/a", notes: str = "") -> None:
        import psycopg

        self._psycopg, self.dsn, self.tables, self.cutoff, self.notes = psycopg, dsn, tables, cutoff, notes
        self.allowed = {t.lower() for t in tables}
        self._schema_text: str | None = None
        self._lock = threading.Lock()

    def _connect(self):
        return self._psycopg.connect(self.dsn, autocommit=True, connect_timeout=5,
                                     options="-c default_transaction_read_only=on -c statement_timeout=25000")

    def schema_text(self) -> str:
        if self._schema_text is None:
            parts = []
            with self._connect() as conn, conn.cursor() as cur:
                for full in self.tables:
                    schema, name = full.split(".")
                    cur.execute("SELECT obj_description(%s::regclass, 'pg_class')", (full,))
                    table_comment = cur.fetchone()[0] or ""
                    cur.execute("SELECT a.attname, format_type(a.atttypid, a.atttypmod), col_description(a.attrelid, a.attnum) "
                                "FROM pg_attribute a WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum",
                                (full,))
                    cols = "\n".join(f"  {c} {t}" + (f" -- {d}" if d else "") for c, t, d in cur.fetchall())
                    parts.append(f"TABLE {full}" + (f" -- {table_comment}" if table_comment else "") + f"\n{cols}")
            self._schema_text = "\n\n".join(parts)
        return self._schema_text

    def meta(self) -> dict:
        return {"data_cutoff": self.cutoff, "table_count": len(self.tables), "record_count": None}

    def run(self, sql: str) -> tuple[list[str], list[list[Any]]]:
        safe = validate_sql(sql, self.allowed)
        with self._lock, self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM ({safe}) AS q LIMIT {MAX_ROWS}")
            columns = [d.name for d in cur.description]
            rows = [[None if v is None else (float(v) if hasattr(v, "as_tuple") else v) for v in row] for row in cur.fetchall()]
        return columns, rows

    def ask(self, question: str, model) -> dict:
        """Ask the model for SQL, run it, repair once on a database error. Returns {sql, columns, rows, explanation} or {error}."""
        notes = f"\n\nNotes about these tables:\n{self.notes}" if self.notes else ""
        prompt = f"{self.schema_text()}{notes}\n\nQuestion: {question}"
        feedback = ""
        for _ in range(2):
            reply = model.chat_json(SYSTEM, prompt + feedback)
            if not reply or not reply.get("sql"):
                return {"error": (reply or {}).get("explanation") or "no query"}
            try:
                columns, rows = self.run(reply["sql"])
                if rows and all(v is None for row in rows for v in row) and not feedback:
                    # Only NULLs usually means a filter value that does not exist (a name spelled differently).
                    feedback = ("\n\nYour previous query returned only NULL values. A filter value probably does not match the "
                                "data: check the exact spelling and format of names and categories, then write a corrected query.")
                    continue
                if not rows and not feedback:
                    # An empty answer is usually a wrong filter or table, so ask once for another approach.
                    feedback = ("\n\nYour previous query returned no rows. Check the filters (values, years, period) and "
                                "whether a different table or column holds the data, then write a corrected query.")
                    continue
                return {"sql": reply["sql"].strip().rstrip(";"), "columns": columns, "rows": rows,
                        "explanation": str(reply.get("explanation", ""))[:300]}
            except UnsafeSql as error:
                feedback = f"\n\nYour previous query was rejected: {error}. Write a corrected single SELECT."
            except self._psycopg.errors.QueryCanceled:
                feedback = ("\n\nYour previous query was too slow and was cancelled. Narrow it: filter by year first, avoid "
                            "functions on indexed columns, and search text with a single ILIKE pattern.")
            except Exception as error:  # noqa: BLE001
                feedback = f"\n\nYour previous query failed with: {str(error)[:200]}. Write a corrected query."
        return {"error": "the model could not produce a valid query"}


def parse_json_reply(text: str) -> dict | None:
    """Extract the first JSON object from a model reply (models sometimes wrap it in a code fence)."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None
