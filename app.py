import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from time import sleep

from helpers import apology, login_required, lookup, usd


# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
#if not os.environ.get("API_KEY"):
#    raise RuntimeError("API_KEY not set")


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

    # Get current user_stock_depot data from database
    user_depot = db.execute("SELECT symbol, value FROM user_stock_depot JOIN stock_symbols ON user_stock_depot.symbol_id = stock_symbols.id WHERE user_id = ?", session["user_id"])

    # Add current price to stocks in user_depot
    depot_total = 0
    for stock in user_depot:
        stock["price"] = lookup(stock["symbol"])["price"]
        stock["total"] = stock["price"] * float(stock["value"])
        depot_total = depot_total + (stock["price"] * stock["value"])

    # Get current amount of cash on user account
    user_credit = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    return render_template("index.html", depot=user_depot, user_credit=user_credit, grand_total=depot_total + user_credit)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a purchase via POST)
    if request.method == "POST":

        # Validate user input
        symbol = request.form.get("symbol")
        stock = lookup(symbol)

        if not stock:
            return apology("Stock not found", 400)

        try:
            shares = int(request.form.get("shares"))
            if shares < 1:
                return apology("Please enter a valid amount", 400)
        except ValueError:
            return apology("Please enter a valid amount", 400)


        # Check liquidity of user
        credit = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        price = stock["price"] * shares

        if price > credit:
            return apology("Payment not possible - check account balance", 400)


        # If symbol does not exists, create entry
        try:
            symbol_id = db.execute("SELECT id FROM stock_symbols WHERE symbol = ?", symbol)[0]["id"]
        except IndexError:
            symbol_id = db.execute("INSERT INTO stock_symbols (symbol) VALUES (?)", symbol)


        # Check if stock exists already in user depot
        depot = db.execute("SELECT * FROM user_stock_depot WHERE symbol_id = ? AND user_id = ?",
                           symbol_id, session["user_id"])

        if not depot:
            db.execute("INSERT INTO user_stock_depot (symbol_id, user_id, value) VALUES (?,?,?)",
                       symbol_id, session["user_id"], shares)
        else:
            db.execute("UPDATE user_stock_depot SET value = ? WHERE symbol_id = ? AND user_id = ?",
                       shares + depot[0]["value"], symbol_id, session["user_id"])


        # Store transaction data in database
        transaction_type = db.execute("SELECT id FROM transaction_type WHERE transaction_type = 'buy'")[0]["id"]
        query = "INSERT INTO transactions (symbol_id, shares, price_per_share, transaction_type, user_id) VALUES (?,?,?,?,?)"
        db.execute(query, symbol_id, shares, stock["price"], transaction_type, session["user_id"])

        # Update account balance
        credit -= price
        db.execute("UPDATE users SET cash = ? WHERE id = ?", credit, session["user_id"])

        # Redirect to index.html
        return redirect("/")


    # User reached route via GET (as by opening 'Buy'-tab in navbar)
    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # ONLY GET #
    # Generate query to get transaction data
    query = '''
        SELECT transaction_type.transaction_type, symbol, price_per_share, shares, timestamp FROM transactions
        JOIN stock_symbols ON transactions.symbol_id = stock_symbols.id
        JOIN transaction_type ON transactions.transaction_type = transaction_type.id
        WHERE user_id = ?
    '''

    # Execute query
    transaction_data = db.execute(query, session["user_id"])

    # Render history
    return render_template("history.html", transaction_data = transaction_data)



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

    # User reached route via 'GET' (as by clicking a link or via redirect)
    else:
        return render_template("login.html")



