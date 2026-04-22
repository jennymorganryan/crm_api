import os
import re
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from pymysql.cursors import DictCursor

app = Flask(__name__)
CORS(app)

EMAIL_PATTERN = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'


def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set")

    url = urlparse(database_url)

    return pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database="jenny_morgan_crm",
        port=url.port,
        cursorclass=DictCursor,
        autocommit=False
    )


def clear_results(cur):
    while cur.nextset():
        pass

def require_customer_account(is_customer_account):
    if not isinstance(is_customer_account, bool):
        return error_response("is_customer_account must be true or false")

    if not is_customer_account:
        return error_response("Customer account required", 403)

    return None


def standardize_item_name(item_name):
    return " ".join(word.capitalize() for word in item_name.strip().split())


def fetch_one_value(cur, query, params=None, key=None):
    cur.execute(query, params or ())
    row = cur.fetchone()
    if not row:
        return None
    if key:
        return row.get(key)
    return list(row.values())[0]


def error_response(message, status_code=400):
    return jsonify({"error": message}), status_code


def success_response(payload, status_code=200):
    return jsonify(payload), status_code


def validate_email(email):
    return bool(email and re.match(EMAIL_PATTERN, email))


def validate_account_type(account_type):
    return account_type in ("customer", "business")


def validate_password_for_signup(password):
    return bool(password) and len(password) >= 13


def validate_star_rating(star_rating):
    try:
        rating = float(star_rating)
        return 0 < rating <= 5
    except (TypeError, ValueError):
        return False


def validate_review_text(review_text):
    return isinstance(review_text, str) and 100 <= len(review_text.strip()) <= 999


def get_open_order_id(cur, user_id):
    return fetch_one_value(
        cur,
        "SELECT get_open_order_id(%s) AS order_id",
        (user_id,),
        "order_id"
    )


@app.route("/", methods=["GET"])
def root():
    return success_response({"message": "Furniture CRM API is running ✅"})


@app.route("/health", methods=["GET"])
def health():
    return success_response({"ok": True})


@app.route("/products", methods=["GET"])
def get_products():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM catalog_summary ORDER BY item_name")
        rows = cur.fetchall()
        return success_response(rows)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/products/<string:item_name>/reviews", methods=["GET"])
