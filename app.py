import os
import io
import sqlite3
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, send_file, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__)
app.secret_key = "change_this_secret_key"


# ========== DB HELPERS ==========

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Users
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    # Products
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            description TEXT
        )
        """
    )

    # Orders
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    # Order items
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price_each REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
        """
    )

    # Create default admin if not exists
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if cur.fetchone() is None:
        admin_pwd = generate_password_hash("admin123")
        cur.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
            ("admin", admin_pwd, 1),
        )

    conn.commit()
    conn.close()

def init_db_once():
    """Initialize DB only once when app starts"""
    init_db()

# Call it immediately after app creation
with app.app_context():
    init_db_once()


# ========== AUTH HELPERS ==========

def current_user():
    if "user_id" not in session:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user = cur.fetchone()
    conn.close()
    return user


def login_required(view_func):
    from functools import wraps

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped


def admin_required(view_func):
    from functools import wraps

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user["is_admin"] != 1:
            flash("Admin access required", "error")
            return redirect(url_for("index"))
        return view_func(*args, **kwargs)

    return wrapped


# ========== ROUTES: BASIC ==========

@app.route("/")
def index():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if user["is_admin"]:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))


import re

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        is_admin = 1 if request.form.get("is_admin") == "on" else 0

        # ---------- VALIDATIONS ----------

        # Empty fields
        if not username or not password:
            flash("All fields are required!", "error")
            return redirect(url_for("signup"))

        # Username length
        if len(username) < 3:
            flash("Username must be at least 3 characters!", "error")
            return redirect(url_for("signup"))

        # Password length
        if len(password) < 6:
            flash("Password must be at least 6 characters!", "error")
            return redirect(url_for("signup"))

        # Password strength (must contain number)
        if not re.search(r"\d", password):
            flash("Password must contain at least one number!", "error")
            return redirect(url_for("signup"))

        # ---------- DATABASE CHECK ----------

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE username=?", (username,))
        if cur.fetchone():
            conn.close()
            flash("Username already exists!", "error")
            return redirect(url_for("signup"))

        # ---------- SAVE USER ----------

        pwd_hash = generate_password_hash(password)

        cur.execute("""
            INSERT INTO users (username, password_hash, is_admin)
            VALUES (?, ?, ?)
        """, (username, pwd_hash, is_admin))

        conn.commit()
        conn.close()

        flash("Signup successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session.setdefault("cart", {})
            flash("Logged in successfully", "success")
            if user["is_admin"]:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("user_dashboard"))
        else:
            flash("Invalid username or password", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "success")
    return redirect(url_for("login"))


# ========== ROUTES: DASHBOARDS ==========

@app.route("/user/dashboard")
@login_required
def user_dashboard():
    user = current_user()
    if user["is_admin"]:
        return redirect(url_for("admin_dashboard"))
    return render_template("user.html", user=user)


@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    user = current_user()
    return render_template("admin.html", user=user)


# ========== ROUTES: PRODUCTS (USER) ==========

@app.route("/products")
@login_required
def products():
    conn = get_db()
    cur = conn.cursor()

    search = request.args.get("search", "").strip()
    if search:
        cur.execute(
            "SELECT * FROM products WHERE name LIKE ? OR category LIKE ?",
            (f"%{search}%", f"%{search}%"),
        )
    else:
        cur.execute("SELECT * FROM products")

    products_list = cur.fetchall()
    conn.close()
    return render_template("products.html", products=products_list)


