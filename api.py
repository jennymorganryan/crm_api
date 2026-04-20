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

# ====================== BASIC ROUTES ======================
@app.route("/", methods=["GET"])
def root():
    return jsonify({"message": "Furniture CRM API is running ✅"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200

@app.route("/products", methods=["GET"])
def get_products():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM catalog_summary ORDER BY item_name")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows), 200

# ====================== AUTH ======================
@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    account_type = data.get("account_type", "").strip().lower()

    if not email or not password or account_type not in ("customer", "business"):
        return jsonify({"error": "Valid email, password, and account_type are required"}), 400

    is_customer_account = account_type == "customer"

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT check_user_login(%s, %s, %s) AS valid", (email, password, is_customer_account))
        login_valid = cur.fetchone()["valid"]

        if not login_valid:
            return jsonify({"error": "Invalid credentials"}), 401

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
        cur.close()
        conn.close()

@app.route("/auth/signup", methods=["POST"])
def signup():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    account_type = data.get("account_type", "").strip().lower()

    if not email or not password or account_type not in ("customer", "business"):
        return jsonify({"error": "Valid email, password, and account_type are required"}), 400

    is_customer_account = account_type == "customer"

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("create_customer", [email, password, is_customer_account])
        clear_results(cur)

        cur.execute("SELECT get_customer_id_by_login(%s, %s, %s) AS id", (email, password, is_customer_account))
        customer_id = cur.fetchone()["id"]

        return jsonify({
            "message": "Account created successfully",
            "customer_id": customer_id,
            "account_type": account_type
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ====================== CUSTOMER & ORDERS ======================
@app.route("/customers/<int:customer_id>", methods=["GET"])
def get_customer(customer_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.callproc("show_customer_info", [customer_id])
    rows = cur.fetchall()
    clear_results(cur)
    cur.close()
    conn.close()
    return jsonify(rows[0] if rows else {}), 200

@app.route("/customers/<int:customer_id>/orders", methods=["GET"])
def get_customer_orders(customer_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.callproc("get_customer_order_history", [customer_id])
    rows = cur.fetchall()
    clear_results(cur)
    cur.close()
    conn.close()
    return jsonify(rows), 200

@app.route("/customers/<int:customer_id>/reviews", methods=["GET"])
def get_customer_reviews(customer_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.callproc("get_customer_written_reviews", [customer_id])
    rows = cur.fetchall()
    clear_results(cur)
    cur.close()
    conn.close()
    return jsonify(rows), 200

@app.route("/customers/<int:customer_id>/eligible-reviews", methods=["GET"])
def get_eligible_reviews(customer_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.callproc("get_customer_products_eligible_for_review", [customer_id])
    rows = cur.fetchall()
    clear_results(cur)
    cur.close()
    conn.close()
    return jsonify(rows), 200

# ====================== CART ======================
@app.route("/customers/<int:customer_id>/cart", methods=["GET"])
def get_cart(customer_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.callproc("view_order_cart", [customer_id])  # adjust if needed
    rows = cur.fetchall()
    clear_results(cur)
    cur.close()
    conn.close()
    return jsonify(rows), 200

@app.route("/cart/add", methods=["POST"])
def add_to_cart():
    data = request.get_json() or {}
    customer_id = data.get("customer_id")
    item_name = data.get("item_name")
    quantity = data.get("quantity", 1)

    if not customer_id or not item_name:
        return jsonify({"error": "customer_id and item_name required"}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Get or create open order
        cur.callproc("get_open_order_id", [customer_id])
        result = cur.fetchone()
        clear_results(cur)
        order_id = result["found_order_id"] if result else None

        if not order_id:
            cur.callproc("create_order_cart", [customer_id])
            result = cur.fetchone()
            clear_results(cur)
            order_id = result["new_order_id"]

        cur.callproc("upsert_cart_item", [order_id, item_name, quantity])
        clear_results(cur)
        conn.commit()
        return jsonify({"message": "Item added to cart"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route("/cart/delete", methods=["DELETE"])
def delete_from_cart():
    data = request.get_json() or {}
    customer_id = data.get("customer_id")
    item_name = data.get("item_name")

    if not customer_id or not item_name:
        return jsonify({"error": "customer_id and item_name required"}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("delete_cart_item", [customer_id, item_name])  # adjust if needed
        clear_results(cur)
        conn.commit()
        return jsonify({"message": "Item deleted from cart"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ====================== CHECKOUT ======================
@app.route("/checkout", methods=["POST"])
def checkout():
    data = request.get_json() or {}
    customer_id = data.get("customer_id")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    street1 = data.get("street1")
    street2 = data.get("street2")
    city = data.get("city")
    state = data.get("state")
    zip_code = data.get("zip_code")
    country = data.get("country")

    if not customer_id or not all([first_name, last_name, street1, city, state, zip_code, country]):
        return jsonify({"error": "All customer info fields required"}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("create_customer_info", [customer_id, first_name, last_name, street1, street2, city, state, int(zip_code), country])
        clear_results(cur)
        cur.callproc("checkout_order", [customer_id])  # adjust if needed
        clear_results(cur)
        conn.commit()
        return jsonify({"message": "Order checked out successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ====================== REVIEWS ======================
@app.route("/reviews", methods=["POST"])
def create_review():
    data = request.get_json() or {}
    customer_id = data.get("customer_id")
    item_name = data.get("item_name")
    review = data.get("review")
    star_rating = data.get("star_rating")

    if not all([customer_id, item_name, review, star_rating is not None]):
        return jsonify({"error": "Missing required fields"}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("create_review", [customer_id, item_name, review, star_rating])
        clear_results(cur)
        conn.commit()
        return jsonify({"message": "Review created"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ====================== PHOTOS ======================
@app.route("/photos", methods=["GET"])
def get_photos():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM photo")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)