@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash():
   """Add cash to account"""

    # User reached route via 'POST' (as by adding cash to account via button)
   if request.method == "POST":

        # Validate user input
        try:
            amount_load = float(request.form.get("add_cash"))
            if amount_load <= 0:
                return apology("Enter non-zero positive value")
        except ValueError:
            return apology("Enter non-zero positive value")

        # Store new cash value in database
        current_user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        current_user_cash += amount_load
        db.execute("UPDATE users SET cash = ? WHERE id = ?", current_user_cash, session["user_id"])

        # Redirect to index.html
        return redirect("/")

    # User reached route via 'GET' (as by clicking on 'add cash'-tab in navbar)
   else:
       return render_template("add_cash.html")


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

    # User reached route via POST (as by submitting a symbol via POST)
    if request.method == "POST":

        # Lookup symbol provided by user, if no symbol found - ERROR
        stock = lookup(request.form.get("symbol"))

        if not stock:
            return apology("Stock not found", 400)
        else:
            return render_template("quoted.html", stock = stock)

    # User reached route via GET (as by opening 'Quote'-tab via navbar)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        # Validate if user inputs username
        if not username :
            return apology("Enter username", 400)

        # Check if username already exists
        elif db.execute("SELECT username FROM users WHERE username = ?", username):
            return apology("Username already exists", 400)

        # Validate password
        if not password:
            return apology("Enter password", 400)

        # Check if password matches confirmation
        elif not request.form.get("confirmation") == password:
            return apology("Passwords do not match", 400)

        # Register user in database
        query = "INSERT INTO users (username, hash) VALUES (?,?)"
        session["user_id"] = db.execute(query, username, generate_password_hash(password))

        # Redirect user index.html
        return redirect("/")

    else:
        # User reached via 'GET' (as requesting login form)
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached via 'POST' (as selling stock via form)
    if request.method == "POST":

        symbol = request.form.get("symbol")
        query = '''
            SELECT value FROM user_stock_depot
            JOIN stock_symbols ON user_stock_depot.symbol_id = stock_symbols.id
            WHERE user_id = ? AND symbol = ?
        '''
        depot_shares = db.execute(query, session["user_id"], symbol)

        # Validate choosed stock
        if len(depot_shares) == 0:
            return apology("Stock not in depot/ Choose correct stock", 400)

        # Validate choosed shares
        try:
            shares = int(request.form.get("shares"))
            if shares < 1 or shares > depot_shares[0]["value"]:
                return apology("Please enter a valid amount", 400)
        except ValueError:
            return apology("Please enter a valid amount", 400)


        # Get current stock price
        stock = lookup(symbol)

        # Update shares
        depot_shares[0]["value"] = depot_shares[0]["value"] - shares
        if depot_shares[0]["value"] == 0:
            query = '''
                DELETE FROM user_stock_depot
                WHERE user_id = ? AND symbol_id = (SELECT symbol_id FROM stock_symbols WHERE symbol = ?)
            '''
            db.execute(query,  session["user_id"], symbol)

        else:
            query = '''
                UPDATE user_stock_depot SET value = ? WHERE user_id = ?
                AND symbol_id = (SELECT symbol_id FROM stock_symbols WHERE symbol = ?)
            '''
            db.execute(query, depot_shares[0]["value"], session["user_id"], symbol)

        # Update account balance
        credit = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        credit += (shares * stock["price"])
        db.execute("UPDATE users SET cash = ? WHERE id = ?", credit, session["user_id"])

        # Log transaction
        transaction_type = db.execute("SELECT id FROM transaction_type WHERE transaction_type = 'sell'")[0]["id"]
        query = '''
            INSERT INTO transactions (symbol_id, shares, price_per_share, transaction_type, user_id)
            VALUES ((SELECT id FROM stock_symbols WHERE symbol = ?),?,?,?,?)
        '''
        db.execute(query, symbol, shares, stock["price"], transaction_type, session["user_id"])

        return redirect("/")

    # User reached via 'GET' (as visiting 'sell'-tab via navbar)
    else:
        depot_data = db.execute("SELECT symbol, symbol_id FROM user_stock_depot JOIN users ON user_stock_depot.user_id = users.id JOIN stock_symbols ON user_stock_depot.symbol_id = stock_symbols.id WHERE users.id = ?", session["user_id"])
        return render_template("sell.html", depot=depot_data)


