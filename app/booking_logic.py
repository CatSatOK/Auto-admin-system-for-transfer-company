"""Booking orchestration: the decision logic that ties the pipeline together.

Two entry points are used by the scheduled job (`oneWayPath`, `returnPath`) and
two by the web app when the operator clicks Accept/Reject on an on-hold booking
(`restartReturn`, `rejectOrderReturn`). A booking is auto-confirmed only if it
passes the extras/last-minute checks and the calendar is free; otherwise it is
parked as ONHOLD and the operator is alerted.
"""

import os
import re
from datetime import datetime, timedelta

from google.oauth2 import service_account

from db import addToDatabase, connection, updateStatus
from email_service import gmailSendMessage, starMesage, unstarMesage
from notifications import sendAlert
from routing import gmapsAPI, mapTimings, getDuration
from calendar_service import calendarCheckSimple, calendarAddEvent
from invoicing import sendInvoice

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]
# Path to the Google service-account key file (kept out of version control)
SERVICE_AUTH_FILE = os.getenv("SERVICE_AUTH_FILE", "admin-auth.json")


def _build_creds():
    CalID = os.getenv("CalID")
    return service_account.Credentials.from_service_account_file(
        SERVICE_AUTH_FILE, scopes=SCOPES, subject=CalID
    )


def _calendar_entry(order, name, pax, phone, total, deposit, extras, details, address, body, note=""):
    extra = f"\n{note}\n" if note else ""
    return f"""
Order no: {order},
{name}, {pax},
Phone: {phone},
Total: {total},
Deposit: {deposit},
Extras: {extras},
Notes: {details},
Address: {address}
{extra}
Email body:
{body}
"""


def extrasCheckSimple(PAX, DATE, TIME, EXTRAS):
    """Flag bookings needing manual review: bulky extras, >8 pax, or last minute."""
    extra_options = ["surfboards", "golf bags", "bicycles"]
    num = int([x for x in PAX.split() if x.isdigit()][0])
    start_str = f"{DATE} {TIME}"
    datetime_object = datetime.strptime(start_str, "%d %B, %Y %H:%M")
    seconds_in_48h = 172800
    if any(map(EXTRAS.__contains__, extra_options)) or num > 8:
        return "EXTRAS_ISSUE"
    if (datetime_object - datetime.now()).total_seconds() < seconds_in_48h:
        return "LAST_MIN_ISSUE"
    return None


def oneWayPath(data, BODY, STATUS, PushToken, James, CalID, creds, EMAIL, MESSAGE_ID):
    """Process a one-way booking enquiry end to end."""
    (ORDER, NAME, DATE, TIME, FROM, TO, PAX, TOTAL, DEPOSIT, PHONE,
     EXTRAS, DETAILS, ADDRESS) = map(
        data.get,
        ("Order", "Name", "Date", "Time", "From", "To", "Pax", "Total",
         "Deposit", "Phone", "Extras", "Details", "Address"),
    )
    addToDatabase(ORDER, DATE, TIME, FROM, TO, NAME, PAX, TOTAL, DEPOSIT,
                  PHONE, EXTRAS, DETAILS, ADDRESS, BODY, EMAIL, MESSAGE_ID, STATUS)

    busy_email = f"Hello {NAME},\n\n#ADD EMAIL TEXT HERE\n"
    SUBJECT = f"RE: Transfers Enquiry no: {ORDER}"
    last_min = f"Last minute enquiry received (order {ORDER}), please check : LINK TO ONHOLD PAGE"
    extras = f"Enquiry that requires extra checks received (order {ORDER}), please check : LINK TO ONHOLD PAGE"

    checks = extrasCheckSimple(PAX, DATE, TIME, EXTRAS)
    if checks == "EXTRAS_ISSUE":
        sendAlert(PushToken, James, extras)
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, busy_email)
        updateStatus(ORDER, "ONHOLD")
        starMesage(creds, MESSAGE_ID)
        return
    if checks == "LAST_MIN_ISSUE":
        sendAlert(PushToken, James, last_min)
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, busy_email)
        updateStatus(ORDER, "ONHOLD")
        starMesage(creds, MESSAGE_ID)
        return

    api_key = gmapsAPI()
    start_str = f"{DATE} {TIME}"
    hrs, mins = getDuration(mapTimings(FROM, TO, start_str, api_key))
    unavailable = f"Enquiry received for time when currently unavailable (order {ORDER}), please check : LINK TO ONHOLD PAGE"

    if calendarCheckSimple(CalID, creds, start_str, hrs, mins) is False:
        sendAlert(PushToken, James, unavailable)
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, busy_email)
        updateStatus(ORDER, "ONHOLD")
        starMesage(creds, MESSAGE_ID)
        return

    calendar_entry = _calendar_entry(
        ORDER, NAME, PAX, PHONE, TOTAL, DEPOSIT, EXTRAS, DETAILS, ADDRESS, BODY
    )
    calendarAddEvent(creds, start_str, hrs, mins, calendar_entry, FROM, TO)
    available_email = f"Hello {NAME},\n\n#ADD EMAIL TEXT HERE\n"
    gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=available_email)
    sendInvoice(ORDER)
    updateStatus(ORDER, "INVOICED")


