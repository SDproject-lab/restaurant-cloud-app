from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import pymysql
import requests
import json

CLOUD_FUNCTION_URL = "https://service1-268065620206.europe-west1.run.app"
# -----------------------------
# CONNECT TO MONGODB
# -----------------------------
cluster = MongoClient("mongodb+srv://restaurantdb:Mk02pZLldI4tzorc@restaurantcluster.dajvmwz.mongodb.net/?retryWrites=true&w=majority&tls=true&appName=restaurantcluster")


db = cluster["restaurantdb"]
menu_collection = db["menu"]

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_KEY"   # Required for sessions


# -----------------------------
# HOME PAGE
# -----------------------------
@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html")


# -----------------------------
# MENU PAGE (from MongoDB)
# -----------------------------
@app.route("/menu")
def menu():
    response = requests.get(CLOUD_FUNCTION_URL)
    items = json.loads(response.text)

    # group items by category
    categories = {}
    for item in items:
        cat = item.get("category", "Other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    return render_template("menu.html", categories=categories, items=items)




# -----------------------------
# ADD TO CART (WORKING VERSION)
# -----------------------------
@app.route("/add_to_cart/<item_id>", methods=["POST"])
def add_to_cart(item_id):

    # Fetch menu from Cloud Function
    response = requests.get(CLOUD_FUNCTION_URL)
    items = json.loads(response.text)

    # Find the item in the JSON list
    item = None
    for i in items:
        if i["_id"]["$oid"] == item_id:
            item = i
            break

    if item is None:
        flash("Item not found.")
        return redirect(url_for("menu"))

    # Convert item to cart format
    cart_item = {
        "id": item_id,
        "name": item["name"],
        "price": item["price"]
    }

    cart = session.get("cart", [])
    cart.append(cart_item)
    session["cart"] = cart

    flash(f"{item['name']} added to cart.")
    return redirect(url_for("menu"))



# -----------------------------
# VIEW CART
# -----------------------------
@app.route("/cart")
def cart():
    cart_items = session.get("cart", [])
    return render_template("cart.html", cart_items=cart_items)


@app.route("/place_order", methods=["POST"])
def place_order():
    if "user_id" not in session:
        flash("You must log in to place an order.")
        return redirect(url_for("login"))

    cart = session.get("cart", [])

    if not cart:
        flash("Your cart is empty.")
        return redirect(url_for("cart"))

    # calculate total
    total = sum(float(item["price"]) for item in cart)

    # save to SQL
    conn = get_sql_connection()
    with conn.cursor() as cursor:

        # insert order
        cursor.execute(
            "INSERT INTO orders (user_id, total) VALUES (%s, %s)",
            (session["user_id"], total)
        )
        order_id = cursor.lastrowid

        # insert items
        for item in cart:
            cursor.execute(
                "INSERT INTO order_items (order_id, item_name, item_price) VALUES (%s, %s, %s)",
                (order_id, item["name"], item["price"])
            )

    conn.commit()
    conn.close()

    # clear the cart
    session["cart"] = []

    flash("Order placed successfully!")
    return redirect(url_for("home"))

@app.route("/orders")
def orders():
    if "user_id" not in session:
        flash("Please log in first.")
        return redirect(url_for("login"))

    conn = get_sql_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, total, created_at FROM orders WHERE user_id=%s ORDER BY created_at DESC",
            (session["user_id"],)
        )
        user_orders = cursor.fetchall()

    conn.close()
    return render_template("orders.html", orders=user_orders)



# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_sql_connection()

        # LOCAL MODE
        if conn is None:
            if username == "admin" and password == "admin":
                session["user_id"] = 1
                session["username"] = username
                flash("Logged in (local mode).")
                return redirect(url_for("home"))
            else:
                error = "Local mode: use admin / admin"
                return render_template("login.html", error=error)

        # REAL MODE
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, password_hash FROM users WHERE username=%s",
                (username,)
            )
            user = cursor.fetchone()

        conn.close()

        if user and check_password_hash(user[1], password):
            session["user_id"] = user[0]
            session["username"] = username
            flash("Logged in successfully.")
            return redirect(url_for("home"))
        else:
            error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("home"))





# -----------------------------
# REGISTER
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_sql_connection()

        # LOCAL MODE
        if conn is None:
            flash("Local mode: Registration disabled.")
            return redirect(url_for("login"))

        # REAL MODE
        with conn.cursor() as cursor:
            hashed_password = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, hashed_password)
            )

        conn.commit()
        conn.close()

        flash("Account created successfully.")
        return redirect(url_for("login"))

    return render_template("register.html")



def get_sql_connection():
    # Always use Cloud SQL Unix Socket in Cloud Shell or App Engine
    unix_socket = f"/cloudsql/{os.environ['CLOUD_SQL_CONNECTION_NAME']}"

    return pymysql.connect(
        user=os.environ['CLOUD_SQL_USERNAME'],
        password=os.environ['CLOUD_SQL_PASSWORD'],
        unix_socket=unix_socket,
        db=os.environ['CLOUD_SQL_DATABASE_NAME']
    )









# -----------------------------
# RUN LOCALLY
# -----------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
