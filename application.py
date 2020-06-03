import os
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import operator
from datetime import date
import urllib
import json
from helpers import apology, login_required
import math

# Global variable to check status of request form
request_live = False


# Configure application
app = Flask(__name__)


# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached (fresh data every time)
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///hudsmatch.db")

@app.route("/")
def index():

    # Render front page template
    return render_template("index.html")


@app.route("/home")
@login_required
def home():

    # Redirect based on party
    rows = db.execute("SELECT * FROM users WHERE id=:id", id=session["user_id"])
    if rows[0]["party"] == 1:
        return redirect("/huds")
    else:
        return redirect("/shelter")


@app.route("/huds")
@login_required
def huds():

    # User reached route via GET (as by clicking a link or via redirect)
        return render_template("huds.html")


@app.route("/donationform", methods=["GET", "POST"])
@login_required
def donationform():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        try:
            # Store entered values in a table
            soup = int(request.form.get("soup"))
            salad = int(request.form.get("salad"))
            sandwich = int(request.form.get("sandwich"))
            entree = int(request.form.get("entree"))
            side = int(request.form.get("side"))
            dessert = int(request.form.get("dessert"))
            db.execute("INSERT INTO huds (id, soup, salad, sandwich, entree, side, dessert) VALUES(:id, :soup, :salad, :sandwich, :entree, :side, :dessert)",
                       id=session["user_id"], soup = soup, salad = salad, sandwich = sandwich, entree = entree, side = side, dessert = dessert)
            return redirect("/home")
        except:
            return apology("Please fill out all fields of the donation form!")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("donationform.html")


@app.route("/donatenow")
@login_required
def donatenow():

    # Check that the HUDS table is not empty
    huds_empty = db.execute("SELECT * FROM huds where id = :id",id=session["user_id"])
    if not huds_empty:
      return apology("Please add least one donation before delivering")

    # Sum totals for each food type in all HUDS donations on the table
    huds_raw = db.execute("SELECT SUM(soup), SUM(salad), SUM(sandwich), SUM(entree), SUM(side), SUM(dessert) FROM huds WHERE id=:id", id=session["user_id"])
    huds_list = []
    for typefood in ["SUM(soup)", "SUM(salad)", "SUM(sandwich)", "SUM(entree)","SUM(side)","SUM(dessert)"]:
        huds_list.append(huds_raw[0][typefood])

    # To pass into HTML
    huds_initial = huds_list

    # Select information from requests and HUDS
    date_today = date.today()
    rows = db.execute("SELECT id, SUM(soup), SUM(salad), SUM(sandwich), SUM(entree), SUM(side), SUM(dessert) FROM requests WHERE requestdate=:requestdate GROUP BY id", requestdate=date_today)
    if not rows:
        return apology("No requests were made for today!")

    # Select information from users associated with the logged in donor
    rows_huds = db.execute("SELECT id, address FROM users WHERE id=:id", id=session["user_id"])

    # Create dictionaries for the shelter food matches, distances, happinesses, rankings, and all food requests
    shelter_rawmatch = {}
    shelter_dist_list = []
    shelter_happiness = {}
    shelter_rank = []
    shelter_all_food = {}

    # For each shelter
    for i in range(len(rows)):

        # Set matches for that shelter to 0
        num_matches = 0

        # Create temporary list of shelter totals for comparison with HUDS, add to our list of all food requested
        shelter_food_list = [rows[i]["SUM(soup)"], rows[i]["SUM(salad)"], rows[i]["SUM(sandwich)"], rows[i]["SUM(entree)"], rows[i]["SUM(side)"], rows[i]["SUM(dessert)"]]
        shelter_all_food[rows[i]["id"]] = shelter_food_list

        # For each food item
        for j in range(len(huds_list)):

            # Add the number of items in common between HUDS and shelter to the match score of the respective shelter by taking the min
            num_matches += min(huds_list[j], shelter_food_list[j])

        # Add info to our dictionary with IDs as keys and matches as values
        shelter_rawmatch[rows[i]["id"]] = num_matches

        # Find distance for each shelter
        address1 = rows_huds[0]["address"]
        rows_users = db.execute("SELECT address FROM users WHERE id=:id", id=rows[i]["id"])
        address2 = rows_users[0]["address"]
        try:
            shelter_dist_list.append(get_distance(address1, address2))
        except:
            return apology("Invalid street address")

        # Find happiness for each shelter
        shelter_happiness[rows[i]["id"]] = math.sqrt(shelter_rawmatch[rows[i]["id"]]/shelter_dist_list[i])
        sorted_shelter_happiness = sorted(shelter_happiness.items(), key=operator.itemgetter(1), reverse=True)

    # Rank shelters from top (highest happiness score) to bottom (lowest score)
    for k in range(len(sorted_shelter_happiness)):
        shelter_id = sorted_shelter_happiness[k][0]
        shelter_rank.append(shelter_id)

    # Find best 3 shelters (ranked by happiness level)
    shelters_chosen = []
    for m in range(3):
        try:
            shelters_chosen.append(shelter_rank[m])
        except IndexError as error:
            shelters_chosen = shelter_rank

    # Declare dictionaries for amount donated, shelter names/addresses
    donated_rows = {}
    shelter_names_addresses = {}
    rows_users = db.execute("SELECT id, username, address FROM users")

    # For each of the chosen shelters, find how much to donate
    for n in range(len(shelters_chosen)):
        # Create temporary list of donations to add to huds_donation_rows
        huds_donation = []
        donated = []
        for p in range(len(huds_list)):
            # Find how much of that item HUDS would have after donating
            donate_amt = huds_list[p] - shelter_all_food[shelters_chosen[n]][p]

            # If HUDS has enough, donate the exact amt requested; else just give all that is left
            if donate_amt >= 0:
                huds_donation.append(donate_amt)
            else:
                huds_donation.append(0)

            # Calculate amount actually donated
            donated.append(huds_list[p] - huds_donation[p])

        # Update amount left in HUDS' stock
        huds_list = huds_donation

        # Update the dictionary containing all donations
        donated_rows[shelters_chosen[n]] = donated

        # Update list of names/addresses for the shelters donated to
        for r in range(len(rows_users)):
            if rows_users[r]["id"] == shelters_chosen[n]:
                shelter_names_addresses[shelters_chosen[n]] = (rows_users[r]["username"], rows_users[r]["address"])

    # Render template
    return render_template("donatenow.html", huds_list = huds_list, huds_initial = huds_initial, shelters_chosen=shelters_chosen, shelter_names_addresses=shelter_names_addresses, donated_rows=donated_rows)

