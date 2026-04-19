import os
from flask import Flask, request, jsonify # type: ignore
from flask_cors import CORS
import pymysql

app = Flask(__name__)
CORS(app)

def get_connection():
    return pymysql.connect(
        host=os.environ["MYSQLHOST"],
        user=os.environ["MYSQLUSER"],
        password=os.environ["MYSQLPASSWORD"],
        database=os.environ["MYSQLDATABASE"],
        port=int(os.environ.get("MYSQLPORT") or 3306),
        cursorclass=DictCursor
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
    return jsonify({"ok": True})

@app.route("/catalog", methods=["GET"])
def get_catalog():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM catalog_summary ORDER BY item_name")
        rows = cur.fetchall()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    account_type = data.get("account_type", "").strip().lower()

    if account_type not in ("customer", "business"):
        return jsonify({"error": "Invalid account type"}), 400

    is_customer_account = account_type == "customer"

    conn = get_connection()
    cur = conn.cursor()

    try:
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
            "success": True,
            "customer_id": customer_id,
            "is_customer_account": is_customer_account
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)