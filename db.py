import json
import sqlite3
from pathlib import Path

from flask import current_app, g

from datetime import date, datetime, timedelta

from seed_data import CATEGORIES, COUPONS, PRODUCTS

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "instance" / "store.db"


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """One connection per request, closed again by close_db()."""
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(path=DB_PATH):
    """(Re)create the tables and load the sample catalog."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    conn.executescript((BASE / "schema.sql").read_text())

    for order, (slug, name, tax) in enumerate(CATEGORIES):
        conn.execute(
            "INSERT INTO categories (slug, name, sort_order, tax_rate) VALUES (?, ?, ?, ?)",
            (slug, name, order, tax),
        )
    cat_ids = {r["slug"]: r["id"] for r in conn.execute("SELECT id, slug FROM categories")}

    for (slug, name, cat, price, old, summary, desc, specs, stock,
         rating, count, image, added) in PRODUCTS:
        conn.execute(
            """INSERT INTO products
               (slug, name, category_id, price, compare_at, summary, description,
                specs, stock, rating, rating_count, image, added_on)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, name, cat_ids[cat], price * 100, old * 100 if old else None,
             summary, desc, json.dumps(specs), stock, rating, count, image, added),
        )

    today = date.today()
    for (code, kind, value, cap, minimum, start, end, max_uses, once, public, desc) in COUPONS:
        conn.execute(
            """INSERT INTO coupons (code, kind, value, max_discount, min_subtotal, starts_on, expires_on,
                   max_uses, once_per_customer, public, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, kind, value if kind == "percent" else value * 100, cap * 100 if cap else None,
             minimum * 100, (today + timedelta(days=start)).isoformat() if start is not None else None,
             (today + timedelta(days=end)).isoformat() if end is not None else None,
             max_uses, once, public, desc, datetime.now().isoformat(timespec="seconds")),
        )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"database ready at {DB_PATH}")