@app.route("/deliver")
@login_required
def deliver():

    # Clear HUDS table to start new set of donations
    clear = db.execute("DELETE FROM huds")

    # Render template
    return render_template("deliver.html")


@app.route("/shelter")
@login_required
def shelter():

    # User reached route via GET (as by clicking a link or via redirect)
        return render_template("shelter.html")


@app.route("/requestform", methods=["GET", "POST"])
@login_required
def requestform():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        try:
            # Process requests for each item
            soup = int(request.form.get("soup"))
            salad = int(request.form.get("salad"))
            sandwich = int(request.form.get("sandwich"))
            entree = int(request.form.get("entree"))
            side = int(request.form.get("side"))
            dessert = int(request.form.get("dessert"))
            request_date = (request.form.get("requestdate"))
        except:
           return apology("Please fill out all fields in the delivery request form!")

        # Insert into requests table
        if request_date <= str(date.today()):
            return apology("Please make the delivery request at least one day in advance")
        else:
            db.execute("INSERT INTO requests (id, requestdate, soup, salad, sandwich, entree, side, dessert) VALUES(:id, :requestdate, :soup, :salad, :sandwich, :entree, :side, :dessert)",
                       id=session["user_id"], soup = soup, requestdate = request_date, salad = salad, sandwich = sandwich, entree = entree, side = side, dessert = dessert)
            return render_template("requestthanks.html")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("requestform.html")


@app.route("/viewrequests")
@login_required
def viewrequests():

    # Find the requests associated with the shelter that is currently logged in
    rows = db.execute("SELECT requestdate, soup, salad, sandwich, entree, side, dessert FROM requests WHERE id=:id ORDER BY requestdate ASC", id=session["user_id"])

    # User reached route via GET (as by clicking a link or via redirect)
    return render_template("viewrequests.html", rows = rows)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and passworrd is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user depending on username
        return redirect("/home")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Must provide password")

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("Must provide password confirmation")

        # Ensure that passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords don't match")

        # Hash password
        hash = generate_password_hash(request.form.get("password"))

        # Find address
        try:
            address = request.form.get("address") + ", " + request.form.get("city") + ", " + request.form.get("state") + " " + request.form.get("zip")
        except:
            return apology("Must provide address!")

        # Find party
        if request.form.get("party") == "Donor":
            party = 1
        elif request.form.get("party") == "Requester":
            party = 0
        else:
            return apology("Must select whether you are food donor or requester")

        # Store values
        result = db.execute("INSERT INTO users(username, hash, address, party) VALUES (:username, :hash, :address, :party)",
                             username=request.form.get("username"), hash=hash, address=address, party=party)
        if not result:
             return apology("username is not available")

        session["user_id"] = result

        # Redirect user to home page
        return redirect("/home")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/home")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""

    # Get the username
    u = request.args.get("username")

    # Get list of usernames from database
    uList = db.execute("SELECT username FROM users")

    # Check if the username is in the list
    for i in range(len(uList)):
        if u == uList[i]["username"] or len(u) < 1:
            return jsonify(False)
    return jsonify(True)

def get_distance(address1, address2):

    # Base url that doesn't need altering
    baseurl = 'http://www.mapquestapi.com/directions/v2/route?key='

    # Plug in baseurl, addresses, and our API key to form the complete URL
    yql_url = baseurl + "9eEID9MBoDUAw99dq5iBSgyHlzN9J7XL" + "&" + urllib.parse.urlencode({'from':address1}) + "&" + urllib.parse.urlencode({'to':address2})

    # Read URL
    res = urllib.request.urlopen(yql_url).read()

    # If res is not null
    if (res):

        # User json.loads to load the data
        data = json.loads(res)

        # Parse the data to find distance
        distance = data["route"]["distance"]

        # Return the value obtained for distance
        return distance

    # If res is null
    else:

        # Return None to avoid errors
        return None