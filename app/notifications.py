"""Pushover notifications to alert the operator's phone about bookings."""

import http.client
import urllib


def sendAlert(PushToken, user, msg):
    """Send a push notification to the operator via the Pushover API."""
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request(
        "POST",
        "/1/messages.json",
        urllib.parse.urlencode(
            {"token": PushToken, "user": user, "message": msg}
        ),
        {"Content-type": "application/x-www-form-urlencoded"},
    )
    conn.getresponse()
