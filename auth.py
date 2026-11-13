import re, sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from database import DATABASE

def register(name,email,password):
    name=(name or '').strip(); email=(email or '').strip().lower()
    if not name or not email or not password: raise ValueError('All fields are required.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise ValueError('Enter a valid email address.')
    if len(password)<8: raise ValueError('Password must be at least 8 characters.')
    c=sqlite3.connect(DATABASE)
    try:
        cur=c.execute('INSERT INTO users(username,email,full_name,password) VALUES(?,?,?,?)',(email,email,name,generate_password_hash(password)))
        c.commit(); return cur.lastrowid
    except sqlite3.IntegrityError: raise ValueError('An account with this email already exists.')
    finally: c.close()
def authenticate(email,password):
    c=sqlite3.connect(DATABASE); c.row_factory=sqlite3.Row
    try:
        u=c.execute('SELECT id,email,full_name,password FROM users WHERE email=?',((email or '').strip().lower(),)).fetchone()
        if u and check_password_hash(u['password'],password or ''): return {'id':u['id'],'email':u['email'],'full_name':u['full_name'] or u['email']}
        return None
    finally: c.close()
