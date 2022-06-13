import os
from datetime import datetime, date

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    orders = db.execute("SELECT symbol, sum(shares) as sumshares, price FROM orders WHERE user_id = ? GROUP BY symbol", session["user_id"])
    _sum = cash[0]["cash"]
    for order in orders:
        name = lookup(order["symbol"])["name"]
        total = order["sumshares"] * order["price"]
        order["name"] = name
        order["total"] = total
        order["price"] = order["price"]
        _sum += total
    return render_template("index.html", orders=orders, cash=cash[0]["cash"], sum=_sum)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        #missing or invalid symbol
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not symbol:
            return apology("Missing Symbol", 400)
        elif not quote:
            return apology("Invalid Symbol", 400)

        #Invalid shares number
        try:
            shares = float(request.form.get("shares"))
            if not shares or not float.is_integer(shares) or shares <= 0:
                raise ValueError
        except ValueError:
            return apology("Invalid number", 400)

        # insufficient balance
        row = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = row[0]["cash"]
        balance = cash - shares * quote["price"]
        if balance < 0:
            return apology("Insufficient balance.", 400)

        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, session["user_id"])
        db.execute("INSERT INTO orders (user_id, symbol, shares, price, timestamp) VALUES (?, ?, ?, ?, ?)", session["user_id"], symbol.upper(), shares, quote["price"], datetime.now())
        return redirect("/")

    else:
        return render_template("buy.html")

    #CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, user_id INTEGER, symbol VARCHAR, shares INTEGER, price FLOAT, timestamp VARCHAR, FOREIGN KEY (user_id) REFERENCES users(id));

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    orders = db.execute("SELECT symbol, shares, price, timestamp FROM orders WHERE user_id = ?", session["user_id"])
    if not orders:
        return apology("No history", 403)
    else:
        for order in orders:
            order["name"] = lookup(order["symbol"])["name"]
            if order["shares"] > 0:
                order["status"] = "Bought"
            else:
                order["status"] = "Sold"
        return render_template("history.html", orders=orders)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not symbol:
            return apology("Missing Symbol", 400)
        elif not quote:
            return apology("Invalid Symbol", 400)
        else:
            return render_template("quoted.html", quote=quote)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        name = request.form.get("username")
        password = request.form.get("password")

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password and confirmation matched
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Password and confirmation don't match.", 400)

        #Ensure not existed user
        checkuser = db.execute("SELECT * FROM users WHERE username = ?", name)
        if len(checkuser) == 1:
            return apology("User already existed.", 400)
        else:
            db.execute("INSERT INTO users (username, hash) VALUES (? , ?)", name, generate_password_hash(password))
            return render_template("login.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        symbols = db.execute("SELECT symbol FROM orders WHERE user_id = ? GROUP BY symbol", session["user_id"])
        return render_template("sell.html", symbol=symbols)
    else:
        # get user input
        symbol = request.form.get("symbol")
        print(symbol)
        shares = request.form.get("shares")
        if not shares:
            return apology("Invaild shares", 400)
        shares = int(shares)
        #check missing symbol, shares, negative shares
        if shares<=0:
            return apology("Invaild symbol or shares", 400)

        #check shares to be sold exceed bought shares
        sumshares = db.execute("SELECT symbol, SUM(shares) as sumshares FROM orders WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
        if shares > int(sumshares[0]["sumshares"]):
            return apology("You don't have so many shares",400)

        #sell
        shares = -shares
        quote = lookup(symbol)
        print(quote)
        sql = db.execute("INSERT INTO orders (user_id, symbol, shares, price, timestamp) VALUES (?, ?, ?, ?, ?)", session["user_id"], symbol, shares, quote["price"], datetime.now())
        sold = shares * quote["price"]
        print(sold)

        #update cash
        cash = db.execute("select cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        cash = cash - sold
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])
        return redirect("/")