@app.route("/add_to_cart/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    quantity = int(request.form.get("quantity", 1))
    if quantity <= 0:
        flash("Quantity must be at least 1", "error")
        return redirect(url_for("products"))

    # Update session cart
    cart = session.get("cart", {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + quantity
    session["cart"] = cart
    flash("Product added to cart", "success")
    return redirect(url_for("products"))


@app.route("/cart")
@login_required
def view_cart():
    cart = session.get("cart", {})
    if not cart:
        return render_template("cart.html", items=[], total=0)

    conn = get_db()
    cur = conn.cursor()

    product_ids = [int(pid) for pid in cart.keys()]
    placeholders = ",".join("?" for _ in product_ids)
    cur.execute(
        f"SELECT * FROM products WHERE id IN ({placeholders})", product_ids
    )
    products = cur.fetchall()
    conn.close()

    items = []
    total = 0
    for p in products:
        qty = cart.get(str(p["id"]), 0)
        line_total = p["price"] * qty
        total += line_total
        items.append(
            {
                "id": p["id"],
                "name": p["name"],
                "price": p["price"],
                "quantity": qty,
                "line_total": line_total,
            }
        )

    return render_template("cart.html", items=items, total=total)


@app.route("/remove_from_cart/<int:product_id>", methods=["POST"])
@login_required
def remove_from_cart(product_id):
    cart = session.get("cart", {})
    cart.pop(str(product_id), None)
    session["cart"] = cart
    flash("Item removed from cart", "success")
    return redirect(url_for("view_cart"))


@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Cart is empty", "error")
        return redirect(url_for("view_cart"))

    user = current_user()
    conn = get_db()
    cur = conn.cursor()

    # Fetch all products in cart
    product_ids = [int(pid) for pid in cart.keys()]
    placeholders = ",".join("?" for _ in product_ids)
    cur.execute(
        f"SELECT * FROM products WHERE id IN ({placeholders})", product_ids
    )
    products = cur.fetchall()

    # Check stock and calculate total
    total = 0
    for p in products:
        pid_str = str(p["id"])
        qty = cart.get(pid_str, 0)
        if qty > p["stock"]:
            conn.close()
            flash(f"Not enough stock for {p['name']}", "error")
            return redirect(url_for("view_cart"))
        total += p["price"] * qty

    # Create order
    created_at = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO orders (user_id, total_amount, created_at) VALUES (?, ?, ?)",
        (user["id"], total, created_at),
    )
    order_id = cur.lastrowid

    # Create order items + reduce stock
    for p in products:
        pid_str = str(p["id"])
        qty = cart.get(pid_str, 0)
        if qty <= 0:
            continue
        cur.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, price_each) VALUES (?, ?, ?, ?)",
            (order_id, p["id"], qty, p["price"]),
        )
        cur.execute(
            "UPDATE products SET stock = stock - ? WHERE id = ?",
            (qty, p["id"]),
        )

    conn.commit()
    conn.close()

    # Clear cart
    session["cart"] = {}
    flash("Purchase successful!", "success")
    return render_template("checkout_success.html", order_id=order_id, total=total)


# ========== ROUTES: ADMIN PRODUCTS ==========

@app.route("/admin/products")
@login_required
@admin_required
def admin_products():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    products_list = cur.fetchall()
    conn.close()
    return render_template("admin_products.html", products=products_list)


@app.route("/admin/products/add", methods=["GET", "POST"])
@login_required
@admin_required
def admin_add_product():
    if request.method == "POST":
        name = request.form.get("name").strip()
        category = request.form.get("category").strip()
        price = float(request.form.get("price", 0))
        stock = int(request.form.get("stock", 0))
        description = request.form.get("description", "").strip()

        if not name or price <= 0:
            flash("Name and positive price required", "error")
            return redirect(url_for("admin_add_product"))

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO products (name, category, price, stock, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, category, price, stock, description),
        )
        conn.commit()
        conn.close()
        flash("Product added", "success")
        return redirect(url_for("admin_products"))

    return render_template("admin_add_product.html")


