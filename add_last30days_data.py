import sqlite3
import random
from datetime import datetime, timedelta

DB = "database.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# -----------------------------
# GET USERS
# -----------------------------
cur.execute("SELECT id FROM users WHERE is_admin = 0")
users = [u[0] for u in cur.fetchall()]

if not users:
    print("❌ No users found. Create users first.")
    exit()

# -----------------------------
# GET PRODUCTS
# -----------------------------
cur.execute("SELECT id, price FROM products")
products = cur.fetchall()

if not products:
    print("❌ No products found. Add products first.")
    exit()

print("Adding last 30 days purchase data...")

# -----------------------------
# INSERT ORDERS FOR LAST 30 DAYS
# -----------------------------
for day in range(30):

    date = datetime.utcnow() - timedelta(days=day)

    # create 5–10 orders per day
    for _ in range(random.randint(5, 10)):

        user_id = random.choice(users)

        cur.execute("""
        INSERT INTO orders (user_id, total_amount, created_at)
        VALUES (?, ?, ?)
        """, (user_id, 0, date.isoformat()))

        order_id = cur.lastrowid

        total = 0

        # each order contains 1–4 items
        for _ in range(random.randint(1, 4)):
            pid, price = random.choice(products)
            qty = random.randint(1, 5)

            cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, price_each)
            VALUES (?, ?, ?, ?)
            """, (order_id, pid, qty, price))

            total += price * qty

        # update order total
        cur.execute("""
        UPDATE orders SET total_amount = ? WHERE id = ?
        """, (total, order_id))

conn.commit()
conn.close()

print("✅ SUCCESS! Last 30 days purchase data added.")
