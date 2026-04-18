# BillZap - Cloud Billing App v2
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import random, string, os
import stripe
stripe.api_key = 'sk_test_51TNXTaJB7ze9VgSgonG2TAxTMJIw6M0YFDKiwKAZu8MlK1cYj1ckBLgalgWlsR0kiGBkLGBExLXmekmO8CMuexmY003Bez9qXb'

app = Flask(__name__)

# Use /home for persistent storage on Azure
db_path = os.path.join('/home', 'billing.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SECRET_KEY'] = 'billing-secret-key'
db = SQLAlchemy(app)

class Plan(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(100), nullable=False)
    price     = db.Column(db.Float, nullable=False)
    interval  = db.Column(db.String(20), default='monthly')
    features  = db.Column(db.String(500))
    customers = db.relationship('Customer', backref='plan', lazy=True)

class Customer(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    email    = db.Column(db.String(120), unique=True, nullable=False)
    plan_id  = db.Column(db.Integer, db.ForeignKey('plan.id'))
    status   = db.Column(db.String(20), default='active')
    joined   = db.Column(db.DateTime, default=datetime.utcnow)
    invoices = db.relationship('Invoice', backref='customer', lazy=True)

class Invoice(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    invoice_no  = db.Column(db.String(20), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    amount      = db.Column(db.Float, nullable=False)
    status      = db.Column(db.String(20), default='pending')
    issued_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date    = db.Column(db.DateTime)
    paid_date   = db.Column(db.DateTime)

with app.app_context():
    db.create_all()

@app.route('/')
def dashboard():
    customers = Customer.query.all()
    invoices  = Invoice.query.all()
    plans     = Plan.query.all()
    total_rev = sum(i.amount for i in invoices if i.status == 'paid')
    pending   = sum(i.amount for i in invoices if i.status == 'pending')
    return render_template('dashboard.html',
        customers=customers, invoices=invoices,
        plans=plans, total_rev=total_rev, pending=pending)

@app.route('/plans', methods=['GET','POST'])
def plans():
    if request.method == 'POST':
        p = Plan(name=request.form['name'],
                 price=float(request.form['price']),
                 interval=request.form['interval'],
                 features=request.form['features'])
        db.session.add(p); db.session.commit()
        return redirect(url_for('plans'))
    return render_template('plans.html', plans=Plan.query.all())

@app.route('/customers', methods=['GET','POST'])
def customers():
    if request.method == 'POST':
        c = Customer(name=request.form['name'],
                     email=request.form['email'],
                     plan_id=int(request.form['plan_id']))
        db.session.add(c); db.session.commit()
        return redirect(url_for('customers'))
    return render_template('customers.html',
        customers=Customer.query.all(), plans=Plan.query.all())

@app.route('/billing', methods=['GET','POST'])
def billing():
    if request.method == 'POST':
        cid = int(request.form['customer_id'])
        c   = Customer.query.get(cid)
        inv = Invoice(
            invoice_no  = 'INV-' + ''.join(random.choices(string.digits, k=6)),
            customer_id = cid,
            amount      = c.plan.price,
            status      = 'pending',
            due_date    = datetime.utcnow() + timedelta(days=30))
        db.session.add(inv); db.session.commit()
        return redirect(url_for('billing'))
    return render_template('billing.html',
        invoices=Invoice.query.order_by(Invoice.issued_date.desc()).all(),
        customers=Customer.query.filter_by(status='active').all())

@app.route('/pay/<int:inv_id>')
def pay_invoice(inv_id):
    inv = Invoice.query.get_or_404(inv_id)
    inv.status    = 'paid'
    inv.paid_date = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('billing'))

@app.route('/reports')
def reports():
    invoices  = Invoice.query.all()
    customers = Customer.query.all()
    plans     = Plan.query.all()
    monthly   = {}
    for inv in invoices:
        key = inv.issued_date.strftime('%b %Y')
        monthly[key] = monthly.get(key, 0) + (inv.amount if inv.status=='paid' else 0)
    return render_template('reports.html',
        invoices=invoices, customers=customers,
        plans=plans, monthly=monthly)

@app.route('/seed')
def seed():
    db.drop_all(); db.create_all()
    plans = [
        Plan(name='Starter',    price=9.99,  interval='monthly', features='5 users, 10GB storage, Email support'),
        Plan(name='Pro',        price=29.99, interval='monthly', features='25 users, 100GB storage, Priority support'),
        Plan(name='Enterprise', price=99.99, interval='monthly', features='Unlimited users, 1TB storage, 24/7 support'),
    ]
    db.session.add_all(plans); db.session.flush()
    customers = [
        Customer(name='Alice Johnson', email='alice@example.com', plan_id=plans[0].id),
        Customer(name='Bob Smith',     email='bob@example.com',   plan_id=plans[1].id),
        Customer(name='Carol White',   email='carol@example.com', plan_id=plans[2].id),
        Customer(name='David Lee',     email='david@example.com', plan_id=plans[1].id),
    ]
    db.session.add_all(customers); db.session.flush()
    for c in customers:
        for i in range(3):
            inv = Invoice(
                invoice_no  = 'INV-' + ''.join(random.choices(string.digits, k=6)),
                customer_id = c.id,
                amount      = c.plan.price,
                status      = random.choice(['paid','paid','pending']),
                issued_date = datetime.utcnow() - timedelta(days=30*i),
                due_date    = datetime.utcnow() - timedelta(days=30*i - 30))
            if inv.status == 'paid':
                inv.paid_date = inv.issued_date + timedelta(days=random.randint(1,10))
            db.session.add(inv)
    db.session.commit()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
