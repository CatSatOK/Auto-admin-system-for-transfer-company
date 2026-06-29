"""Google Maps routing: travel time between pickup and destination."""

from datetime import datetime
import re

import googlemaps


def gmapsAPI():
    """Read the Google Maps API key from a local file and return it."""
    with open("GMaps_api.txt") as f:
        api_key = f.readline().strip()
    return api_key


def mapTimings(FROM, TO, start_str, api_key):
    """Return the estimated driving time for the transfer as a text string."""
    client = googlemaps.Client(key=api_key)
    datetime_object = datetime.strptime(start_str, "%d %B, %Y %H:%M")
    directions_results = client.directions(
        FROM, TO, mode="driving", departure_time=datetime_object
    )
    travel_time = directions_results[0]["legs"][0]["duration"]["text"]
    return travel_time


def getDuration(time):
    """Parse a '1 hour 20 mins' style string into (hours, minutes) ints."""
    dur = re.findall(r"\d+", time)
    if len(dur) > 1:
        hrs, mins = int(dur[0]), int(dur[1])
    else:
        hrs, mins = 0, int(dur[0])
    return hrs, mins
