import os
from urllib.parse import urlparse

from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from pymysql.cursors import DictCursor

app = Flask(__name__)
CORS(app)

def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set")

    url = urlparse(database_url)

    return pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database="Jenny_Morgan_CRM",      
        port=url.port,
        cursorclass=DictCursor,
        autocommit=True
    )

def clear_results(cur):
    while cur.nextset():
        pass

# ====================== ROOT ROUTE (fixes WeWeb 404) ======================
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "message": "Furniture CRM API is running ✅",
        "available_endpoints": [
            "/health", "/products", "/auth/login",
            "/customers/<id>", "/customers/<id>/orders", "/customers/<id>/reviews",
            "/reviews (POST)", "/reviews/<id> (DELETE)"
        ]
    }), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200

@app.route("/products", methods=["GET"])
def get_products():
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM catalog_summary ORDER BY item_name")
        rows = cur.fetchall()
        return jsonify(rows), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    account_type = data.get("account_type", "").strip().lower()

    if not email or not password or account_type not in ("customer", "business"):
        return jsonify({"error": "Valid email, password, and account_type are required"}), 400

    is_customer_account = account_type == "customer"

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Check login
        cur.execute("SELECT check_user_login(%s, %s, %s) AS valid", (email, password, is_customer_account))
        login_valid = cur.fetchone()["valid"]

        if not login_valid:
            return jsonify({"error": "Invalid credentials"}), 401

        # Get customer_id
        cur.execute("SELECT get_customer_id_by_login(%s, %s, %s) AS id", (email, password, is_customer_account))
        customer_id = cur.fetchone()["id"]

        return jsonify({
            "message": "Login successful",
            "customer_id": customer_id,
            "account_type": account_type
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

# Add the rest of your existing routes here (I kept them the same)
@app.route("/customers/<int:customer_id>", methods=["GET"])
def get_customer(customer_id):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.callproc("show_customer_info", [customer_id])
        rows = cur.fetchall()
        clear_results(cur)
        return jsonify(rows[0] if rows else {}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route("/customers/<int:customer_id>/orders", methods=["GET"])
def get_customer_orders(customer_id):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.callproc("get_customer_order_history", [customer_id])
        rows = cur.fetchall()
        clear_results(cur)
        return jsonify(rows), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route("/customers/<int:customer_id>/reviews", methods=["GET"])
def get_customer_reviews(customer_id):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.callproc("get_customer_written_reviews", [customer_id])
        rows = cur.fetchall()
        clear_results(cur)
        return jsonify(rows), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

@app.route("/reviews", methods=["POST"])
def create_review():
    data = request.get_json() or {}
    customer_id = data.get("customer_id")
    item_name = data.get("item_name", "").strip()
    review_text = data.get("review", "").strip()
    star_rating = data.get("star_rating")

    if not all([customer_id, item_name, review_text, star_rating is not None]):
        return jsonify({"error": "Missing required fields"}), 400

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.callproc("create_review", [customer_id, item_name, review_text, star_rating])
        clear_results(cur)
        return jsonify({"message": "Review created"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

# Keep your delete_review route as is...

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)