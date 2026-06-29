"""Database access: connection handling and booking CRUD.

Bookings live in a MySQL/MariaDB database (`bookingsdb`). Corporate clients are
linked via a foreign key so repeat business can be recognised by email address.
"""

import os

import mysql.connector as mariadb


def connection():
    """Open a connection to the bookings database and return (cursor, conn)."""
    db_user = os.getenv("DBuser")
    db_password = os.getenv("DBpass")
    conn = mariadb.connect(
        host="localhost",
        user=db_user,
        password=db_password,
        database="bookingsdb",
    )
    cur = conn.cursor()
    return cur, conn


def addToDatabase(
    ORDER, DATE, TIME, FROM, TO, NAME, PAX, TOTAL, DEPOSIT, PHONE,
    EXTRAS, DETAILS, ADDRESS, BODY, EMAIL, MESSAGE_ID, STATUS,
):
    """Insert a new booking enquiry, attaching a corporate client id if known."""
    cur, conn = connection()
    # Recognise repeat corporate clients by their email address
    cur.execute(
        "SELECT Customer_ID FROM Corporate_clients WHERE Customer_Email = %s",
        (EMAIL,),
    )
    corp_id = cur.fetchone()
    if corp_id is not None:
        corp_id = corp_id[0]
    cur.execute(
        "INSERT INTO Bookings (`Order`, Date, Time, `From`, `To`, Name, Pax, "
        "Total, Deposit, Phone, Extras, Details, Address, `Body`, Email, "
        "Message_ID, Status, Corp_Client_ID) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (ORDER, DATE, TIME, FROM, TO, NAME, PAX, TOTAL, DEPOSIT, PHONE,
         EXTRAS, DETAILS, ADDRESS, BODY, EMAIL, MESSAGE_ID, STATUS, corp_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def updateStatus(ORDER, STATUS_UPDATED):
    """Update the status of a single booking (e.g. TBC -> INVOICED / CANCELLED)."""
    cur, conn = connection()
    cur.execute(
        "UPDATE Bookings SET Status = %s WHERE `Order` = %s",
        (STATUS_UPDATED, ORDER),
    )
    conn.commit()
    cur.close()
    conn.close()


def deletePassedBookings():
    """Delete bookings whose transfer date has already passed (run daily)."""
    cur, conn = connection()
    cur.execute(
        "DELETE FROM Bookings WHERE STR_TO_DATE(Date, '%d %B, %Y') < CURDATE()"
    )
    conn.commit()
    cur.close()
    conn.close()
