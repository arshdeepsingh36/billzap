# BillZap - Cloud Billing App v4
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random, string, os, functools
import stripe

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.ckkdeanetcbobirktpgt:YOURPASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres'
app.config['SECRET_KEY'] = 'billzap-secret-key-2026'
db = SQLAlchemy(app)
stripe.api_key = 'sk_test_51TNXTaJB7ze9VgSgonG2TAxTMJIw6M0YFDKiwKAZu8MlK1cYj1ckBLgalgWlsR0kiGBkLGBExLXmekmO8CMuexmY003Bez9qXb'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'customer_login'

def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def customer_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('customer_login'))
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated

class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), default='customer')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

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
    try:
        db.create_all()
        if not User.query.filter_by(email='admin@billzap.com').first():
            admin = User(
                name          = 'BillZap Admin',
                email         = 'admin@billzap.com',
                password_hash = generate_password_hash('Admin@1234'),
                role          = 'admin'
            )
            db.session.add(admin)
            db.session.commit()
    except Exception as e:
        print(f"Startup error: {e}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ── Public ────────────────────────────────────────────────────
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('customer_dashboard'))
    plans = Plan.query.all()
    return render_template('index.html', plans=plans)

# ── Admin Auth ────────────────────────────────────────────────
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        user     = User.query.filter_by(email=email, role='admin').first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('Invalid admin credentials', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))

# ── Admin Routes ──────────────────────────────────────────────
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    customers = Customer.query.all()
    invoices  = Invoice.query.all()
    plans     = Plan.query.all()
    total_rev = sum(i.amount for i in invoices if i.status == 'paid')
    pending   = sum(i.amount for i in invoices if i.status == 'pending')
    users     = User.query.filter_by(role='customer').all()
    return render_template('dashboard.html',
        customers=customers, invoices=invoices, users=users,
        plans=plans, total_rev=total_rev, pending=pending)

@app.route('/admin/plans', methods=['GET', 'POST'])
@admin_required
def plans():
    if request.method == 'POST':
        p = Plan(
            name     = request.form['name'],
            price    = float(request.form['price']),
            interval = request.form['interval'],
            features = request.form['features'])
        db.session.add(p); db.session.commit()
        return redirect(url_for('plans'))
    return render_template('plans.html', plans=Plan.query.all())

@app.route('/admin/customers', methods=['GET', 'POST'])
@admin_required
def customers():
    if request.method == 'POST':
        c = Customer(
            name    = request.form['name'],
            email   = request.form['email'],
            plan_id = int(request.form['plan_id']))
        db.session.add(c); db.session.commit()
        return redirect(url_for('customers'))
    return render_template('customers.html',
        customers=Customer.query.all(), plans=Plan.query.all())

@app.route('/admin/billing', methods=['GET', 'POST'])
@admin_required
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

@app.route('/admin/reports')
@admin_required
def reports():
    invoices  = Invoice.query.all()
    customers = Customer.query.all()
    plans     = Plan.query.all()
    monthly   = {}
    for inv in invoices:
        key = inv.issued_date.strftime('%b %Y')
        monthly[key] = monthly.get(key, 0) + (inv.amount if inv.status == 'paid' else 0)
    return render_template('reports.html',
        invoices=invoices, customers=customers,
        plans=plans, monthly=monthly)

@app.route('/admin/pay/<int:inv_id>')
@admin_required
def pay_invoice(inv_id):
    inv           = Invoice.query.get_or_404(inv_id)
    inv.status    = 'paid'
    inv.paid_date = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('billing'))

# ── Customer Auth ─────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def customer_login():
    if current_user.is_authenticated and current_user.role == 'customer':
        return redirect(url_for('customer_dashboard'))
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        user     = User.query.filter_by(email=email, role='customer').first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('customer_dashboard'))
        flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name     = request.form['name']
        email    = request.form['email']
        password = request.form['password']
        plan_id  = request.form.get('plan_id')
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        user = User(
            name          = name,
            email         = email,
            password_hash = generate_password_hash(password),
            role          = 'customer'
        )
        db.session.add(user)
        db.session.flush()
        customer = None
        if not Customer.query.filter_by(email=email).first():
            customer = Customer(
                name    = name,
                email   = email,
                plan_id = int(plan_id) if plan_id else None
            )
            db.session.add(customer)
            db.session.flush()
        db.session.commit()
        customer = Customer.query.filter_by(email=email).first()
        if customer and customer.plan_id:
            inv = Invoice(
                invoice_no  = 'INV-' + ''.join(random.choices(string.digits, k=6)),
                customer_id = customer.id,
                amount      = customer.plan.price,
                status      = 'pending',
                due_date    = datetime.utcnow() + timedelta(days=30)
            )
            db.session.add(inv)
            db.session.commit()
        login_user(user)
        flash('Account created! Please complete your payment to access your dashboard.', 'success')
        return redirect(url_for('payment_required'))
    plans = Plan.query.all()
    return render_template('register.html', plans=plans)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

