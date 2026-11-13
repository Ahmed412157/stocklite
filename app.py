import os, sqlite3
from datetime import timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, session
from database import DATABASE, create_tables, claim_legacy_data
from auth import register, authenticate

app=Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY','CHANGE-THIS-SECRET-BEFORE-DEPLOYMENT'),SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','0')=='1',PERMANENT_SESSION_LIFETIME=timedelta(days=30))
create_tables()
def db():
    c=sqlite3.connect(DATABASE); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def uid(): return session.get('user_id')
def protected(fn):
    @wraps(fn)
    def w(*a,**k):
        if not uid(): return jsonify(success=False,message='Please log in to continue.'),401
        return fn(*a,**k)
    return w
def data(): return request.get_json(silent=True) or request.form

@app.get('/')
def home(): return render_template('Inventory management.html')
@app.get('/auth/me')
def me():
    if not uid(): return jsonify(success=True,authenticated=False)
    return jsonify(success=True,authenticated=True,user={'id':uid(),'email':session.get('email'),'full_name':session.get('full_name')})
@app.post('/register')
def register_route():
    d=data()
    try:
        user_id=register(d.get('full_name') or d.get('name'),d.get('email'),d.get('password'))
        c=db(); unclaimed=c.execute('SELECT COUNT(*) FROM products WHERE user_id IS NULL').fetchone()[0]; c.close()
        if unclaimed: claim_legacy_data(user_id)
        session.clear(); session.update(user_id=user_id,email=d.get('email','').strip().lower(),full_name=(d.get('full_name') or d.get('name') or '').strip()); session.permanent=bool(d.get('remember_me'))
        return jsonify(success=True,message='Account created successfully.'),201
    except ValueError as e: return jsonify(success=False,message=str(e)),400
@app.post('/login')
def login_route():
    d=data(); u=authenticate(d.get('email'),d.get('password'))
    if not u: return jsonify(success=False,message='Incorrect email or password.'),401
    session.clear(); session.update(user_id=u['id'],email=u['email'],full_name=u['full_name']); session.permanent=bool(d.get('remember_me'))
    return jsonify(success=True,message='Login successful.',user=u)
@app.post('/logout')
def logout(): session.clear(); return jsonify(success=True)

@app.get('/products')
@protected
def products_get():
    c=db(); rows=c.execute('SELECT id,name,category,quantity,price,cost_price FROM products WHERE user_id=? ORDER BY id DESC',(uid(),)).fetchall(); c.close(); return jsonify([dict(x) for x in rows])
@app.post('/products')
@protected
def products_add():
    d=data()
    try:
        name=str(d.get('name','')).strip(); q=int(d.get('quantity',0)); p=float(d.get('price',0)); cost=float(d.get('cost_price',0) or 0)
        if not name or min(q,p,cost)<0: raise ValueError
    except (ValueError,TypeError): return jsonify(success=False,message='Invalid product data.'),400
    c=db(); cur=c.execute('INSERT INTO products(name,category,quantity,price,cost_price,user_id) VALUES(?,?,?,?,?,?)',(name,d.get('category',''),q,p,cost,uid())); c.commit(); pid=cur.lastrowid;c.close();return jsonify(success=True,id=pid,message='Product added.'),201
@app.route('/products/<int:pid>',methods=['PUT','DELETE'])
@protected
def products_detail(pid):
    c=db(); p=c.execute('SELECT * FROM products WHERE id=? AND user_id=?',(pid,uid())).fetchone()
    if not p: c.close();return jsonify(success=False,message='Product not found.'),404
    if request.method=='DELETE': c.execute('DELETE FROM products WHERE id=? AND user_id=?',(pid,uid()));c.commit();c.close();return jsonify(success=True)
    d=request.get_json(silent=True) or {}
    try:
        vals=(str(d.get('name',p['name'])).strip(),d.get('category',p['category']),int(d.get('quantity',p['quantity'])),float(d.get('price',p['price'])),float(d.get('cost_price',p['cost_price'] or 0)))
        if not vals[0] or min(vals[2],vals[3],vals[4])<0: raise ValueError
    except (ValueError,TypeError): c.close();return jsonify(success=False,message='Invalid product data.'),400
    c.execute('UPDATE products SET name=?,category=?,quantity=?,price=?,cost_price=? WHERE id=? AND user_id=?',(*vals,pid,uid()));c.commit();c.close();return jsonify(success=True,message='Product updated.')

