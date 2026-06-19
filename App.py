from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv
import os

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__)

# ---------------------- DATABASE CONFIG ----------------------
# Set the DATABASE_URL environment variable to your Supabase Postgres
# connection string to use Supabase. Example:
#   postgresql://postgres:[email protected]:5432/postgres
#
# If DATABASE_URL is not set, the app falls back to a local SQLite file
# (expenses.db) so it keeps working without any extra setup.
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # SQLAlchemy + psycopg2 require the "postgresql://" scheme (not "postgres://")
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'expenses.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ---------------------- MODELS ----------------------

class HousingInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    monthly_rent = db.Column(db.Float, default=0.0)
    security_advance = db.Column(db.Float, default=0.0)


class RentPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.String(7), nullable=False)   # format: YYYY-MM
    paid_on = db.Column(db.String(10), nullable=False)  # format: YYYY-MM-DD
    amount = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "month": self.month,
            "paid_on": self.paid_on,
            "amount": self.amount
        }


class Day(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_number = db.Column(db.Integer, unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    items = db.relationship('ExpenseItem', backref='day', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "day_number": self.day_number,
            "completed": self.completed,
            "items": [item.to_dict() for item in self.items],
            "total": sum(item.amount for item in self.items)
        }


class ExpenseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey('day.id'), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "item_name": self.item_name,
            "amount": self.amount
        }


# ---------------------- ROUTES ----------------------

@app.route('/')
def index():
    return render_template('index.html')


# ---- Housing Info ----

@app.route('/api/housing', methods=['GET'])
def get_housing():
    housing = HousingInfo.query.first()
    payments = RentPayment.query.order_by(RentPayment.month.asc()).all()

    monthly_rent = housing.monthly_rent if housing else 0
    security_advance = housing.security_advance if housing else 0

    return jsonify({
        "monthly_rent": monthly_rent,
        "security_advance": security_advance,
        "payments": [p.to_dict() for p in payments]
    })


@app.route('/api/housing', methods=['POST'])
def save_housing():
    data = request.get_json()
    monthly_rent = float(data.get('monthly_rent', 0) or 0)
    security_advance = float(data.get('security_advance', 0) or 0)

    housing = HousingInfo.query.first()
    if not housing:
        housing = HousingInfo(monthly_rent=monthly_rent, security_advance=security_advance)
        db.session.add(housing)
    else:
        housing.monthly_rent = monthly_rent
        housing.security_advance = security_advance

    db.session.commit()

    payments = RentPayment.query.order_by(RentPayment.month.asc()).all()

    return jsonify({
        "monthly_rent": housing.monthly_rent,
        "security_advance": housing.security_advance,
        "payments": [p.to_dict() for p in payments]
    })


@app.route('/api/housing/payments', methods=['POST'])
def add_rent_payment():
    data = request.get_json()
    month = (data.get('month') or '').strip()       # expected "YYYY-MM"
    paid_on = (data.get('paid_on') or '').strip()   # expected "YYYY-MM-DD"

    if not month or not paid_on:
        return jsonify({"error": "month and paid_on are required"}), 400

    housing = HousingInfo.query.first()
    if not housing:
        return jsonify({"error": "Please save housing details (monthly rent) first"}), 400

    existing = RentPayment.query.filter_by(month=month).first()
    if existing:
        return jsonify({"error": f"A payment for {month} already exists"}), 400

    payment = RentPayment(month=month, paid_on=paid_on, amount=housing.monthly_rent)
    db.session.add(payment)
    db.session.commit()

    payments = RentPayment.query.order_by(RentPayment.month.asc()).all()

    return jsonify({
        "monthly_rent": housing.monthly_rent,
        "security_advance": housing.security_advance,
        "payments": [p.to_dict() for p in payments]
    }), 201


@app.route('/api/housing/payments/<int:payment_id>', methods=['DELETE'])
def delete_rent_payment(payment_id):
    payment = RentPayment.query.get_or_404(payment_id)
    db.session.delete(payment)
    db.session.commit()

    housing = HousingInfo.query.first()
    payments = RentPayment.query.order_by(RentPayment.month.asc()).all()

    return jsonify({
        "monthly_rent": housing.monthly_rent if housing else 0,
        "security_advance": housing.security_advance if housing else 0,
        "payments": [p.to_dict() for p in payments]
    })


# ---- Days & Daily Expenses ----

@app.route('/api/days', methods=['GET'])
def get_days():
    days = Day.query.order_by(Day.day_number.asc()).all()

    if not days:
        # Auto-create Day 1 if nothing exists yet
        day1 = Day(day_number=1)
        db.session.add(day1)
        db.session.commit()
        days = [day1]

    return jsonify([day.to_dict() for day in days])


@app.route('/api/days/<int:day_id>', methods=['DELETE'])
def delete_day(day_id):
    day = Day.query.get_or_404(day_id)
    db.session.delete(day)
    db.session.commit()

    # Re-number remaining days sequentially
    remaining = Day.query.order_by(Day.day_number.asc()).all()
    for i, d in enumerate(remaining, start=1):
        d.day_number = i
    db.session.commit()

    return jsonify([d.to_dict() for d in remaining])


@app.route('/api/days', methods=['POST'])
def add_day():
    last_day = Day.query.order_by(Day.day_number.desc()).first()
    new_day_number = (last_day.day_number + 1) if last_day else 1

    new_day = Day(day_number=new_day_number)
    db.session.add(new_day)
    db.session.commit()

    return jsonify(new_day.to_dict()), 201


@app.route('/api/days/<int:day_id>/items', methods=['POST'])
def add_item(day_id):
    day = Day.query.get_or_404(day_id)
    data = request.get_json()

    item_name = (data.get('item_name') or '').strip()
    amount = data.get('amount')

    if not item_name or amount is None:
        return jsonify({"error": "item_name and amount are required"}), 400

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "amount must be a number"}), 400

    new_item = ExpenseItem(day_id=day.id, item_name=item_name, amount=amount)
    db.session.add(new_item)
    db.session.commit()

    return jsonify(day.to_dict()), 201


