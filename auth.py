import re
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

def register(name, email, password):
    name=(name or '').strip(); email=(email or '').strip().lower()
    if not name or not email or not password: raise ValueError('All fields are required.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email): raise ValueError('Enter a valid email address.')
    if len(password)<8: raise ValueError('Password must be at least 8 characters.')
    try:
        with get_db() as c:
            row=c.execute('INSERT INTO users(username,email,full_name,password) VALUES(%s,%s,%s,%s) RETURNING id', (email,email,name,generate_password_hash(password))).fetchone()
            return row['id']
    except Exception as e:
        if 'unique' in str(e).lower(): raise ValueError('An account with this email already exists.')
        raise

def authenticate(email,password):
    with get_db() as c:
        u=c.execute('SELECT id,email,full_name,password FROM users WHERE email=%s', ((email or '').strip().lower(),)).fetchone()
        if u and check_password_hash(u['password'], password or ''):
            return {'id':u['id'],'email':u['email'],'full_name':u['full_name'] or u['email']}
        return None
