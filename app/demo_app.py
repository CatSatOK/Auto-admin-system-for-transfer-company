"""Self-contained demo of the operator web app - no credentials required.

The production app talks to Gmail, Google Calendar, Google Maps, a MySQL
database and WordPress. None of that can be exposed publicly, so this demo
recreates just the operator-facing web UI using Flask and an in-memory SQLite
database seeded with synthetic bookings.

It lets a reviewer:
  - log in (any username/password in demo mode),
  - browse all bookings,
  - see on-hold bookings and Accept / Reject them (status updates in SQLite).

Run it:
    python3 -m pip install flask
    python3 demo_app.py
    # open http://127.0.0.1:5000  (login: demo / demo)
"""

import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = "demo-only-not-a-real-secret"

DEMO_USER = "demo"
DEMO_PASS = "demo"

# Column order matches the production Bookings table the templates index into:
# 0 Order, 1 Date, 2 Time, 3 From, 4 To, 5 Name, 6 Pax, 7 Total, 8 Deposit,
# 9 Phone, 10 Extras, 11 Details, 12 Address, 13 Body, 14 Email, 15 Message_ID,
# 16 Status
SEED_BOOKINGS = [
    ("1042", "12 July, 2026", "09:30", "Malaga Airport", "Marbella", "A. Dupont",
     "3 passengers", "180 EUR", "deposit paid", "+34 600 111 222", "none",
     "Flight IB3412", "Hotel Los Monteros", "...", "a.dupont@example.com",
     "msg_1042", "INVOICED"),
    ("1043", "12 July, 2026", "18:00", "Marbella", "Malaga Airport", "A. Dupont",
     "3 passengers", "180 EUR", "deposit paid", "+34 600 111 222", "none",
     "Return leg", "Hotel Los Monteros", "...", "a.dupont@example.com",
     "msg_1043", "INVOICED"),
    ("1051", "13 July, 2026", "07:15", "Malaga Airport", "Nerja", "B. Schmidt",
     "2 passengers", "210 EUR", "query", "+49 170 555 000", "golf bags",
     "Extra luggage", "Villa Mar", "...", "b.schmidt@example.com",
     "msg_1051", "ONHOLD"),
    ("1052", "13 July, 2026", "20:45", "Estepona", "Gibraltar Airport", "C. Rossi",
     "10 passengers", "320 EUR", " ", "+39 333 444 555", "none",
     "Large group", "Kempinski Hotel", "...", "c.rossi@example.com",
     "msg_1052", "ONHOLD"),
    ("1060", "14 July, 2026", "11:00", "Malaga Airport", "Fuengirola", "D. Owusu",
     "1 passenger", "120 EUR", "deposit paid", "+44 7700 900111", "none",
     "Flight BA2588", "Hotel Yaramar", "...", "d.owusu@example.com",
     "msg_1060", "TBC"),
    ("1061", "15 July, 2026", "05:30", "Marbella", "Malaga Airport", "E. Nilsson",
     "4 passengers", "175 EUR", "deposit paid", "+46 70 123 4567", "none",
     "Early pickup", "Puente Romano", "...", "e.nilsson@example.com",
     "msg_1061", "CANCELLED"),
]


def get_db():
    """Return a fresh in-process SQLite connection seeded with demo bookings."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE Bookings ("
        "`Order` TEXT, Date TEXT, Time TEXT, `From` TEXT, `To` TEXT, Name TEXT,"
        "Pax TEXT, Total TEXT, Deposit TEXT, Phone TEXT, Extras TEXT, Details TEXT,"
        "Address TEXT, Body TEXT, Email TEXT, Message_ID TEXT, Status TEXT)"
    )
    conn.executemany(
        "INSERT INTO Bookings VALUES (" + ",".join(["?"] * 17) + ")",
        _bookings_state(),
    )
    return conn


# Status changes persist for the life of the process so Accept/Reject "stick".
_STATE = {row[0]: row for row in SEED_BOOKINGS}


def _bookings_state():
    return list(_STATE.values())


def _set_status(order, status):
    if order in _STATE:
        row = list(_STATE[order])
        row[16] = status
        _STATE[order] = tuple(row)


def login_required(view):
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form["username"] == DEMO_USER and request.form["password"] == DEMO_PASS:
            session["logged_in"] = True
            return redirect(url_for("bookings"))
        error = "Invalid Credentials. Please try again. (demo / demo)"
    return render_template(
        "login.html", error=error, demo_hint=True,
        demo_user=DEMO_USER, demo_pass=DEMO_PASS,
    )


@app.route("/bookings")
@login_required
def bookings():
    conn = get_db()
    rows = conn.execute("SELECT * FROM Bookings").fetchall()
    conn.close()
    return render_template("bookings.html", rows=rows)


@app.route("/onhold", methods=["GET", "POST"])
@login_required
def onhold():
    if request.method == "POST":
        status = request.form.get("status")
        order = request.form.get("orderid")
        if status == "Accept":
            _set_status(order, "INVOICED")
            return render_template("confirm.html")
        if status == "Reject":
            _set_status(order, "CANCELLED")
            return render_template("cancel.html")
    conn = get_db()
    rows = conn.execute("SELECT * FROM Bookings WHERE Status = 'ONHOLD'").fetchall()
    conn.close()
    return render_template("onhold.html", rows=rows)


if __name__ == "__main__":
    print("Demo running at http://127.0.0.1:5000  (login: demo / demo)")
    app.run(host="127.0.0.1", port=5000, debug=False)
