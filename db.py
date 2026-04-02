import os
import sqlite3
from typing import Optional

import pandas as pd


def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Create a SQLite connection suitable for Streamlit (multiple threads).
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Better concurrency for Streamlit deployments.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _has_meta_flag(conn: sqlite3.Connection, key: str) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row is not None


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS coupon (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          "Coupon unique code no." TEXT,
          "Date" TEXT,
          "Time" TEXT,
          "Employee code" TEXT,
          "Employee name" TEXT,
          "Type of dish" TEXT,
          "Rupees of items" REAL,
          "OTP" TEXT,
          "Redeemed" INTEGER
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sweet_records (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          "Date" TEXT,
          "Time" TEXT,
          "Employee Number" INTEGER,
          "Employee Name" TEXT,
          "Bill Items" TEXT,
          "MRP" REAL,
          "Discount" REAL,
          "Total Price" REAL,
          "otp" TEXT,
          "redeemed" INTEGER
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employee (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          "Employee Code" REAL,
          "Employee Name" TEXT,
          "CategoryName" TEXT,
          "Department" TEXT,
          "Designation" TEXT,
          "Mobile No." REAL
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS menu (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          "Item" TEXT,
          "Price" REAL,
          "Discount" REAL
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          "Material Description" TEXT,
          "MRP" INTEGER,
          "Discounted amount" REAL,
          "Price" REAL,
          "Weight" INTEGER,
          "unit" TEXT
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          "Personal No" REAL,
          "EMPLOYEE NAME." TEXT,
          "Email Id " TEXT
        );
        """
    )

    conn.commit()


def _bool_to_int(v) -> int:
    if pd.isna(v):
        return 0
    if isinstance(v, (bool, pd.BooleanDtype)):
        return int(bool(v))
    if isinstance(v, (int, float)):
        return int(v != 0)
    s = str(v).strip().lower()
    return 1 if s in {"true", "1", "t", "yes", "y"} else 0


def _normalize_sweet_records_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    The current codebase historically produced different sweet_records schemas.
    Normalize into the columns we use in the app.
    """
    # If it's already in normalized shape, keep it.
    required_cols = [
        "Date",
        "Time",
        "Employee Number",
        "Employee Name",
        "Bill Items",
        "MRP",
        "Discount",
        "Total Price",
        "otp",
        "redeemed",
    ]
    if all(c in df.columns for c in required_cols):
        out = df.copy()
    else:
        # Older schema seen in this repo: ['employee_name', 'otp', 'bill_details']
        out = pd.DataFrame()
        out["Date"] = pd.NaT
        out["Time"] = pd.NaT
        out["Employee Number"] = 0
        out["Employee Name"] = df["employee_name"] if "employee_name" in df.columns else None
        out["Bill Items"] = df["bill_details"] if "bill_details" in df.columns else None
        out["MRP"] = 0.0
        out["Discount"] = 0.0
        out["Total Price"] = 0.0
        out["otp"] = df["otp"] if "otp" in df.columns else None
        out["redeemed"] = 0

    # Ensure columns exist and types are reasonable.
    for c in required_cols:
        if c not in out.columns:
            out[c] = None

    if "redeemed" in out.columns:
        out["redeemed"] = out["redeemed"].apply(_bool_to_int).astype(int)

    return out[required_cols]


def is_sqlite_seeded(conn: sqlite3.Connection) -> bool:
    return _has_meta_flag(conn, "sqlite_seeded_v1")


def migrate_pickles_to_sqlite(
    conn: sqlite3.Connection,
    pickles_dir: str = ".",
    *,
    import_on_first_run: bool = True,
) -> None:
    """
    Import existing pickle files into SQLite exactly once.
    """
    if not import_on_first_run:
        return
    if is_sqlite_seeded(conn):
        return

    def load_pickle(name: str) -> Optional[pd.DataFrame]:
        p = os.path.join(pickles_dir, name)
        if not os.path.exists(p):
            return None
        return pd.read_pickle(p)

    # Read pickles (if available)
    coupon_df = load_pickle("coupon.pkl")
    sweet_df = load_pickle("sweet_records.pkl")
    employee_df = load_pickle("employee.pkl")
    menu_df = load_pickle("menu.pkl")
    price_df = load_pickle("price.pkl")
    email_df = load_pickle("email.pkl")

    # Import
    conn.execute("BEGIN;")
    try:
        # Replace each table to keep migration idempotent on the first run.
        if coupon_df is not None:
            coupon_df = coupon_df.copy()
            if "Redeemed" in coupon_df.columns:
                coupon_df["Redeemed"] = coupon_df["Redeemed"].apply(_bool_to_int).astype(int)
            coupon_df.to_sql("coupon", conn, if_exists="append", index=False)

        if sweet_df is not None:
            sweet_norm = _normalize_sweet_records_df(sweet_df)
            sweet_norm.to_sql("sweet_records", conn, if_exists="append", index=False)

        if employee_df is not None:
            employee_df.to_sql("employee", conn, if_exists="append", index=False)

        if menu_df is not None:
            menu_df.to_sql("menu", conn, if_exists="append", index=False)

        if price_df is not None:
            price_df.to_sql("price", conn, if_exists="append", index=False)

        if email_df is not None:
            email_df.to_sql("email", conn, if_exists="append", index=False)

        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?);",
            ("sqlite_seeded_v1", "1"),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _select_all(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    df = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
    return df


def load_coupon_df(conn: sqlite3.Connection, *, include_id: bool = False) -> pd.DataFrame:
    df = _select_all(conn, "coupon")
    if not include_id and "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def load_sweet_records_df(
    conn: sqlite3.Connection, *, include_id: bool = False
) -> pd.DataFrame:
    df = _select_all(conn, "sweet_records")
    if not include_id and "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def load_employee_df(conn: sqlite3.Connection, *, include_id: bool = False) -> pd.DataFrame:
    df = _select_all(conn, "employee")
    if not include_id and "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def load_menu_df(conn: sqlite3.Connection, *, include_id: bool = False) -> pd.DataFrame:
    df = _select_all(conn, "menu")
    if not include_id and "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def load_price_df(conn: sqlite3.Connection, *, include_id: bool = False) -> pd.DataFrame:
    df = _select_all(conn, "price")
    if not include_id and "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def load_email_df(conn: sqlite3.Connection, *, include_id: bool = False) -> pd.DataFrame:
    df = _select_all(conn, "email")
    if not include_id and "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def replace_table_from_df(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    """
    Replace all rows in a table with the provided DataFrame.
    """
    # Delete existing data
    conn.execute(f'DELETE FROM "{table}";')

    # Normalize bool->int where needed
    if table == "coupon" and "Redeemed" in df.columns:
        df = df.copy()
        df["Redeemed"] = df["Redeemed"].apply(_bool_to_int).astype(int)

    if table == "sweet_records" and "redeemed" in df.columns:
        df = df.copy()
        df["redeemed"] = df["redeemed"].apply(_bool_to_int).astype(int)

    df.to_sql(table, conn, if_exists="append", index=False)
    conn.commit()


def insert_coupon_row(conn: sqlite3.Connection, row: dict) -> None:
    df = pd.DataFrame([row])
    if "Redeemed" in df.columns:
        df["Redeemed"] = df["Redeemed"].apply(_bool_to_int).astype(int)
    df.to_sql("coupon", conn, if_exists="append", index=False)
    conn.commit()


def redeem_coupon_by_id(conn: sqlite3.Connection, coupon_id: int) -> None:
    conn.execute(
        'UPDATE "coupon" SET "Redeemed" = 1 WHERE id = ? AND "Redeemed" = 0;',
        (coupon_id,),
    )
    conn.commit()


def redeem_sweet_record_by_id(conn: sqlite3.Connection, sweet_id: int) -> None:
    conn.execute(
        'UPDATE "sweet_records" SET "redeemed" = 1 WHERE id = ? AND "redeemed" = 0;',
        (sweet_id,),
    )
    conn.commit()


def insert_sweet_record_row(conn: sqlite3.Connection, row: dict) -> None:
    df = pd.DataFrame([row])
    if "redeemed" in df.columns:
        df["redeemed"] = df["redeemed"].apply(_bool_to_int).astype(int)
    df.to_sql("sweet_records", conn, if_exists="append", index=False)
    conn.commit()

