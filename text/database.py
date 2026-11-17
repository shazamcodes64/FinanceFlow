
import sqlite3
import sys
import os
import shutil
import csv

from pathlib import Path
from datetime import date, datetime


# ============================================================
# DATABASE LOCATION
# ============================================================

if getattr(sys, "frozen", False):
    # Packaged application (.exe)
    # Store user data in Windows AppData, not beside the EXE.
    BASE_DIR = (
        Path(os.environ.get("LOCALAPPDATA", Path.home()))
        / "FinanceFlow"
    )
else:
    # Normal development mode
    # Keeps using your existing project database.
    BASE_DIR = Path(__file__).resolve().parent


DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATABASE_DIR / "finance.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():
    with get_connection() as connection:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_type TEXT NOT NULL
                    CHECK(transaction_type IN ('Income', 'Expense')),
                amount REAL NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                transaction_date TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category_type TEXT NOT NULL
                    CHECK(category_type IN ('Income', 'Expense'))
            )
        """)

        defaults = [
            ("Food", "Expense"),
            ("Shopping", "Expense"),
            ("Travel", "Expense"),
            ("Bills", "Expense"),
            ("Education", "Expense"),
            ("Health", "Expense"),
            ("Entertainment", "Expense"),
            ("Other", "Expense"),
            ("Salary", "Income"),
            ("Business", "Income"),
            ("Investment", "Income"),
            ("Other", "Income")
        ]

        for name, kind in defaults:
            connection.execute(
                """
                INSERT OR IGNORE INTO categories
                (name, category_type)
                VALUES (?, ?)
                """,
                (name, kind)
            )

        connection.execute("""
            INSERT OR IGNORE INTO settings
            (setting_key, setting_value)
            VALUES ('currency', 'INR')
        """)


# ============================================================
# TRANSACTIONS
# ============================================================

def add_transaction(
    transaction_type,
    amount,
    category,
    description,
    transaction_date
):
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO transactions
            (
                transaction_type,
                amount,
                category,
                description,
                transaction_date
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            transaction_type,
            amount,
            category,
            description,
            transaction_date
        ))


def update_transaction(
    transaction_id,
    transaction_type,
    amount,
    category,
    description,
    transaction_date
):
    with get_connection() as connection:
        connection.execute("""
            UPDATE transactions
            SET
                transaction_type = ?,
                amount = ?,
                category = ?,
                description = ?,
                transaction_date = ?
            WHERE id = ?
        """, (
            transaction_type,
            amount,
            category,
            description,
            transaction_date,
            transaction_id
        ))


def delete_transaction(transaction_id):
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM transactions WHERE id = ?",
            (transaction_id,)
        )


# ============================================================
# GET ALL TRANSACTIONS
# ============================================================

def get_all_transactions(
    start_date=None,
    end_date=None,
    transaction_type=None
):
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if start_date:
        query += " AND transaction_date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND transaction_date <= ?"
        params.append(end_date)

    if transaction_type and transaction_type != "All":
        query += " AND transaction_type = ?"
        params.append(transaction_type)

    query += " ORDER BY transaction_date DESC, id DESC"

    with get_connection() as connection:
        return connection.execute(query, params).fetchall()


# ============================================================
# FINANCIAL SUMMARY
# ============================================================

def get_summary(start_date=None, end_date=None):
    query = """
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN transaction_type = 'Income'
                        THEN amount ELSE 0
                    END
                ), 0
            ) AS income,

            COALESCE(
                SUM(
                    CASE
                        WHEN transaction_type = 'Expense'
                        THEN amount ELSE 0
                    END
                ), 0
            ) AS expenses

        FROM transactions
        WHERE 1=1
    """

    params = []

    if start_date:
        query += " AND transaction_date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND transaction_date <= ?"
        params.append(end_date)

    with get_connection() as connection:
        row = connection.execute(query, params).fetchone()

    income = float(row["income"])
    expenses = float(row["expenses"])

    return {
        "income": income,
        "expenses": expenses,
        "balance": income - expenses
    }


# ============================================================
# EXPENSES BY CATEGORY
# ============================================================

def get_expenses_by_category(start_date=None, end_date=None):
    query = """
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE transaction_type = 'Expense'
    """

    params = []

    if start_date:
        query += " AND transaction_date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND transaction_date <= ?"
        params.append(end_date)

    query += " GROUP BY category ORDER BY total DESC"

    with get_connection() as connection:
        return connection.execute(query, params).fetchall()


# ============================================================
# MONTHLY SUMMARY
# ============================================================

def get_monthly_summary(year=None):
    """Return all 12 months for the selected year, including empty months."""

    selected_year = int(year) if year is not None else date.today().year

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT
                CAST(substr(transaction_date, 6, 2) AS INTEGER)
                    AS month_number,

                COALESCE(
                    SUM(
                        CASE
                            WHEN transaction_type = 'Income'
                            THEN amount ELSE 0
                        END
                    ), 0
                ) AS income,

                COALESCE(
                    SUM(
                        CASE
                            WHEN transaction_type = 'Expense'
                            THEN amount ELSE 0
                        END
                    ), 0
                ) AS expenses

            FROM transactions
            WHERE substr(transaction_date, 1, 4) = ?
            GROUP BY substr(transaction_date, 6, 2)
        """, (str(selected_year),)).fetchall()

    by_month = {
        int(row["month_number"]): row
        for row in rows
    }

    return [
        {
            "month": f"{selected_year}-{month:02d}",
            "income": (
                float(by_month[month]["income"])
                if month in by_month else 0.0
            ),
            "expenses": (
                float(by_month[month]["expenses"])
                if month in by_month else 0.0
            )
        }
        for month in range(1, 13)
    ]


# ============================================================
# CATEGORIES
# ============================================================

def get_categories(category_type=None):
    query = "SELECT name FROM categories"
    params = []

    if category_type:
        query += " WHERE category_type = ?"
        params.append(category_type)

    query += " ORDER BY name COLLATE NOCASE"

    with get_connection() as connection:
        return [
            row["name"]
            for row in connection.execute(query, params).fetchall()
        ]


def add_category(name, category_type):
    name = name.strip()

    if not name:
        raise ValueError("Category name cannot be empty.")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO categories (name, category_type)
            VALUES (?, ?)
            """,
            (name, category_type)
        )


def delete_category(name, category_type):
    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM categories
            WHERE name = ? AND category_type = ?
            """,
            (name, category_type)
        )


# ============================================================
# SETTINGS
# ============================================================

def get_setting(key, default=None):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT setting_value
            FROM settings
            WHERE setting_key = ?
            """,
            (key,)
        ).fetchone()

    return row["setting_value"] if row else default


def set_setting(key, value):
    with get_connection() as connection:
        connection.execute("""
            INSERT INTO settings (setting_key, setting_value)
            VALUES (?, ?)

            ON CONFLICT(setting_key)
            DO UPDATE SET setting_value = excluded.setting_value
        """, (key, str(value)))


# ============================================================
# DATABASE BACKUP
# ============================================================

def backup_database(destination):
    destination = Path(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(DATABASE_PATH, destination)

    return destination


# ============================================================
# EXPORT TRANSACTIONS TO CSV
# ============================================================

def export_transactions_csv(
    destination,
    start_date=None,
    end_date=None
):
    rows = get_all_transactions(start_date, end_date)

    with open(
        destination,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "ID",
            "Type",
            "Amount",
            "Category",
            "Description",
            "Date"
        ])

        for row in rows:
            writer.writerow([
                row["id"],
                row["transaction_type"],
                row["amount"],
                row["category"],
                row["description"],
                row["transaction_date"]
            ])

    return len(rows)
