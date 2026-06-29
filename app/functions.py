"""Backwards-compatible facade for the auto-admin functions.

The implementation was refactored from this single 1,000-line file into focused
modules (see below). This module re-exports everything so existing imports such
as `from functions import *` keep working.

    db.py               -> connection, addToDatabase, updateStatus, deletePassedBookings
    email_service.py    -> getEmails, clean_emails, mark/star/unstar, gmailSendMessage
    ner_extraction.py   -> ner
    routing.py          -> gmapsAPI, mapTimings, getDuration
    calendar_service.py -> calendarCheckSimple, calendarAddEvent, getAbbrevations
    invoicing.py        -> sendInvoice
    notifications.py    -> sendAlert
    booking_logic.py    -> extrasCheckSimple, oneWayPath, returnPath,
                           restartReturn, rejectOrderReturn
    logging_config.py   -> logger
"""

from logging_config import logger
from db import connection, addToDatabase, updateStatus, deletePassedBookings
from email_service import (
    clean_emails, getEmails, markEmailAsRead, starMesage, unstarMesage,
    gmailSendMessage,
)
from ner_extraction import ner
from routing import gmapsAPI, mapTimings, getDuration
from calendar_service import getAbbrevations, calendarCheckSimple, calendarAddEvent
from invoicing import sendInvoice
from notifications import sendAlert
from booking_logic import (
    extrasCheckSimple, oneWayPath, returnPath, restartReturn, rejectOrderReturn,
)

__all__ = [
    "logger", "connection", "addToDatabase", "updateStatus", "deletePassedBookings",
    "clean_emails", "getEmails", "markEmailAsRead", "starMesage", "unstarMesage",
    "gmailSendMessage", "ner", "gmapsAPI", "mapTimings", "getDuration",
    "getAbbrevations", "calendarCheckSimple", "calendarAddEvent", "sendInvoice",
    "sendAlert", "extrasCheckSimple", "oneWayPath", "returnPath", "restartReturn",
    "rejectOrderReturn",
]