@app.post('/sales')
@protected
def sales_add():
    d=request.get_json(silent=True) or {}
    try: pid=int(d.get('product_id',0));q=int(d.get('quantity',0)); assert pid>0 and q>0
    except: return jsonify(success=False,message='Product and quantity must be positive integers.'),400
    method=d.get('payment_method','Cash')
    if method not in ('Cash','Card','Wallet'): return jsonify(success=False,message='Invalid payment method.'),400
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE');p=c.execute('SELECT * FROM products WHERE id=? AND user_id=?',(pid,uid())).fetchone()
        if not p: c.rollback();return jsonify(success=False,message='Product not found.'),404
        if p['quantity']<q: c.rollback();return jsonify(success=False,message='Insufficient stock.',available_quantity=p['quantity']),400
        total=round(p['price']*q,2);cur=c.execute('INSERT INTO sales(total_amount,payment_method,user_id) VALUES(?,?,?)',(total,method,uid()));sid=cur.lastrowid
        cost=p['cost_price'] if p['cost_price'] and p['cost_price']>0 else None
        c.execute('INSERT INTO sale_items(sale_id,product_id,quantity,unit_price,unit_cost) VALUES(?,?,?,?,?)',(sid,pid,q,p['price'],cost))
        c.execute('UPDATE products SET quantity=quantity-? WHERE id=? AND user_id=?',(q,pid,uid()))
        c.execute('INSERT INTO stock_movements(product_id,movement_type,quantity_change,reference_id,notes,user_id) VALUES(?,?,?,?,?,?)',(pid,'SALE',-q,sid,f'Sale of {q} unit(s)',uid()));c.commit()
        return jsonify(success=True,sale_id=sid,total_amount=total,remaining_stock=p['quantity']-q,message='Sale recorded.'),201
    except sqlite3.Error: c.rollback();app.logger.exception('Sale error');return jsonify(success=False,message='Could not record sale.'),500
    finally:c.close()
@app.get('/sales')
@protected
def sales_get():
    c=db();rows=c.execute('''SELECT s.id sale_id,s.sale_date,s.total_amount,s.payment_method,si.product_id,p.name product_name,si.quantity,si.unit_price,si.unit_cost FROM sales s JOIN sale_items si ON si.sale_id=s.id JOIN products p ON p.id=si.product_id WHERE s.user_id=? ORDER BY s.id DESC''',(uid(),)).fetchall();c.close();return jsonify(success=True,count=len(rows),sales=[dict(x) for x in rows])

@app.post('/purchases')
@protected
def purchases_add():
    d=request.get_json(silent=True) or {}; supplier=str(d.get('supplier_name','')).strip(); items=d.get('items')
    if not supplier or not isinstance(items,list) or not items:return jsonify(success=False,message='Supplier and purchase items are required.'),400
    try: items=[(int(x['product_id']),int(x['quantity']),float(x['unit_cost'])) for x in items]; assert all(a>0 and b>0 and c>=0 for a,b,c in items)
    except: return jsonify(success=False,message='Invalid purchase item data.'),400
    c=db()
    try:
        c.execute('BEGIN IMMEDIATE'); names=[];total=0
        for pid,q,cost in items:
            p=c.execute('SELECT name FROM products WHERE id=? AND user_id=?',(pid,uid())).fetchone()
            if not p:c.rollback();return jsonify(success=False,message='Product not found.'),404
            names.append((pid,q,cost,p['name']));total+=q*cost
        cur=c.execute('INSERT INTO purchases(supplier_name,total_amount,notes,user_id) VALUES(?,?,?,?)',(supplier,round(total,2),d.get('notes',''),uid()));purid=cur.lastrowid
        for pid,q,cost,name in names:
            c.execute('INSERT INTO purchase_items(purchase_id,product_id,quantity,unit_cost) VALUES(?,?,?,?)',(purid,pid,q,cost))
            c.execute('UPDATE products SET quantity=quantity+?,cost_price=? WHERE id=? AND user_id=?',(q,cost,pid,uid()))
            c.execute('INSERT INTO stock_movements(product_id,movement_type,quantity_change,reference_id,notes,user_id) VALUES(?,?,?,?,?,?)',(pid,'PURCHASE',q,purid,'Purchase from '+supplier,uid()))
        c.commit();return jsonify(success=True,purchase_id=purid,total_amount=round(total,2),message='Purchase recorded.'),201
    except sqlite3.Error:c.rollback();app.logger.exception('Purchase error');return jsonify(success=False,message='Could not record purchase.'),500
    finally:c.close()
