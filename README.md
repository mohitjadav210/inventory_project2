# 📦 Inventory Management System

A web-based inventory management system built with **Flask** and **SQLite**.

## Features

- 🔐 User authentication (login / signup)
- 🛒 Product browsing, search, cart & checkout
- 📦 Admin: add, edit, stock-in / stock-out products
- 🧾 PDF invoice generation per order
- 📱 QR code payment generation
- 📊 Admin view of user purchases (last 30 days)

## Tech Stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Frontend:** HTML, CSS (Jinja2 templates)
- **Libraries:** ReportLab (PDF), qrcode (QR)

## Setup & Run

```bash
# 1. Clone the repo
git clone https://github.com/your-username/inventory_project2.git
cd inventory_project2

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Seed sample products
python seeds.py

# 5. Run the app
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

## Default Admin Login

| Username | Password |
|----------|----------|
| `admin`  | `admin123` |

## Project Structure

```
inventory_project2/
├── app.py              # Main Flask application
├── seeds.py            # Sample product data seeder
├── add_last30days_data.py  # Demo order data generator
├── requirements.txt    # Python dependencies
├── static/
│   └── css/style.css
└── templates/          # HTML templates
```

