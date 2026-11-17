import os
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured. Add your Neon connection string in Render Environment Variables.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def create_tables():
    with get_db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL, email TEXT UNIQUE, full_name TEXT
        );
        CREATE TABLE IF NOT EXISTS products (
            id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT DEFAULT '',
            quantity INTEGER NOT NULL DEFAULT 0, price DOUBLE PRECISION NOT NULL DEFAULT 0,
            cost_price DOUBLE PRECISION NOT NULL DEFAULT 0, user_id BIGINT REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS sales (
            id BIGSERIAL PRIMARY KEY, sale_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            total_amount DOUBLE PRECISION NOT NULL DEFAULT 0, payment_method TEXT DEFAULT 'Cash',
            user_id BIGINT REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS sale_items (
            id BIGSERIAL PRIMARY KEY, sale_id BIGINT NOT NULL REFERENCES sales(id),
            product_id BIGINT NOT NULL REFERENCES products(id), quantity INTEGER NOT NULL,
            unit_price DOUBLE PRECISION NOT NULL, unit_cost DOUBLE PRECISION
        );
        CREATE TABLE IF NOT EXISTS purchases (
            id BIGSERIAL PRIMARY KEY, purchase_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            supplier_name TEXT NOT NULL, total_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '', user_id BIGINT REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS purchase_items (
            id BIGSERIAL PRIMARY KEY, purchase_id BIGINT NOT NULL REFERENCES purchases(id),
            product_id BIGINT NOT NULL REFERENCES products(id), quantity INTEGER NOT NULL,
            unit_cost DOUBLE PRECISION NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stock_movements (
            id BIGSERIAL PRIMARY KEY, product_id BIGINT NOT NULL REFERENCES products(id),
            movement_type TEXT NOT NULL, quantity_change INTEGER NOT NULL,
            movement_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, reference_id BIGINT,
            notes TEXT DEFAULT '', user_id BIGINT REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_products_user ON products(user_id);
        CREATE INDEX IF NOT EXISTS idx_sales_user ON sales(user_id);
        CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id);
        CREATE INDEX IF NOT EXISTS idx_movements_user ON stock_movements(user_id);
        """)

def claim_legacy_data(uid):
    # Neon starts empty; this helper is retained for compatibility.
    with get_db() as c:
        for table in ("products", "sales", "purchases", "stock_movements"):
            c.execute(f"UPDATE {table} SET user_id=%s WHERE user_id IS NULL", (uid,))
