"""Gmail integration: fetching booking emails, labelling, and replying.

Uses the Gmail API to pull unread booking-request emails, clean the HTML body
into plain text for the NER model, and send threaded replies to the customer.
"""

import base64
import re

import pandas as pd
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.message import EmailMessage
import os

from logging_config import logger

# Gmail label applied to emails already processed by the auto-admin pipeline
PROCESSED_LABEL_ID = "Label_3036548299999784630"


def clean_emails(text):
    """Strip HTML, URLs and whitespace artefacts, returning lowercased text."""
    text = re.sub("<[^<]+?>", " ", text)   # remove HTML tags
    text = re.sub(r"http\S+", " ", text)   # remove URLs
    text = re.sub(r"\r\n", " ", text)
    text = re.sub(r"\t", " ", text)
    text = re.sub(r"\x92", " ", text)
    text = re.sub(r"&gt", " ", text)
    text = re.sub(r";", " ", text)
    text = re.sub(r"\n", " ", text)
    text = text.lower()
    text = re.sub(r" +", " ", text)        # collapse extra whitespace
    return text


def getEmails(creds):
    """Fetch unread booking-request emails and return them as a DataFrame.

    Only emails from the configured `SenderID` whose subject contains
    'New order' (and is not a reply) are treated as booking requests.
    """
    df = pd.DataFrame(
        columns=["Date", "Sender", "Email", "Body", "Subject", "Messsage_ID"]
    )
    service = build("gmail", "v1", credentials=creds)
    result = service.users().messages().list(
        userId="me", labelIds=["UNREAD"], q="in:inbox"
    ).execute()
    messages = result.get("messages")
    if type(messages) is not list:
        raise SystemExit

    for msg in messages:
        txt = service.users().messages().get(userId="me", id=msg["id"]).execute()
        payload = txt["payload"]
        headers = payload["headers"]
        for d in headers:
            if d["name"] == "Date":
                date = d["value"]
            if d["name"] == "Subject":
                subject = d["value"]
            if d["name"] == "From":
                sender = d["value"]
            if d["name"] == "Reply-To":
                email = d["value"]
        if sender == os.getenv("SenderID") and "New order" in subject and "Re:" not in subject:
            # The message body is base64url encoded
            parts = payload.get("parts")[0]
            data = parts["body"]["data"]
            data = data.replace("-", "+").replace("_", "/")
            decoded_data = base64.b64decode(data)
            soup = BeautifulSoup(decoded_data, "lxml")
            body = soup.body()
            dict1 = {
                "Date": date, "Sender": sender, "Email": email,
                "Body": body, "Subject": subject, "Messsage_ID": msg["id"],
            }
            df2 = pd.DataFrame(dict1)
            df = pd.concat([df, df2], axis=0, ignore_index=True)
            df = df.drop_duplicates(subset=["Subject"], keep="first")

    if len(df) == 0:
        raise SystemExit
    df["Cleaned"] = df["Body"].astype(str).apply(clean_emails)
    logger.info("%s messages found", len(df))
    return df


def markEmailAsRead(creds, Message_ID):
    """Mark an email as read and tag it as processed by the auto-admin label."""
    service = build("gmail", "v1", credentials=creds)
    service.users().messages().modify(
        userId="me", id=Message_ID,
        body={"removeLabelIds": ["UNREAD"], "addLabelIds": [PROCESSED_LABEL_ID]},
    ).execute()


def starMesage(creds, Message_ID):
    """Star an email (used to flag on-hold bookings needing manual review)."""
    service = build("gmail", "v1", credentials=creds)
    service.users().messages().modify(
        userId="me", id=Message_ID, body={"addLabelIds": ["STARRED"]}
    ).execute()


def unstarMesage(creds, Message_ID):
    """Remove the star from an email once it has been resolved."""
    service = build("gmail", "v1", credentials=creds)
    service.users().messages().modify(
        userId="me", id=Message_ID, body={"removeLabelIds": ["STARRED"]}
    ).execute()


def gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt):
    """Send a threaded reply to the customer via the Gmail API."""
    try:
        service = build("gmail", "v1", credentials=creds)
        message = EmailMessage()
        message.set_content(txt)
        message["To"] = EMAIL
        message["From"] = CalID
        message["Subject"] = SUBJECT
        # Keep the reply in the same thread as the original enquiry
        message["In-Reply-To"] = MESSAGE_ID
        message["References"] = MESSAGE_ID
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}
        send_message = service.users().messages().send(
            userId="me", body=create_message
        ).execute()
    except HttpError as error:
        logger.error("An error occurred with sending message: %s", error)
        send_message = None
    return send_message
