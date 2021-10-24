import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # DELETE stocks that user has 0 shares
    db.execute("DELETE FROM master WHERE number_of_shares = ?", 0)

    # SELECT to check stocks the user has
    checks = db.execute("SELECT * FROM master WHERE id = ?", session["user_id"])

    # UPDATE price
    for check in checks:
        new_price = lookup(check["symbol"])["price"]
        db.execute("UPDATE master SET price = ?, total = ? WHERE symbol = ?", new_price, new_price*int(check["number_of_shares"]), check["symbol"])

    # SELECT the stocks the user has
    stocks = db.execute("SELECT * FROM master WHERE id = ?", session["user_id"])

    # SELECT amount of cash the user has
    user_cash = db.execute("SELECT cash, username FROM users WHERE id = ?", session["user_id"])
    cash = user_cash[0]["cash"]

    # Calculate total value
    total_value = cash
    if len(stocks) > 0:
        for stock in stocks:
            total_value += stock["total"]

    return render_template("index.html", stocks=stocks, cash=cash, total_value=total_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure user has typed ina stock symbol
        if not request.form.get("symbol"):
            return apology("Please type in a Stock Symbol")

        # Ensure user has typed in a valid stock symbol
        elif lookup(request.form.get("symbol")) == None:
            return apology("Please type in a valid Stock Symbol")

        # Ensure user has typed in the amount of shares they want to buy
        elif not request.form.get("shares"):
            return apology("Please type in the amount of shares you want to buy")

        # Ensure user has typed in a positive integer
        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("Number of Shares is not a positive integer")
        if shares <= 0:
            return apology("Number of Shares is not a positive integer")

        # Lookup price of stock
        price = lookup(request.form.get("symbol"))["price"]

        # SELECT how much cash the user has
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        user_cash = cash[0]["cash"]

        # Ensure the user can afford the price
        if (shares * price) > user_cash:
            return apology("Cannot Afford")

        # Lookup stock name
        stock_name = lookup(request.form.get("symbol"))["name"]

        # Symbol
        symbol = lookup(request.form.get("symbol"))["symbol"]

        # SELECT username of user
        users = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])
        username = users[0]["username"]

        # Get date now
        now = datetime.now()
        # Format date into YYYY-mm-dd
        date = now.strftime("%Y-%m-%d")

        # Amount of cash the user has after purchase
        user_cash_after_purchase = user_cash - (shares*price)

        # UPDATE amount of cash the user has after purchase
        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_cash_after_purchase, session["user_id"])

        # Record purchase in database
        db.execute("INSERT INTO transactions (id, username, date, stock, price, number_of_shares, user_cash_before, user_cash_after, symbol, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", session["user_id"], username, date, stock_name, price, shares, user_cash, user_cash_after_purchase, request.form.get("symbol"), "buy")

        checks = db.execute("SELECT * FROM master WHERE symbol = ? AND id = ?", symbol, session["user_id"])

        # If list is empty
        if not checks:

            # Place purchase into master datbase
            db.execute("INSERT INTO master (id, username, symbol, stock, number_of_shares, price, total) VALUES (?, ?, ?, ?, ?, ?, ?)", session["user_id"], username, symbol, stock_name, shares, price, (shares*price))

        else:

            for check in checks:

                # update new number of shares
                new_shares = shares + int(check["number_of_shares"])

                # Check for user and symbol are the same
                if check["symbol"] == symbol and check["id"] == session["user_id"]:

                    # UPDATE the master table with the new number of shares
                    db.execute("UPDATE master SET number_of_shares = ?, total = ? WHERE symbol = ? AND id = ?", new_shares, (new_shares*price), symbol, session["user_id"])

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # SELECT the names and amount of shares of the stocks the user has
    stocks = db.execute("SELECT * FROM transactions WHERE id = ?", session["user_id"])

    for stock in stocks:
        # Lookup symbol of the stocks
        stock["symbol"] = lookup(stock["symbol"])["symbol"]

    return render_template("history.html", stocks=stocks)


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

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure a valid symbol was given
        if not request.form.get("symbol") or lookup(request.form.get("symbol")) == None:
            return apology("Please provide a valid symbol")

        # Get the stock symbol
        symbol = lookup(request.form.get("symbol"))

        # Send user to page with information about the stock
        return render_template("quoted.html", symbol=symbol)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # Ensure confirmation password was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide confirmation password")

        # Ensure confirmation password is the same as password
        elif not request.form.get("confirmation") == request.form.get("password"):
            return apology("password must match confirmation password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username is valid
        if len(rows) >= 1:
            return apology("invalid username, choose another")

        # Register the user into the database
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    stocks = db.execute("SELECT * FROM master WHERE id = ?", session["user_id"])

    # Get the valid symbols
    symbols = [stock["symbol"] for stock in stocks]
    # Match with the number of shares user has
    shares_list = [stock["number_of_shares"] for stock in stocks]

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure shares was provided
        if not request.form.get("shares"):
            return apology("must provide number of shares")

        # Ensure valid symbol was given (hacking)
        if request.form.get("symbol") not in symbols:
            return apology("must provide valid symbol")

        # Ensure user has typed in a positive integer
        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("Number of Shares is not a positive integer", 400)
        if shares <= 0:
            return apology("Number of Shares is not a positive integer")

        # Ensure that user has shares of the stock
        for i in range(len(symbols)-1):
            if symbols[i] == request.form.get("symbol"):
                if int(request.form.get("shares")) > shares_list[i]:
                    return apology("Don't own that many shares")

        # SELECT username and cash of user
        users = db.execute("SELECT username, cash FROM users WHERE id = ?", session["user_id"])
        username = users[0]["username"]
        user_cash = users[0]["cash"]

        # Get date now
        now = datetime.now()
        # Format date into YYYY-mm-dd
        date = now.strftime("%Y-%m-%d")

        # Stock name
        stock = lookup(request.form.get("symbol"))["name"]

        # Stock symbol
        symbol = request.form.get("symbol")

        # Stock price
        price = lookup(request.form.get("symbol"))["price"]

        # Amount of cash the user has after purchase
        user_cash_after_sell = user_cash + (shares*price)

        # UPDATE amount of cash the user has after purchase
        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_cash_after_sell, session["user_id"])

        # Record sell in database
        db.execute("INSERT INTO transactions (id, username, date, stock, price, number_of_shares, user_cash_before, user_cash_after, symbol, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", session["user_id"], username, date, stock, price, shares, user_cash, user_cash_after_sell, request.form.get("symbol"), "sell")

        checks = db.execute("SELECT * FROM master WHERE symbol = ? AND id = ?", symbol, session["user_id"])

        for check in checks:

            # update new number of shares
            new_shares = int(check["number_of_shares"] - shares)

            # Check for user and symbol are the same
            if check["symbol"] == symbol and check["id"] == session["user_id"]:

                # UPDATE the master table with the new number of shares
                db.execute("UPDATE master SET number_of_shares = ?, total = ? WHERE symbol = ? AND id = ?", new_shares, (new_shares*price), symbol, session["user_id"])

        return redirect("/")

    else:
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