def returnPath(data, BODY, STATUS, PushToken, James, CalID, creds, EMAIL, MESSAGE_ID):
    """Process a return booking (two legs, A and B) end to end."""
    (ORDER_A, NAME, DATE_A, TIME_A, FROM_A, TO_A, PAX_A, TOTAL, DEPOSIT,
     PHONE, EXTRAS_A, DETAILS_A, ADDRESS_A) = map(
        data[0].get,
        ("Order", "Name", "Date", "Time", "From", "To", "Pax", "Total",
         "Deposit", "Phone", "Extras", "Details", "Address"),
    )
    ORDER_orig = ORDER_A
    ORDER_A = f"{ORDER_A}-A"  # unique order number per leg
    addToDatabase(ORDER_A, DATE_A, TIME_A, FROM_A, TO_A, NAME, PAX_A, TOTAL,
                  DEPOSIT, PHONE, EXTRAS_A, DETAILS_A, ADDRESS_A, BODY, EMAIL,
                  MESSAGE_ID, STATUS)
    Achecks = extrasCheckSimple(PAX_A, DATE_A, TIME_A, EXTRAS_A)
    api_key = gmapsAPI()
    start_str_A = f"{DATE_A} {TIME_A}"
    hrs_A, mins_A = getDuration(mapTimings(FROM_A, TO_A, start_str_A, api_key))
    Acalcheck = calendarCheckSimple(CalID, creds, start_str_A, hrs_A, mins_A)

    (ORDER_B, NAME, DATE_B, TIME_B, FROM_B, TO_B, PAX_B, TOTAL, DEPOSIT,
     PHONE, EXTRAS_B, DETAILS_B, ADDRESS_B) = map(
        data[1].get,
        ("Order", "Name", "Date", "Time", "From", "To", "Pax", "Total",
         "Deposit", "Phone", "Extras", "Details", "Address"),
    )
    ORDER_B = f"{ORDER_B}-B"
    addToDatabase(ORDER_B, DATE_B, TIME_B, FROM_B, TO_B, NAME, PAX_B, TOTAL,
                  DEPOSIT, PHONE, EXTRAS_B, DETAILS_B, ADDRESS_B, BODY, EMAIL,
                  MESSAGE_ID, STATUS)
    Bchecks = extrasCheckSimple(PAX_B, DATE_B, TIME_B, EXTRAS_B)
    start_str_B = f"{DATE_B} {TIME_B}"
    hrs_B, mins_B = getDuration(mapTimings(FROM_B, TO_B, start_str_B, api_key))
    Bcalcheck = calendarCheckSimple(CalID, creds, start_str_B, hrs_B, mins_B)

    SUBJECT = f"RE: Transfers Enquiry no: {ORDER_orig}"
    busy_email_return = f"Hello {NAME},\n\n#ADD EMAIL TEXT HERE\n"
    last_min = f"Last minute enquiry received (order {ORDER_orig}), please check : LINK TO ONHOLD PAGE"
    extras = f"Enquiry that requires extra checks received (order {ORDER_orig}), please check : LINK TO ONHOLD PAGE"
    unavailable = f"Enquiry received for time when currently unavailable (order {ORDER_orig}: A or B), please check : LINK TO ONHOLD PAGE"

    def _park_onhold(alert_msg):
        sendAlert(PushToken, James, alert_msg)
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=busy_email_return)
        starMesage(creds, MESSAGE_ID)
        updateStatus(ORDER_A, "ONHOLD")
        updateStatus(ORDER_B, "ONHOLD")

    if Achecks == "EXTRAS_ISSUE" or Bchecks == "EXTRAS_ISSUE":
        _park_onhold(extras)
        return
    if Achecks == "LAST_MIN_ISSUE" or Bchecks == "LAST_MIN_ISSUE":
        _park_onhold(last_min)
        return
    if Acalcheck is False or Bcalcheck is False:
        _park_onhold(unavailable)
        return

    # Both legs available: add to calendar, confirm and invoice
    calendar_entry_B = _calendar_entry(
        ORDER_B, NAME, PAX_B, PHONE, TOTAL, DEPOSIT, EXTRAS_B, DETAILS_B,
        ADDRESS_B, BODY, note=f"RETURN BOOKING - ORIGINAL TRANSFER {DATE_A}"
    )
    calendarAddEvent(creds, start_str_B, hrs_B, mins_B, calendar_entry_B, FROM_B, TO_B)
    calendar_entry_A = _calendar_entry(
        ORDER_A, NAME, PAX_A, PHONE, TOTAL, DEPOSIT, EXTRAS_A, DETAILS_A,
        ADDRESS_A, BODY, note=f"RETURN BOOKING - SECOND TRANSFER {DATE_B}"
    )
    calendarAddEvent(creds, start_str_A, hrs_A, mins_A, calendar_entry_A, FROM_A, TO_A)
    available_email_return = f"Hello {NAME},\n\n#ADD EMAIL TEXT HERE\n"
    gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=available_email_return)
    sendInvoice(ORDER_orig)
    updateStatus(ORDER_A, "INVOICED")
    updateStatus(ORDER_B, "INVOICED")