# ── Customer Routes ───────────────────────────────────────────
@app.route('/payment-required')
@customer_required
def payment_required():
    customer = Customer.query.filter_by(email=current_user.email).first()
    invoices = Invoice.query.filter_by(
        customer_id=customer.id,
        status='pending').all() if customer else []
    return render_template('payment_required.html',
        customer=customer, invoices=invoices, user=current_user)

@app.route('/my-dashboard')
@customer_required
def customer_dashboard():
    customer = Customer.query.filter_by(email=current_user.email).first()
    if not customer:
        return redirect(url_for('logout'))
    invoices         = Invoice.query.filter_by(customer_id=customer.id).order_by(Invoice.issued_date.desc()).all()
    pending_invoices = [i for i in invoices if i.status == 'pending']
    paid_invoices    = [i for i in invoices if i.status == 'paid']
    if not paid_invoices and pending_invoices:
        return redirect(url_for('payment_required'))
    return render_template('customer_dashboard.html',
        customer=customer, invoices=invoices,
        pending_invoices=pending_invoices, user=current_user)

@app.route('/my-invoices')
@customer_required
def my_invoices():
    customer = Customer.query.filter_by(email=current_user.email).first()
    invoices = Invoice.query.filter_by(
        customer_id=customer.id).order_by(
        Invoice.issued_date.desc()).all() if customer else []
    return render_template('my_invoices.html',
        invoices=invoices, customer=customer)

@app.route('/content')
@customer_required
def content():
    customer = Customer.query.filter_by(email=current_user.email).first()
    if not customer:
        return redirect(url_for('logout'))
    invoices  = Invoice.query.filter_by(customer_id=customer.id).all()
    paid      = any(i.status == 'paid' for i in invoices)
    if not paid:
        return redirect(url_for('payment_required'))
    plan_name = customer.plan.name if customer.plan else 'Starter'
    all_plans = Plan.query.all()
    next_plan = None
    for i, p in enumerate(sorted(all_plans, key=lambda x: x.price)):
        if customer.plan and p.id == customer.plan.id and i + 1 < len(all_plans):
            next_plan = sorted(all_plans, key=lambda x: x.price)[i + 1]
    return render_template('content.html',
        customer=customer, plan_name=plan_name,
        next_plan=next_plan, user=current_user)

@app.route('/upgrade/<int:plan_id>')
@customer_required
def upgrade(plan_id):
    customer  = Customer.query.filter_by(email=current_user.email).first()
    new_plan  = Plan.query.get_or_404(plan_id)
    if customer:
        customer.plan_id = plan_id
        inv = Invoice(
            invoice_no  = 'INV-' + ''.join(random.choices(string.digits, k=6)),
            customer_id = customer.id,
            amount      = new_plan.price,
            status      = 'pending',
            due_date    = datetime.utcnow() + timedelta(days=30)
        )
        db.session.add(inv)
        db.session.commit()
        flash(f'Upgraded to {new_plan.name}! Please complete payment.', 'success')
    return redirect(url_for('payment_required'))

@app.route('/checkout/<int:inv_id>')
@customer_required
def checkout(inv_id):
    inv            = Invoice.query.get_or_404(inv_id)
    stripe_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': f'Invoice {inv.invoice_no} - {inv.customer.name}',
                },
                'unit_amount': int(inv.amount * 100),
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=request.host_url + f'pay/{inv_id}',
        cancel_url=request.host_url + 'payment-required',
    )
    return redirect(stripe_session.url)

@app.route('/pay/<int:inv_id>')
@login_required
def pay_success(inv_id):
    inv           = Invoice.query.get_or_404(inv_id)
    inv.status    = 'paid'
    inv.paid_date = datetime.utcnow()
    db.session.commit()
    flash('Payment successful! Welcome to BillZap!', 'success')
    return redirect(url_for('customer_dashboard'))

# ── Seed ──────────────────────────────────────────────────────
@app.route('/seed')
def seed():
    db.drop_all(); db.create_all()
    admin = User(
        name          = 'BillZap Admin',
        email         = 'admin@billzap.com',
        password_hash = generate_password_hash('Admin@1234'),
        role          = 'admin'
    )
    db.session.add(admin)
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
        user = User(
            name          = c.name,
            email         = c.email,
            password_hash = generate_password_hash('Test@1234'),
            role          = 'customer'
        )
        db.session.add(user)
        for i in range(3):
            inv = Invoice(
                invoice_no  = 'INV-' + ''.join(random.choices(string.digits, k=6)),
                customer_id = c.id,
                amount      = c.plan.price,
                status      = random.choice(['paid', 'paid', 'pending']),
                issued_date = datetime.utcnow() - timedelta(days=30*i),
                due_date    = datetime.utcnow() - timedelta(days=30*i - 30))
            if inv.status == 'paid':
                inv.paid_date = inv.issued_date + timedelta(days=random.randint(1, 10))
            db.session.add(inv)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
