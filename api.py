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

    if not all([url.hostname, url.username, url.password, url.port]):
        raise ValueError("Invalid DATABASE_URL")

    return pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path.lstrip("/"),
        port=url.port,
        cursorclass=DictCursor,
        connect_timeout=10,
        autocommit=True
    )


def clear_results(cur):
    while cur.nextset():
        pass


def fetch_function_value(cur, query, params=None):
    cur.execute(query, params or ())
    row = cur.fetchone()
    return list(row.values())[0] if row else None


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
        if cur:
            cur.close()
        if conn:
            conn.close()


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

        login_valid = fetch_function_value(
            cur,
            "SELECT check_user_login(%s, %s, %s) AS login_valid",
            (email, password, is_customer_account)
        )

        if not login_valid:
            return jsonify({"error": "Invalid email, password, or account type"}), 401

        customer_id = fetch_function_value(
            cur,
            "SELECT get_customer_id_by_login(%s, %s, %s) AS customer_id",
            (email, password, is_customer_account)
        )

        return jsonify({
            "message": "Login successful",
            "customer_id": customer_id,
            "account_type": account_type
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


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

        if not rows:
            return jsonify({"error": "Customer not found"}), 404

        return jsonify(rows[0]), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


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
        if cur:
            cur.close()
        if conn:
            conn.close()


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
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/reviews", methods=["POST"])
def create_review():
    data = request.get_json() or {}

    customer_id = data.get("customer_id")
    item_name = data.get("item_name", "").strip()
    review = data.get("review", "").strip()
    star_rating = data.get("star_rating")

    if not customer_id or not item_name or not review or star_rating is None:
        return jsonify({"error": "customer_id, item_name, review, and star_rating are required"}), 400

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.callproc("create_review", [customer_id, item_name, review, star_rating])
        clear_results(cur)

        return jsonify({"message": "Review created successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.route("/reviews/<int:review_id>", methods=["DELETE"])
def delete_review(review_id):
    data = request.get_json() or {}
    customer_id = data.get("customer_id")

    if not customer_id:
        return jsonify({"error": "customer_id is required"}), 400

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.callproc("delete_review", [review_id, customer_id])
        clear_results(cur)

        return jsonify({"message": "Review deleted successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)