def _split_return_order(ORDER):
    """Given an -A or -B order id, return (ORDER_A, ORDER_B, ORDER_orig)."""
    if "-A" in ORDER:
        return ORDER, ORDER.replace("-A", "-B"), ORDER.replace("-A", "")
    return ORDER.replace("-B", "-A"), ORDER, ORDER.replace("-B", "")


def restartReturn(ORDER):
    """Confirm an on-hold booking when the operator clicks Accept in the app."""
    CalID = os.getenv("CalID")
    creds = _build_creds()
    cur, conn = connection()
    is_return = bool(re.search("-A|-B", ORDER))

    if is_return:
        ORDER_A, ORDER_B, ORDER_orig = _split_return_order(ORDER)
        for leg, suffix in ((ORDER_A, "A"), (ORDER_B, "B")):
            cur.execute("SELECT * FROM Bookings WHERE `Order` = %s", (leg,))
            r = cur.fetchall()[0]
            DATE, TIME, FROM, TO, NAME, PAX, TOTAL, DEPOSIT, PHONE, EXTRAS, \
                DETAILS, ADDRESS, BODY, EMAIL, MESSAGE_ID = r[1:16]
            start_str = f"{DATE} {TIME}"
            api_key = gmapsAPI()
            hrs, mins = getDuration(mapTimings(FROM, TO, start_str, api_key))
            entry = _calendar_entry(ORDER_orig, NAME, PAX, PHONE, TOTAL,
                                    DEPOSIT, EXTRAS, DETAILS, ADDRESS, BODY)
            calendarAddEvent(creds, start_str, hrs, mins, entry, FROM, TO)
            if suffix == "A":
                EMAIL_A, MESSAGE_ID_A, NAME_A = EMAIL, MESSAGE_ID, NAME
        subject = f"RE: Transfers Enquiry no: {ORDER_orig}"
        available = f"Hello {NAME_A},\n\n#ADD EMAIL TEXT HERE\n"
        gmailSendMessage(CalID, creds, EMAIL_A, subject, MESSAGE_ID_A, txt=available)
        unstarMesage(creds, MESSAGE_ID_A)
        sendInvoice(ORDER_orig)
        updateStatus(ORDER_A, "INVOICED")
        updateStatus(ORDER_B, "INVOICED")
    else:
        cur.execute("SELECT * FROM Bookings WHERE `Order` = %s", (ORDER,))
        r = cur.fetchall()[0]
        DATE, TIME, FROM, TO, NAME, PAX, TOTAL, DEPOSIT, PHONE, EXTRAS, \
            DETAILS, ADDRESS, BODY, EMAIL, MESSAGE_ID = r[1:16]
        start_str = f"{DATE} {TIME}"
        api_key = gmapsAPI()
        hrs, mins = getDuration(mapTimings(FROM, TO, start_str, api_key))
        subject = f"RE: Transfers Enquiry no: {ORDER}"
        entry = _calendar_entry(ORDER, NAME, PAX, PHONE, TOTAL, DEPOSIT,
                                EXTRAS, DETAILS, ADDRESS, BODY)
        calendarAddEvent(creds, start_str, hrs, mins, entry, FROM, TO)
        available = f"Hello {NAME},\n\n#ADD EMAIL TEXT HERE\n"
        gmailSendMessage(CalID, creds, EMAIL, subject, MESSAGE_ID, txt=available)
        unstarMesage(creds, MESSAGE_ID)
        sendInvoice(ORDER)
        updateStatus(ORDER, "INVOICED")

    cur.close()
    conn.close()