@app.route('/api/days/<int:day_id>', methods=['DELETE'])
def delete_day(day_id):
    day = Day.query.get_or_404(day_id)
    db.session.delete(day)
    db.session.commit()
    return jsonify({"success": True})


@app.route('/api/days/<int:day_id>/toggle-complete', methods=['POST'])
def toggle_day_complete(day_id):
    day = Day.query.get_or_404(day_id)
    day.completed = not day.completed
    db.session.commit()
    return jsonify(day.to_dict())


@app.route('/api/items/<int:item_id>', methods=['PUT'])
def edit_item(item_id):
    item = ExpenseItem.query.get_or_404(item_id)
    data = request.get_json()

    item_name = (data.get('item_name') or '').strip()
    amount = data.get('amount')

    if not item_name or amount is None:
        return jsonify({"error": "item_name and amount are required"}), 400

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "amount must be a number"}), 400

    item.item_name = item_name
    item.amount = amount
    db.session.commit()

    return jsonify(item.day.to_dict())


@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    item = ExpenseItem.query.get_or_404(item_id)
    day = item.day
    db.session.delete(item)
    db.session.commit()
    return jsonify(day.to_dict())


@app.route('/api/summary', methods=['GET'])
def get_summary():
    housing = HousingInfo.query.first()
    days = Day.query.all()
    payments = RentPayment.query.all()

    total_daily_expenses = sum(
        item.amount for day in days for item in day.items
    )

    monthly_rent = housing.monthly_rent if housing else 0
    security_advance = housing.security_advance if housing else 0
    months_paid = len(payments)

    total_rent_paid = sum(p.amount for p in payments)
    total_paid_till_date = security_advance + total_rent_paid

    return jsonify({
        "monthly_rent": monthly_rent,
        "security_advance": security_advance,
        "months_paid": months_paid,
        "total_paid_till_date": total_paid_till_date,
        "total_daily_expenses": total_daily_expenses,
        "grand_total": total_paid_till_date + total_daily_expenses
    })


# ---------------------- MAIN ----------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)