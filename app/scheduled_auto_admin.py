#getting all the intall requirements
#pip install -r requirements.txt 

#loading .env file to access the passwords
from dotenv import load_dotenv  
load_dotenv()

#Variables & scopes etc to be used in various Google API callsc
from google.oauth2 import service_account
import os
CalID = os.getenv('CalID') #getting id email from .env file
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", 
          "https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/calendar"]
service_auth_file = "bat-admin-auth.json"
creds = service_account.Credentials.from_service_account_file(service_auth_file, scopes=SCOPES, subject=CalID)


#getting all the functions I created for this project
from functions import *

#connecting to the bookingddb database 
cur, conn = connection()

#getting the emails & saving the variables
df = getEmails(creds) 

#required variables
STATUS = "TBC" #holder status until have results - then ONHOLD or INVOICED 
#alert settings
James = os.getenv("PushJames")
PushToken = os.getenv("PushToken")

##### ALLOWING FOR MULTIPLE EMAILS ####
print(len(df), "messages found")
for e in df.index:
    MESSAGE_ID = df['Messsage_ID'][e]
    EMAIL = df['Email'][e]
    BODY = df['Cleaned'][e]
    #marking email as read and labelling it as processed by AutoAdmin
    markEmailAsRead(creds, MESSAGE_ID)
    #error messsage template
    error = f"Error procesing a booking enquiry, please check : LINK TO ONHOLD PAGE"
    #applying the ner model
    data = ner(BODY)
    #dealing with ner result errors
    if data is None:
        starMesage(creds, MESSAGE_ID)
        #sending hold email to client
        busy_email = f"""
Hello, 

#ADD EMAIL TEXT HERE
"""
        subject = "Transfers enquiry"
        gmailSendMessage(CalID, creds, EMAIL, subject, MESSAGE_ID, busy_email)
        #logging details of which email has the error
        logger.error("Data load fail on email from: %s", EMAIL)
        #alerting James
        sendAlert(PushToken, James, error)
        continue    

    #### RETURN BOOKING PATH ####
    if len(data) == 2:
        returnPath(data, BODY, STATUS, PushToken, James, CalID, creds, EMAIL, MESSAGE_ID)

    #### ONEWAY BOOKING PATH #####
    elif len(data) != 2:
        oneWayPath(data, BODY, STATUS, PushToken, James, CalID, creds, EMAIL,MESSAGE_ID)

##### EXIT ONCE ALL BOOKING EMAILS HAVE BEEN DEALT WITH #####
#closing datatbase connection
try:
    cur.close()
    conn.close()
except Exception as e:
    logger.error("Error closing the database connection: %s", e)
#exiting program
raise SystemExit