def rejectOrderReturn(ORDER):
    """Reject an on-hold booking when the operator clicks Reject in the app."""
    CalID = os.getenv("CalID")
    creds = _build_creds()
    cur, conn = connection()
    is_return = bool(re.search("-A|-B", ORDER))

    if is_return:
        ORDER_A, ORDER_B, ORDER_orig = _split_return_order(ORDER)
        cur.execute("SELECT * FROM Bookings WHERE `Order` = %s", (ORDER_A,))
        r = cur.fetchall()[0]
        NAME_A, EMAIL_A, MESSAGE_ID_A = r[5], r[14], r[15]
        subject = f"RE: Transfers Enquiry no: {ORDER_orig}"
        cancel_email = f"Hello {NAME_A},\n#ADD EMAIL TEXT HERE\n"
        gmailSendMessage(CalID, creds, EMAIL_A, subject, MESSAGE_ID_A, txt=cancel_email)
        updateStatus(ORDER_A, "CANCELLED")
        updateStatus(ORDER_B, "CANCELLED")
    else:
        cur.execute("SELECT * FROM Bookings WHERE `Order` = %s", (ORDER,))
        r = cur.fetchall()[0]
        NAME, EMAIL, MESSAGE_ID = r[5], r[14], r[15]
        subject = f"RE: Transfers Enquiry no: {ORDER}"
        cancel_email = f"Hello {NAME},\n\n#ADD EMAIL TEXT HERE\n"
        gmailSendMessage(CalID, creds, EMAIL, subject, MESSAGE_ID, txt=cancel_email)
        updateStatus(ORDER, "CANCELLED")

    cur.close()
    conn.close()