@app.get('/purchases')
@protected
def purchases_get():
    c=db();rows=c.execute('''SELECT pu.id purchase_id,pu.purchase_date,pu.supplier_name,pu.total_amount,pu.notes,pi.product_id,p.name product_name,pi.quantity,pi.unit_cost FROM purchases pu JOIN purchase_items pi ON pi.purchase_id=pu.id JOIN products p ON p.id=pi.product_id WHERE pu.user_id=? ORDER BY pu.id DESC''',(uid(),)).fetchall();c.close();return jsonify(success=True,count=len(rows),purchases=[dict(x) for x in rows])
@app.get('/stock-movements')
@protected
def movements_get():
    c=db();rows=c.execute('''SELECT sm.id movement_id,sm.product_id,p.name product_name,sm.movement_type,sm.quantity_change,sm.movement_date,sm.reference_id,sm.notes FROM stock_movements sm JOIN products p ON p.id=sm.product_id WHERE sm.user_id=? ORDER BY sm.id DESC''',(uid(),)).fetchall();c.close();return jsonify(success=True,count=len(rows),movements=[dict(x) for x in rows])

@app.get('/dashboard/stats')
@protected
def dashboard():
    c=db();u=uid();s=c.execute('SELECT COUNT(*) total_products,COALESCE(SUM(quantity),0) total_stock,COALESCE(SUM(CASE WHEN quantity=0 THEN 1 ELSE 0 END),0) out_of_stock,COALESCE(SUM(quantity*price),0) inventory_value FROM products WHERE user_id=?',(u,)).fetchone();o=c.execute('SELECT COUNT(*) total_orders,COALESCE(SUM(total_amount),0) total_revenue FROM sales WHERE user_id=?',(u,)).fetchone();sold=c.execute('SELECT COALESCE(SUM(si.quantity),0) total_sold FROM sale_items si JOIN sales s ON s.id=si.sale_id WHERE s.user_id=?',(u,)).fetchone();recent=c.execute('SELECT id,name,category,quantity,price FROM products WHERE user_id=? ORDER BY id DESC LIMIT 5',(u,)).fetchall();c.close();return jsonify(success=True,total_products=s['total_products'],total_stock=s['total_stock'],out_of_stock=s['out_of_stock'],inventory_value=s['inventory_value'],total_orders=o['total_orders'],total_revenue=o['total_revenue'],total_sold=sold['total_sold'],recent_products=[dict(x) for x in recent])
@app.get('/reports/stats')
@protected
def reports():
    c=db();u=uid();t=c.execute('''SELECT COUNT(DISTINCT s.id) total_orders,COALESCE(SUM(si.quantity*si.unit_price),0) revenue,COALESCE(SUM(CASE WHEN si.unit_cost IS NOT NULL THEN si.quantity*si.unit_cost ELSE 0 END),0) cost,COALESCE(SUM(CASE WHEN si.unit_cost IS NOT NULL THEN si.quantity ELSE 0 END),0) units_cost,COALESCE(SUM(si.quantity),0) units FROM sales s JOIN sale_items si ON si.sale_id=s.id WHERE s.user_id=?''',(u,)).fetchone();m=c.execute('''SELECT strftime('%Y-%m',s.sale_date) month,COUNT(DISTINCT s.id) orders,COALESCE(SUM(si.quantity*si.unit_price),0) revenue,COALESCE(SUM(CASE WHEN si.unit_cost IS NOT NULL THEN si.quantity*si.unit_cost ELSE 0 END),0) cost,COALESCE(SUM(CASE WHEN si.unit_cost IS NOT NULL THEN si.quantity*(si.unit_price-si.unit_cost) ELSE 0 END),0) profit,COALESCE(SUM(CASE WHEN si.unit_cost IS NULL THEN si.quantity ELSE 0 END),0) units_without_cost FROM sales s JOIN sale_items si ON si.sale_id=s.id WHERE s.user_id=? AND date(s.sale_date)>=date('now','start of month','-5 months') GROUP BY month ORDER BY month''',(u,)).fetchall();cm=c.execute("SELECT COUNT(*) FROM sales WHERE user_id=? AND strftime('%Y-%m',sale_date)=strftime('%Y-%m','now')",(u,)).fetchone()[0];c.close();rev=float(t['revenue']);cost=float(t['cost']);profit=rev-cost;return jsonify(success=True,total_orders=t['total_orders'],total_revenue=rev,total_cost=cost,gross_profit=profit,profit_margin=profit/rev*100 if rev else 0,monthly_sales=cm,units_without_cost=int(t['units'])-int(t['units_cost']),monthly_data=[dict(x) for x in m])

if __name__=='__main__': app.run(debug=os.environ.get('FLASK_DEBUG','0')=='1')
