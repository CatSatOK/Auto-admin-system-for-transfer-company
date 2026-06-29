"""Google Calendar integration: availability checks and creating events.

A booking needs a free slot covering the outbound trip plus the return leg
(hence the duration is doubled). New bookings are added as `TBC` events until
confirmed by the operator in the web app.
"""

from datetime import timedelta

import datefinder
from googleapiclient.discovery import build

# Map full destination names to short codes used in calendar event titles.
# Populate with the real route names, e.g. {"Malaga Airport": "AGP"}.
DESTINATION_ABBREVIATIONS = {}


def getAbbrevations(FROM, TO):
    """Shorten known destination names for compact calendar event titles."""
    FROM = DESTINATION_ABBREVIATIONS.get(FROM, FROM)
    TO = DESTINATION_ABBREVIATIONS.get(TO, TO)
    return FROM, TO


def calendarCheckSimple(CalID, creds, start_str, hrs, mins):
    """Return True if the calendar is free for the whole transfer window."""
    service = build("calendar", "v3", credentials=creds)
    matches = list(datefinder.find_dates(start_str))
    start_time = matches[0]
    start = start_time.astimezone().isoformat()
    oneway = timedelta(hours=hrs, minutes=mins)
    end_time = start_time + (oneway * 2)  # allow for the return leg
    end = end_time.astimezone().isoformat()
    body = {
        "timeMin": start,
        "timeMax": end,
        "timeZone": "Europe/Paris",
        "items": [{"id": CalID}],
    }
    events_result = service.freebusy().query(body=body).execute()
    busy = events_result["calendars"].get(CalID, {}).get("busy")
    return not (busy and len(busy) > 0)


def calendarAddEvent(creds, start_str, hrs, mins, calendar_entry, FROM, TO):
    """Create a TBC calendar event for the transfer (and its return leg)."""
    FROM, TO = getAbbrevations(FROM, TO)
    title = f"TBC {FROM} - {TO}"
    service = build("calendar", "v3", credentials=creds)
    matches = list(datefinder.find_dates(start_str))
    start_time = matches[0]
    oneway = timedelta(hours=hrs, minutes=mins)
    end_time = start_time + (oneway * 2)  # allow for the return leg
    event = {
        "summary": title,
        "location": TO,
        "description": calendar_entry,
        "start": {
            "dateTime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Europe/Paris",
        },
        "end": {
            "dateTime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Europe/Paris",
        },
        "reminders": {"useDefault": True},
    }
    return service.events().insert(calendarId="primary", body=event).execute()