@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_product(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cur.fetchone()

    if not product:
        conn.close()
        flash("Product not found", "error")
        return redirect(url_for("admin_products"))

    if request.method == "POST":
        name = request.form.get("name").strip()
        category = request.form.get("category").strip()
        price = float(request.form.get("price", 0))
        stock = int(request.form.get("stock", 0))
        description = request.form.get("description", "").strip()

        cur.execute(
            """
            UPDATE products
            SET name = ?, category = ?, price = ?, stock = ?, description = ?
            WHERE id = ?
            """,
            (name, category, price, stock, description, product_id),
        )
        conn.commit()
        conn.close()
        flash("Product updated", "success")
        return redirect(url_for("admin_products"))

    conn.close()
    return render_template("admin_edit_product.html", product=product)


@app.route("/admin/products/<int:product_id>/stock_in", methods=["GET", "POST"])
@login_required
@admin_required
def admin_stock_in(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cur.fetchone()

    if not product:
        conn.close()
        flash("Product not found", "error")
        return redirect(url_for("admin_products"))

    if request.method == "POST":
        qty = int(request.form.get("quantity", 0))
        if qty <= 0:
            flash("Quantity must be > 0", "error")
        else:
            cur.execute(
                "UPDATE products SET stock = stock + ? WHERE id = ?",
                (qty, product_id),
            )
            conn.commit()
            flash("Stock increased", "success")
            conn.close()
            return redirect(url_for("admin_products"))

    conn.close()
    return render_template("admin_stock_in.html", product=product)


@app.route("/admin/products/<int:product_id>/stock_out", methods=["GET", "POST"])
@login_required
@admin_required
def admin_stock_out(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cur.fetchone()

    if not product:
        conn.close()
        flash("Product not found", "error")
        return redirect(url_for("admin_products"))

    if request.method == "POST":
        qty = int(request.form.get("quantity", 0))
        if qty <= 0:
            flash("Quantity must be > 0", "error")
        elif qty > product["stock"]:
            flash("Cannot stock-out more than available stock", "error")
        else:
            cur.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (qty, product_id),
            )
            conn.commit()
            flash("Stock decreased", "success")
            conn.close()
            return redirect(url_for("admin_products"))

    conn.close()
    return render_template("admin_stock_out.html", product=product)


# ========== ROUTES: INVOICE (PDF) ==========

@app.route("/invoice/<int:order_id>")
@login_required
def invoice(order_id):
    user = current_user()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user["id"]))
    order = cur.fetchone()
    if not order:
        conn.close()
        flash("Order not found", "error")
        return redirect(url_for("user_dashboard"))

    cur.execute(
        """
        SELECT oi.*, p.name
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        """,
        (order_id,),
    )
    items = cur.fetchall()
    conn.close()

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y, "Invoice")
    y -= 30

    p.setFont("Helvetica", 10)
    p.drawString(50, y, f"Order ID: {order['id']}")
    y -= 15
    p.drawString(50, y, f"User: {user['username']}")
    y -= 15
    p.drawString(50, y, f"Date: {order['created_at']}")
    y -= 30

    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Product")
    p.drawString(250, y, "Quantity")
    p.drawString(320, y, "Price")
    p.drawString(400, y, "Total")
    y -= 20

    p.setFont("Helvetica", 10)
    for item in items:
        line_total = item["quantity"] * item["price_each"]
        p.drawString(50, y, item["name"])
        p.drawString(250, y, str(item["quantity"]))
        p.drawString(320, y, f"{item['price_each']:.2f}")
        p.drawString(400, y, f"{line_total:.2f}")
        y -= 15
        if y < 50:
            p.showPage()
            y = height - 50

    y -= 20
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y, f"Total Amount: {order['total_amount']:.2f}")

    p.showPage()
    p.save()

    buffer.seek(0)
    filename = f"invoice_{order_id}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )


# ========== ROUTES: QR PAYMENT GENERATION & SCAN PAGE ==========

@app.route("/payment_qr/<int:order_id>")
@login_required
def payment_qr(order_id):
    user = current_user()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user["id"]))
    order = cur.fetchone()
    conn.close()

    if not order:
        flash("Order not found", "error")
        return redirect(url_for("user_dashboard"))

    # Simple payment text (could be UPI / bank string in real project)
    qr_text = f"PAYMENT|ORDER={order['id']}|USER={user['username']}|AMOUNT={order['total_amount']}"
    img = qrcode.make(qr_text)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return send_file(buffer, mimetype="image/png")




from datetime import datetime, timedelta

@app.route("/admin/user_purchases")
@login_required
@admin_required
def admin_user_purchases():
    conn = get_db()
    cur = conn.cursor()

    # last 30 days date
    last_month = (datetime.utcnow() - timedelta(days=30)).isoformat()

    cur.execute("""
        SELECT 
            u.username,
            p.name AS product_name,
            oi.quantity,
            o.created_at
        FROM orders o
        JOIN users u ON u.id = o.user_id
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        WHERE o.created_at >= ?
        ORDER BY o.created_at DESC
    """, (last_month,))

    data = cur.fetchall()
    conn.close()

    return render_template("admin_user_purchases.html", data=data)


# ========== MAIN ==========

if __name__ == "__main__":
    app.run(debug=True)
