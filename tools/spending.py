import os
import json
from datetime import date
from pathlib import Path
import duckdb

DB_PATH = os.environ.get(
    "SPENDWISELY_DB",
    str(Path.home() / "Projects/SpendWisely/db/spendwisely.duckdb"),
)


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


def _start_month(months_back: int) -> str:
    today = date.today()
    m = today.month - (months_back - 1)
    y = today.year
    while m <= 0:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def get_spending_summary(months: int = 3) -> str:
    """
    Monthly income/expense summary for the past N months.
    Excludes internal transfers between own accounts.
    Returns totals and per-month breakdown in PLN.
    """
    start = _start_month(months)
    conn = _conn()
    rows = conn.execute(
        """
        SELECT
            month,
            ROUND(SUM(CASE WHEN direction = 'income'  THEN abs_amount ELSE 0 END), 2) AS income,
            ROUND(SUM(CASE WHEN direction = 'expense' THEN abs_amount ELSE 0 END), 2) AS expenses
        FROM transactions
        WHERE month >= ?
          AND direction != 'internal'
        GROUP BY month
        ORDER BY month
        """,
        [start],
    ).fetchall()

    monthly = [
        {"month": r[0], "income": r[1], "expenses": r[2], "net": round(r[1] - r[2], 2)}
        for r in rows
    ]
    totals = {
        "income":   round(sum(r["income"]   for r in monthly), 2),
        "expenses": round(sum(r["expenses"] for r in monthly), 2),
        "net":      round(sum(r["net"]      for r in monthly), 2),
    }
    return json.dumps({"from": start, "months": monthly, "totals": totals}, indent=2)


def get_spending_by_category(months: int = 1, direction: str = "expense") -> str:
    """
    Spending breakdown by category for the past N months.
    direction: 'expense' (default), 'income', or 'all'
    """
    if direction not in ("expense", "income", "all"):
        raise ValueError("direction must be 'expense', 'income', or 'all'")

    start = _start_month(months)
    conn = _conn()

    params: list = [start]
    dir_clause = ""
    if direction != "all":
        dir_clause = "AND direction = ?"
        params.append(direction)

    rows = conn.execute(
        f"""
        SELECT
            category,
            COUNT(*)                    AS count,
            ROUND(SUM(abs_amount), 2)   AS total,
            ROUND(AVG(abs_amount), 2)   AS avg_tx
        FROM transactions
        WHERE month >= ?
          AND direction != 'internal'
          {dir_clause}
        GROUP BY category
        ORDER BY total DESC
        """,
        params,
    ).fetchall()

    categories = [
        {"category": r[0], "count": r[1], "total": r[2], "avg_tx": r[3]}
        for r in rows
    ]
    return json.dumps(
        {"from": start, "direction": direction, "categories": categories}, indent=2
    )


def get_recent_transactions(
    limit: int = 20,
    category: str | None = None,
    direction: str | None = None,
) -> str:
    """
    Recent transactions, newest first.
    Optionally filter by category (e.g. 'Groceries') or direction ('expense', 'income', 'internal').
    """
    conn = _conn()
    filters: list[str] = []
    params: list = []

    if category:
        filters.append("category = ?")
        params.append(category)
    if direction:
        filters.append("direction = ?")
        params.append(direction)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT booking_date, counterparty, title, amount, currency, category, direction
        FROM transactions
        {where}
        ORDER BY booking_date DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    txns = [
        {
            "date": str(r[0]),
            "counterparty": r[1],
            "title": r[2],
            "amount": r[3],
            "currency": r[4],
            "category": r[5],
            "direction": r[6],
        }
        for r in rows
    ]
    return json.dumps({"count": len(txns), "transactions": txns}, indent=2)