def get_item_reviews(item_name):
    conn = get_connection()
    cur = conn.cursor()
    try:
        item_name = standardize_item_name(item_name)
        cur.callproc("read_item_reviews", [item_name])
        rows = cur.fetchall()
        clear_results(cur)
        return success_response(rows)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    is_customer_account = data.get("is_customer_account")

    if not validate_email(email):
        return error_response("Valid email is required")

    if not password:
        return error_response("Password is required")

    if not isinstance(is_customer_account, bool):
        return error_response("is_customer_account must be true or false")

    account_type = "customer" if is_customer_account else "business"
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        login_valid = fetch_one_value(
            cur,
            "SELECT check_user_login(%s, %s, %s) AS valid",
            (email, password, is_customer_account),
            "valid"
        )

        if not login_valid:
            return error_response("Invalid credentials", 401)

        user_id = fetch_one_value(
            cur,
            "SELECT get_user_id_by_login(%s, %s, %s) AS user_id",
            (email, password, is_customer_account),
            "user_id"
        )

        return success_response({
            "message": "Login successful",
            "user_id": user_id,
            "account_type": account_type
        })
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/auth/signup", methods=["POST"])
def signup():
    data = request.get_json() or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    is_customer_account = data.get("is_customer_account")

    if not validate_email(email):
        return error_response("Valid email is required")

    if not password:
        return error_response("Password is required")

    if not isinstance(is_customer_account, bool):
        return error_response("is_customer_account must be true or false")

    account_type = "customer" if is_customer_account else "business"

    conn = get_connection()
    cur = conn.cursor()
    try:
        existing = fetch_one_value(
            cur,
            "SELECT check_user_email(%s) AS exists",
            (email,),
            "exists"
        )

        if existing:
            return error_response("Email already exists", 400)
        
        cur.callproc("create_user", [email, password, is_customer_account])
        clear_results(cur)

        user_id = fetch_one_value(
            cur,
            "SELECT get_user_id_by_login(%s, %s, %s) AS user_id",
            (email, password, is_customer_account),
            "user_id"
        )

        conn.commit()

        return success_response({
            "message": "Account created successfully",
            "user_id": user_id,
            "account_type": account_type
        }, 201)
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/customers/<string:user_id>", methods=["GET"])
def get_customer(user_id):
    data = request.get_json(silent=True) or {}
    is_customer_account = data.get("is_customer_account")

    error = require_customer_account(is_customer_account)
    if error:
        return error

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("show_customer_info", [user_id])
        rows = cur.fetchall()
        clear_results(cur)
        return success_response(rows[0] if rows else {})
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/customers/<string:user_id>/orders", methods=["GET"])
def get_customer_orders(user_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("get_customer_order_history", [user_id])
        rows = cur.fetchall()
        clear_results(cur)
        return success_response(rows)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/customers/<string:user_id>/reviews", methods=["GET"])
def get_customer_reviews(user_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("get_customer_written_reviews", [user_id])
        rows = cur.fetchall()
        clear_results(cur)
        return success_response(rows)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/customers/<string:user_id>/eligible-reviews", methods=["GET"])
def get_eligible_reviews(user_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("get_customer_products_eligible_for_review", [user_id])
        rows = cur.fetchall()
        clear_results(cur)
        return success_response(rows)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/customers/<string:user_id>/cart", methods=["GET"])
def get_cart(user_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        order_id = get_open_order_id(cur, user_id)

        if order_id is None:
            return success_response({"cart": [], "message": "No open cart"})

        cur.callproc("view_order_cart", [order_id])
        rows = cur.fetchall()
        clear_results(cur)
        return success_response(rows)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/cart/add", methods=["POST"])
def add_to_cart():
    data = request.get_json() or {}

    user_id = data.get("user_id")
    item_name = data.get("item_name", "").strip()
    quantity = data.get("quantity", 1)

    if not user_id:
        return error_response("user_id is required")

    if not item_name:
        return error_response("item_name is required")

    try:
        quantity = int(quantity)
        if quantity <= 0:
            return error_response("quantity must be greater than 0")
    except (TypeError, ValueError):
        return error_response("quantity must be a valid integer")

    item_name = standardize_item_name(item_name)

    conn = get_connection()
    cur = conn.cursor()
    try:
        order_id = get_open_order_id(cur, user_id)

        if order_id is None:
            cur.callproc("create_order_cart", [user_id])
            result = cur.fetchall()
            clear_results(cur)

            if result and "new_order_id" in result[0]:
                order_id = result[0]["new_order_id"]
            else:
                order_id = get_open_order_id(cur, user_id)

        cur.callproc("upsert_cart_item", [order_id, item_name, quantity])
        clear_results(cur)
        conn.commit()

        return success_response({
            "message": "Item added to cart",
            "order_id": order_id
        })
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/cart/update", methods=["PUT"])
def update_cart_item():
    data = request.get_json() or {}

    user_id = data.get("user_id")
    item_name = data.get("item_name", "").strip()
    quantity = data.get("quantity")

    if not user_id:
        return error_response("user_id is required")

    if not item_name:
        return error_response("item_name is required")

    try:
        quantity = int(quantity)
        if quantity <= 0:
            return error_response("quantity must be greater than 0")
    except (TypeError, ValueError):
        return error_response("quantity must be a valid integer")

    item_name = standardize_item_name(item_name)

    conn = get_connection()
    cur = conn.cursor()
    try:
        order_id = get_open_order_id(cur, user_id)

        if order_id is None:
            return error_response("No open cart found", 404)

        cur.callproc("upsert_cart_item", [order_id, item_name, quantity])
        clear_results(cur)
        conn.commit()

        return success_response({
            "message": "Cart updated successfully",
            "order_id": order_id
        })
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/cart/delete", methods=["DELETE"])
def delete_from_cart():
    data = request.get_json() or {}

    user_id = data.get("user_id")
    item_name = data.get("item_name", "").strip()

    if not user_id:
        return error_response("user_id is required")

    if not item_name:
        return error_response("item_name is required")

    item_name = standardize_item_name(item_name)

    conn = get_connection()
    cur = conn.cursor()
    try:
        order_id = get_open_order_id(cur, user_id)

        if order_id is None:
            return error_response("No open cart found", 404)

        cur.callproc("delete_cart_item", [order_id, item_name])
        clear_results(cur)
        conn.commit()

        return success_response({
            "message": "Item deleted from cart",
            "order_id": order_id
        })
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/cart/cancel", methods=["POST"])
def cancel_cart():
    data = request.get_json() or {}
    user_id = data.get("user_id")

    if not user_id:
        return error_response("user_id is required")

    conn = get_connection()
    cur = conn.cursor()
    try:
        order_id = get_open_order_id(cur, user_id)

        if order_id is None:
            return error_response("No open cart found", 404)

        cur.callproc("cancel_open_cart_on_exit", [order_id])
        clear_results(cur)
        conn.commit()

        return success_response({
            "message": "Open cart cancelled",
            "order_id": order_id
        })
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()

@app.route("/products/top-sellers", methods=["GET"])
def get_top_sellers():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("get_top_selling_items")
        rows = cur.fetchall()
        clear_results(cur)
        return jsonify(rows), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route("/checkout", methods=["POST"])
def checkout():
    data = request.get_json() or {}

    user_id = data.get("user_id")
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    street1 = data.get("street1", "").strip()
    street2 = data.get("street2")
    city = data.get("city", "").strip()
    state = data.get("state", "").strip()
    zip_code = data.get("zip_code")
    country = data.get("country", "").strip()

    if not user_id:
        return error_response("user_id is required")

    if not all([first_name, last_name, street1, city, state, zip_code, country]):
        return error_response("All required customer info fields must be provided")

    try:
        zip_code_str = str(zip_code)
    except (TypeError, ValueError):
        return error_response("zip_code must be valid")

    conn = get_connection()
    cur = conn.cursor()
    try:
        order_id = get_open_order_id(cur, user_id)

        if order_id is None:
            return error_response("No open cart found", 404)

        cur.callproc(
            "create_customer_info",
            [
                user_id,
                first_name,
                last_name,
                street1,
                street2,
                city,
                state,
                zip_code_str,
                country
            ]
        )
        clear_results(cur)

        cur.callproc("checkout_order", [order_id])
        clear_results(cur)

        delivery_date = fetch_one_value(
            cur,
            "SELECT delivery_date FROM order_cart WHERE order_id = %s",
            (order_id,),
            "delivery_date"
        )

        conn.commit()

        return success_response({
            "message": "Order checked out successfully",
            "order_id": order_id,
            "delivery_date": str(delivery_date) if delivery_date else None
        })
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/reviews", methods=["POST"])
def create_review():
    data = request.get_json() or {}

    user_id = data.get("user_id")
    item_name = data.get("item_name", "").strip()
    review = data.get("review", "").strip()
    star_rating = data.get("star_rating")

    if not user_id:
        return error_response("user_id is required")

    if not item_name:
        return error_response("item_name is required")

    if not validate_review_text(review):
        return error_response("Review must be between 100 and 999 characters")

    if not validate_star_rating(star_rating):
        return error_response("star_rating must be greater than 0 and at most 5")

    item_name = standardize_item_name(item_name)

    conn = get_connection()
    cur = conn.cursor()
    try:
        eligible = fetch_one_value(
            cur,
            "SELECT is_item_eligible_for_review(%s, %s) AS valid_review",
            (user_id, item_name),
            "valid_review"
        )

        if not eligible:
            return error_response("This item is not eligible for review", 400)

        cur.callproc("create_review", [user_id, item_name, review, float(star_rating)])
        clear_results(cur)
        conn.commit()

        return success_response({"message": "Review created"}, 201)
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/reviews/<int:review_id>", methods=["PUT"])
def update_review_text(review_id):
    data = request.get_json() or {}

    user_id = data.get("user_id")
    new_review_text = data.get("review", "").strip()

    if not user_id:
        return error_response("user_id is required")

    if not validate_review_text(new_review_text):
        return error_response("Review must be between 100 and 999 characters")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("update_review", [review_id, user_id, new_review_text])
        clear_results(cur)
        conn.commit()

        return success_response({"message": "Review updated successfully"})
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/reviews/<int:review_id>/rating", methods=["PATCH"])
def update_review_rating(review_id):
    data = request.get_json() or {}

    user_id = data.get("user_id")
    star_rating = data.get("star_rating")

    if not user_id:
        return error_response("user_id is required")

    if not validate_star_rating(star_rating):
        return error_response("star_rating must be greater than 0 and at most 5")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("update_star_rating", [review_id, user_id, float(star_rating)])
        clear_results(cur)
        conn.commit()

        return success_response({"message": "Star rating updated successfully"})
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/reviews/<int:review_id>", methods=["DELETE"])
def delete_review(review_id):
    data = request.get_json() or {}
    user_id = data.get("user_id")

    if not user_id:
        return error_response("user_id is required")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.callproc("delete_review", [review_id, user_id])
        clear_results(cur)
        conn.commit()

        return success_response({"message": "Review deleted successfully"})
    except Exception as e:
        conn.rollback()
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


@app.route("/photos", methods=["GET"])
def get_photos():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM photo")
        rows = cur.fetchall()
        return success_response(rows)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)