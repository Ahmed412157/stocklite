import os, sqlite3
DATABASE = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'stocklite.db'))
def create_tables():
    c=sqlite3.connect(DATABASE)
    try:
        c.execute('PRAGMA foreign_keys=ON')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,category TEXT DEFAULT '',quantity INTEGER NOT NULL DEFAULT 0,price REAL NOT NULL DEFAULT 0,cost_price REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY AUTOINCREMENT,sale_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,total_amount REAL NOT NULL DEFAULT 0,payment_method TEXT DEFAULT 'Cash',user_id INTEGER);
        CREATE TABLE IF NOT EXISTS sale_items(id INTEGER PRIMARY KEY AUTOINCREMENT,sale_id INTEGER NOT NULL,product_id INTEGER NOT NULL,quantity INTEGER NOT NULL,unit_price REAL NOT NULL,unit_cost REAL,FOREIGN KEY(sale_id) REFERENCES sales(id),FOREIGN KEY(product_id) REFERENCES products(id));
        CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY AUTOINCREMENT,purchase_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,supplier_name TEXT NOT NULL,total_amount REAL NOT NULL DEFAULT 0,notes TEXT DEFAULT '',user_id INTEGER);
        CREATE TABLE IF NOT EXISTS purchase_items(id INTEGER PRIMARY KEY AUTOINCREMENT,purchase_id INTEGER NOT NULL,product_id INTEGER NOT NULL,quantity INTEGER NOT NULL,unit_cost REAL NOT NULL,FOREIGN KEY(purchase_id) REFERENCES purchases(id),FOREIGN KEY(product_id) REFERENCES products(id));
        CREATE TABLE IF NOT EXISTS stock_movements(id INTEGER PRIMARY KEY AUTOINCREMENT,product_id INTEGER NOT NULL,movement_type TEXT NOT NULL,quantity_change INTEGER NOT NULL,movement_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,reference_id INTEGER,notes TEXT DEFAULT '');
        ''')
        def add(t,n,d):
            if n not in {r[1] for r in c.execute(f'PRAGMA table_info({t})')}: c.execute(f'ALTER TABLE {t} ADD COLUMN {n} {d}')
        for t,n,d in [('users','email','TEXT'),('users','full_name','TEXT'),('products','cost_price','REAL NOT NULL DEFAULT 0'),('products','user_id','INTEGER'),('sales','user_id','INTEGER'),('purchases','user_id','INTEGER'),('stock_movements','user_id','INTEGER'),('sale_items','unit_cost','REAL')]: add(t,n,d)
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL')
        for t in ('products','sales','purchases','stock_movements'): c.execute(f'CREATE INDEX IF NOT EXISTS idx_{t}_user ON {t}(user_id)')
        c.commit()
    finally: c.close()
def claim_legacy_data(uid):
    c=sqlite3.connect(DATABASE)
    try:
        for t in ('products','sales','purchases','stock_movements'): c.execute(f'UPDATE {t} SET user_id=? WHERE user_id IS NULL',(uid,))
        c.commit()
    finally: c.close()
