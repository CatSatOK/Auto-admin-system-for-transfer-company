###### Collection of the functions created for this app  ######

#pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

#getting all the intsall requirements
#pip install -r requirements.txt 

###IMPORTS###
#for database connection
import mysql.connector as mariadb
#general imports
import os
import re
import pandas as pd
import datefinder
from datetime import datetime, timedelta
#getEmail() function
from googleapiclient.discovery import build
from google.oauth2 import service_account
import base64
from bs4 import BeautifulSoup
#ner() function
import spacy
#mapTimings() function
import gmaps
import googlemaps
#gmailSendMessage() function
from email.message import EmailMessage
from googleapiclient.errors import HttpError
#sendAlert() function
import http.client, urllib
#sendInvoice() function
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

#loading .env file to access the passwords
from dotenv import load_dotenv  
load_dotenv()

#setting up basic logging
import logging
logger = logging.getLogger(name='mylogger')
logFileFormatter = logging.Formatter(
    fmt=f"""%(levelname)s %(asctime)s (%(relativeCreated)d)- 
    %(message)s- \t %(pathname)s F%(funcName)s L%(lineno)s""",
    datefmt="%Y-%m-%d %H:%M:%S",
)
fileHandler = logging.FileHandler(filename='logfile.log')
fileHandler.setFormatter(logFileFormatter)
fileHandler.setLevel(level=logging.DEBUG)
logger.addHandler(fileHandler)

####################################################
### CONNECTION FUNCTION
#This function connects to the database and returns the cursor and connection
def connection():
    #import mysql.connector as mariadb
    #getting login details from .env file
    DBuser = os.getenv('DBuser')
    DBpassword = os.getenv('DBpass')
    #connecting to the db
    conn = mariadb.connect(host='localhost', user=DBuser, password=DBpassword, database='bookingsdb')
    cur = conn.cursor()
    return cur, conn
    
####################################################
###GETTING EMAILS FUNCTION
#This function uses the Gmail API to fetch unread mesages from the inbox,
#returns a dataframe of the required information and uses
#the clean_emails() function to create a column of the cleaned email body

#the cleaning function
def clean_emails(text):
    text = re.sub('<[^<]+?>', ' ', text) #getting rid of html tags
    text = re.sub(r'http\S+', ' ', text) #removing urls
    text = re.sub(r'\r\n', ' ', text) #to remove \r\n 
    text = re.sub(r'\t', ' ', text)  #to remove \t
    text = re.sub(r'\x92', ' ', text)  #to remove \x92
    text = re.sub(r'&gt', ' ', text)  #to remove &gt
    text = re.sub(r';', ' ', text)  #to remove &gt
    text = re.sub(r'\n', ' ', text) #to remove \n 
    text = text.lower() #make all lowercase
    #text = re.sub(f"[{string.punctuation}]", " ", text) #get rid of puncutation    
    text = re. sub(r' +', ' ', text) #removing extra whitespce
    return text


#getting the data from email and returning it in df
def getEmails(creds):
    #making empty dataframe for results
    df = pd.DataFrame(columns = ['Date', 'Sender', 'Email', 'Body', 'Subject', 'Messsage_ID'])
    # Connect to the Gmail API
    service = build('gmail', 'v1', credentials=creds)
    # request a list of unread messages in inbox
    result = service.users().messages().list(userId='me', labelIds=['UNREAD'], q='in:inbox').execute()
    # create messages - a list of dictionaries where each dictionary contains a message id.
    messages = result.get('messages')
    #exit if no unread messages
    if type(messages) is not list: raise SystemExit

    # iterate through all the messages
    for msg in messages:
        # Get the message from its id
        txt = service.users().messages().get(userId='me', id=msg['id']).execute()
        # Get value of 'payload' from dictionary 'txt'
        payload = txt['payload']
        headers = payload['headers']
        # Look for Subject and Sender Email in the headers
        for d in headers:
            if d['name'] == 'Date':
                date = d['value']
            if d['name'] == 'Subject':
                subject = d['value']
            if d['name'] == 'From':
                sender = d['value']
            if d['name'] == 'Reply-To':
                email = d['value']
        #checking only looking at new booking request emails
        if sender == os.getenv('SenderID') and 'New order' in subject and 'Re:' not in subject:
            #Getting the data and decoding it with base 64 decoder (message Body is encrypted)
            parts = payload.get('parts')[0]
            data = parts['body']['data']
            data = data.replace("-","+").replace("_","/")
            decoded_data = base64.b64decode(data)
            #data is in lxml so parsing it with BeautifulSoup library
            soup = BeautifulSoup(decoded_data , "lxml")
            body = soup.body()
            #adding to df
            dict1 = {'Date': date, 'Sender' : sender, 'Email' : email, 'Body' : body, 'Subject' : subject, 'Messsage_ID' : msg['id']}
            df2 = pd.DataFrame(dict1)
            df = pd.concat([df, df2], axis=0, ignore_index=True)
            #dropping extra rows for the booking email
            df = df.drop_duplicates(subset=['Subject'], keep='first')

    #if df now empty - exit
    if len(df) == 0: raise SystemExit   
    #creating a cleaned emails column
    emails = df['Body'].astype(str) 
    cleaned = emails.apply(clean_emails)
    df['Cleaned'] = cleaned
    logger.info("%s messages found", len(df))
    return df

####################################################
###MARK EMAILS AS READ FUNCTION
#This takes the message id of the email and marks it as read and adds AutoAdmin label to it

def markEmailAsRead(creds, Message_ID):
    service = build('gmail', 'v1', credentials=creds)
    service.users().messages().modify(userId='me', id=Message_ID, body={'removeLabelIds': ['UNREAD'], 'addLabelIds': ['Label_3036548299999784630']}).execute()

####################################################
###STARRING EMAILS FUNCTION
#adds a star to On Hold Bookings emails
def starMesage(creds, Message_ID):
    service = build('gmail', 'v1', credentials=creds)
    service.users().messages().modify(userId='me', id=Message_ID, body={'addLabelIds': ['STARRED']}).execute()

####################################################
###UNSTARRING EMAILS FUNCTION
#adds a star to On Hold Bookings emails
def unstarMesage(creds, Message_ID):
    service = build('gmail', 'v1', credentials=creds)
    service.users().messages().modify(userId='me', id=Message_ID, body={'removeLabelIds': ['STARRED']}).execute()

####################################################
###APPLY MODEL FUNCTION
#This function applies the ner model to the cleaned email 
#and returns the variables required for other functions

def ner(email):
    #loading the model
    nlp = spacy.load("model-best-gpu") 
    doc = nlp(email)
    #creating global variables
    global ORDER, NAME, DATE, TIME, FROM, TO, EXTRAS, TOTAL, DEPOSIT, PAX, PHONE, DETAILS, ADDRESS
    ORDER = []
    NAME = []
    DATE = []
    TIME = []
    FROM = []
    TO = []
    EXTRAS = []
    TOTAL = []
    DEPOSIT = []
    PAX = []
    PHONE = []
    DETAILS = []
    ADDRESS = []
    #stocking the variables
    for ent in doc.ents:
        if (ent.label_ == 'ORDER'):
            ORDER.append(ent.text)
        elif (ent.label_ == 'PERSON'):
            NAME.append(ent.text)
        elif (ent.label_ == 'DATE'):
            DATE.append(ent.text)
        elif (ent.label_ == 'TIME'):
            TIME.append(ent.text)
        elif (ent.label_ == 'FROM'):
            FROM.append(ent.text)
        elif (ent.label_ == 'TO'):
            TO.append(ent.text)
        elif (ent.label_ == 'EXTRAS'):
            EXTRAS.append(ent.text)
        elif (ent.label_ == 'TOTAL'):
            TOTAL.append(ent.text)
        elif (ent.label_ == 'DEPOSIT'):
            DEPOSIT.append(ent.text)
        elif (ent.label_ == 'PAX'):
            PAX.append(ent.text)
        elif (ent.label_ == 'PHONE'):
            PHONE.append(ent.text)
        elif (ent.label_ == 'DETAILS'):
            DETAILS.append(ent.text)
        elif (ent.label_ == 'ADDRESS'):
            ADDRESS.append(ent.text)
        else:
            pass

    #making a dict of all the returned values
    values = [ORDER, NAME, DATE, TIME, FROM, TO, EXTRAS, TOTAL, DEPOSIT, PAX, PHONE, DETAILS, ADDRESS]
    keys = ['Order', 'Name', 'Date', 'Time', 'From', 'To', 'Extras', 'Total', 'Deposit', 'Pax', 'Phone', 'Details', 'Address']
    variables = dict(zip(keys, values))

    #checking if return booking (using several lists incase of NER errors) & loading variables
    lists = DATE, TIME, FROM, TO
    if all(len(l) == 1 for l in lists):
        #oneway booking
        for key in variables.keys():
            if key == 'Deposit':
                if len(variables[key]) == 0:
                    variables[key] = " "
                elif "deposit" in variables[key]:
                    variables[key] = [s for s in variables[key] if "deposit" in s][0]
                else:
                    variables[key] = "query"
            elif len(variables[key]) == 0:
                    variables[key] = " "
            else:
                variables[key] = variables[key][0]
        return variables
    elif all(len(l) == 2 for l in lists):
        #return booking
        variablesA = dict(zip(keys, values))
        variablesB = dict(zip(keys, values))
        for key in variablesA.keys():
            if key == 'Deposit':
                if len(variablesA[key]) == 0:
                    variablesA[key] = " "
                elif "deposit" in variablesA[key]:
                    variablesA[key] = [s for s in variablesA[key] if "deposit" in s][0]
                else:
                    variablesA[key] = "DEPOSIT QUERY"
            if len(variablesA[key]) == 0:
                variablesA[key] = " "
            else:
                variablesA[key] = variablesA[key][0]
        for key in variablesB.keys():
            if key == 'Deposit':
                if len(variablesB[key]) == 0:
                    variablesB[key] = " "
                elif "deposit" in variablesB[key]:
                    variablesB[key] = [s for s in variablesB[key] if "deposit" in s][0]
                else:
                    variablesB[key] = "DEPOSIT QUERY"
            if len(variablesB[key]) == 0:
                variablesB[key] = " "
            elif len(variablesB[key]) == 1:
                variablesB[key] = variablesB[key][0]
            elif len(variablesB[key]) == 2:
                variablesB[key] = variablesB[key][1]
            else:
                variablesB[key] = variablesB[key]
        return variablesA, variablesB
    else:
        #logging the details of the variables that failed
        logger.error("Data load fail details: %s", lists)
        return

####################################################
## STOP FUNCTION ********
# This function moves directly to calling the alert function if
# some conditions are met 

def extrasCheckSimple(PAX, DATE, TIME, EXTRAS):
    #luggage extras that require extra space
    extra_options = ['surfboards', 'golf bags', 'bicycles']
    #getting the PAX num as an int (so can check not over 8)
    num = [x for x in PAX.split() if x.isdigit()] 
    num = int(num[0])
    #find out of transfer in next 48hrs
    start_str = f'{DATE} {TIME}'
    datetime_object = datetime.strptime(start_str, '%d %B, %Y %H:%M')
    NUMBER_OF_SECONDS = 172800 #no. of sec in 48hrs
    today = datetime.now()
    #calling alert and stopping if any of the stop conditions are met
    if (any(map(EXTRAS.__contains__, extra_options))) or (num > 8):
        return 'EXTRAS_ISSUE'
    elif (datetime_object - today).total_seconds() < NUMBER_OF_SECONDS:
        return 'LAST_MIN_ISSUE'
    else:
        return

####################################################
###MAP CHECK FUNCTION
#This function uses the Google Maps API to get travel time

#function to get the api key
def gmapsAPI():
    with open('GMaps_api.txt') as f:
        api_key = f.readline()
        f.close
    gmaps.configure(api_key=api_key)
    return api_key

#function to get the travel time
def mapTimings(FROM, TO, start_str, api_key):
    gmaps = googlemaps.Client(key=api_key)
    #creating the datetime object from the details from email - used in stop function above
    datetime_object = datetime.strptime(start_str, '%d %B, %Y %H:%M')
    #getting the timings
    directions_results = gmaps.directions(FROM, TO, mode="driving", departure_time=datetime_object)
    TRAVEL_DISTANCE = directions_results[0]['legs'][0]['distance']['text']
    TRAVEL_TIME = directions_results[0]['legs'][0]['duration']['text']
    return TRAVEL_TIME


####################################################
###CHECK CALENDER - FREEBUSY FUNCTION
#This function uses the Google Calendar API to check if the required travel time is free

#function to get the duration of the transfer
def getDuration(time):
    #getting the time from the string
    dur = re.findall(r'\d+', time)
    #formatting it as a float for the calendar api
    if len(dur)>1:
        hrs = dur[0]
        mins= dur[1]
    else:
        hrs = 0
        mins= dur[0]
    hrs = int(hrs)
    mins = int(mins)
    return hrs, mins

#calendar check function 
def calendarCheckSimple(CalID, creds, start_str, hrs, mins):
    #building the service
    service = build('calendar', 'v3', credentials=creds)
    #getting the correct format for the start and end times
    matches = list(datefinder.find_dates(start_str))
    Start_time = matches[0]
    Start = Start_time.astimezone().isoformat() 
    #getting return trip time
    oneway = timedelta(hours=hrs, minutes=mins) 
    End_time = Start_time + (oneway*2)
    End = End_time.astimezone().isoformat()
    #creating request body
    body = {
        "timeMin": Start,
        "timeMax": End,
        "timeZone": 'Europe/Paris',
        "items": [{"id": CalID}]
        }
    #API call
    eventsResult = service.freebusy().query(body=body).execute()
    cal_dict = eventsResult[u'calendars']
    result = cal_dict.get(CalID, {}).get('busy')
    if len(result)>0:
        return False
    else:
        return True

###################################################
# GET ABBREVEATION FUNCTION
# This function takes the shorten name for the calendar entry title

def getAbbrevations(FROM, TO):
    destinations = [list destinations here you want to abbrevate]
    abbrevations = [list abbreviations here]
    if FROM in destinations:
        FROM = abbrevations[destinations.index(FROM)]
    if TO in destinations:
        TO = abbrevations[destinations.index(TO)]
    return FROM, TO
    
####################################################
###ADD TO CALENDER FUNCTION
#This function uses the Google Calendar API to create a TBC booking event for the transfer

def calendarAddEvent(creds, start_str, hrs, mins, calendar_entry, FROM, TO):
    FROM, TO = getAbbrevations(FROM, TO)
    TITLE = f'TBC {FROM} - {TO}'
    #create service - same as in calendarCheck() ****COMBINE THESE TWO FUNCTIONS ?
    service = build('calendar', 'v3', credentials=creds)
    matches = list(datefinder.find_dates(start_str))
    if len(matches):
        start_time = matches[0]
        oneway = timedelta(hours=hrs, minutes=mins) 
        end_time = start_time + (oneway*2) #*2 to allow for return
    event = {
        'summary': TITLE,
        'location': TO,
        'description': calendar_entry,
        'start': {
            'dateTime': start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            'timeZone': 'Europe/Paris',
        },
        'end': {
            'dateTime': end_time.strftime("%Y-%m-%dT%H:%M:%S"),
            'timeZone': 'Europe/Paris',
        },
        'reminders': {
            'useDefault': True
        },
    }
    return service.events().insert(calendarId='primary', body=event).execute()


####################################################
###SEND EMAIL FUNCTION
#This function uses the GMail API to send an email to the customer
#either to say we can do the transfer and invoice will be sent
#or to say we will get back to them (in the case where not currently free or its last minute)

def gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt):
    try:
        #build service
        service = build('gmail', 'v1', credentials=creds)
        message = EmailMessage()
        message.set_content(txt)
        #set meassage details
        message['To'] = EMAIL
        message['From'] = CalID
        message['Subject'] = SUBJECT
        #need to add these to get the message to be a thread with previous email (subjects also need to match)
        message['In-Reply-To'] =  MESSAGE_ID
        message['References'] = MESSAGE_ID
        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()) \
            .decode()
        #creating the message object
        create_message = {
            'raw': encoded_message
        }
        send_message = (service.users().messages().send
                        (userId="me", body=create_message).execute())
    except HttpError as error:
        logger.error("An error occurred with sending message: %s", error)
        send_message = None
    #returning the message object
    return send_message

####################################################
### ALERT FUNCTION
#This function uses the Pushover API to send a notification to the owners phone
#to alert them of request for next 2 days or one we are currently not available for

def sendAlert(PushToken, user, msg):
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
    urllib.parse.urlencode({
        "token": PushToken, 
        "user": user, 
        "message": msg,
    }), { "Content-type": "application/x-www-form-urlencoded" })
    conn.getresponse()

####################################################
## ADD TO DATABASE FUNCTION
# This function adds the new booking enquiry to the database 

def addToDatabase(ORDER, DATE, TIME, FROM, TO, NAME, PAX, TOTAL, DEPOSIT, PHONE, EXTRAS, DETAILS, ADDRESS, BODY, EMAIL, MESSAGE_ID, STATUS):
    #connecting to the bookingddb database
    cur, conn = connection()
    #creating the table - not required as already created
    #cur.execute("CREATE TABLE IF NOT EXISTS Bookings (`Order` VARCHAR(10) NOT NULL UNIQUE, Date VARCHAR(30) NOT NULL, Time VARCHAR(10) NOT NULL, `From` VARCHAR(60) NOT NULL, `To` VARCHAR(60) NOT NULL, Name VARCHAR(100) NOT NULL, Pax VARCHAR(30) NOT NULL, Total VARCHAR(50) NOT NULL, Deposit VARCHAR(50), Phone VARCHAR(30), Extras VARCHAR(200), Details VARCHAR(100), Address VARCHAR(200), `Body` VARCHAR(1000) NOT NULL, Email VARCHAR(80) NOT NULL, Message_ID VARCHAR(20) NOT NULL, Status VARCHAR(20) NOT NULL, Corp_Client_ID INT, FOREIGN KEY (Corp_Client_ID) REFERENCES Corporate_clients(Customer_ID))")
    #checking if corporate client and if so getting the ID
    cur.execute("SELECT Customer_ID FROM Corporate_clients WHERE Customer_Email = %s", (EMAIL,))
    CORP_ID = cur.fetchone()
    if CORP_ID is not None:
        CORP_ID = CORP_ID[0]  
    # Insert booking into Bookings table with Corp_Cust_ID value
    cur.execute("INSERT INTO Bookings (`Order`, Date, Time, `From`, `To`, Name, Pax, Total, Deposit, Phone, Extras, Details, Address, `Body`, Email, Message_ID, Status, Corp_Client_ID) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (ORDER, DATE, TIME, FROM, TO, NAME, PAX, TOTAL, DEPOSIT, PHONE, EXTRAS, DETAILS, ADDRESS, BODY, EMAIL, MESSAGE_ID, STATUS, CORP_ID))
    conn.commit()

####################################################
## DELETE OLD PAST BOOKINGS FROM DB FUNCTION
#This function deletes all bookings where the transfer date has passed
#**not used yet (awaiting lead confirmation)- should be run once a day - make seperate cron job for this?

def deletePassedBookings():
    #connecting to the database
    cur, conn = connection()
    #deleting the data
    #may need format for comparison to CURDATE - '%d-%m-%Y'
    cur.execute("DELETE FROM Bookings WHERE STR_TO_DATE(Date, '%d %B, %Y') < CURDATE()")
    conn.commit()

####################################################
## UPDATE STATUS FUNCTION
#These function updates the booking status in the database

def updateStatus(ORDER, STATUS_UPDATED):
    #connecting to the db
    cur, conn = connection()
    #update status in database
    query = """UPDATE Bookings SET Status = %s WHERE `Order`= %s"""
    tup = (STATUS_UPDATED, ORDER)
    cur.execute(query, tup)
    conn.commit()

####################################################
## RESTART FUNCTION (covers return transfers)
#run when James clicks the accept button in app to confirm the booking

def restartReturn(ORDER):
    #variables
    CalID = os.getenv('CalID')
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/calendar"]
    creds = service_account.Credentials.from_service_account_file("admin-auth.json", scopes=SCOPES, subject=CalID)
    endings = ["-A", "-B"]
    reg =re.compile('|'.join(endings))
    cur, conn = connection()

    #finding out if its a return or oneway
    if reg.search(ORDER):
        #****** RETURN ROUTE **************************
        A = re.compile('|'.join('-A'))
        if A.search(ORDER):
            #getting the different order numbers
            ORDER_A = ORDER
            ORDER_B = ORDER.replace("-A", "-B")
            ORDER_orig = ORDER.replace("-A", "")
        else:
            #dealing with transfer B
            ORDER_B = ORDER
            ORDER_A = ORDER.replace("-B", "-A")
            ORDER_orig = ORDER.replace("-B", "")

        #ORDER_A details from database
        cur.execute(f"""SELECT * FROM Bookings WHERE `Order`= %s""", (ORDER_A,))
        #get the results
        results = cur.fetchall()
        #assign the results to variables
        DATE_A = results[0][1]
        TIME_A = results[0][2]
        FROM_A = results[0][3]
        TO_A = results[0][4]
        NAME_A = results[0][5]
        PAX_A = results[0][6]
        TOTAL_A = results[0][7]
        DEPOSIT_A = results[0][8]
        PHONE_A = results[0][9]
        EXTRAS_A = results[0][10]
        DETAILS_A = results[0][11]
        ADDRESS_A = results[0][12]
        BODY_A = results[0][13]
        EMAIL_A = results[0][14]
        MESSAGE_ID_A = results[0][15]

        #other variable creation - used in other functions but created again here so stand alone
        start_str_A = f'{DATE_A} {TIME_A}'
        api_key = gmapsAPI()
        time_A = mapTimings(FROM_A, TO_A, start_str_A, api_key)
        hrs_A, mins_A = getDuration(time_A)
        calendar_entry_A = f"""
Order no: {ORDER_orig},
{NAME_A}, {PAX_A}, 
Phone: {PHONE_A},
Total: {TOTAL_A}, 
Deposit: {DEPOSIT_A},  
Extras: {EXTRAS_A}, 
Notes: {DETAILS_A}, 
Address: {ADDRESS_A}

Email body:
{BODY_A}
"""
        
        #ORDER_B details from database
        cur.execute(f"""SELECT * FROM Bookings WHERE `Order`= %s""", (ORDER_B,))
        #get the results
        results = cur.fetchall()
        #assign the results to variables
        DATE_B = results[0][1]
        TIME_B = results[0][2]
        FROM_B = results[0][3]
        TO_B = results[0][4]
        NAME_B = results[0][5]
        PAX_B = results[0][6]
        TOTAL_B = results[0][7]
        DEPOSIT_B = results[0][8]
        PHONE_B = results[0][9]
        EXTRAS_B = results[0][10]
        DETAILS_B = results[0][11]
        ADDRESS_B = results[0][12]
        BODY_B = results[0][13]
        EMAIL_B = results[0][14]
        MESSAGE_ID_B = results[0][15]

        #other variable creation - used in other functions but created again here so stand alone
        start_str_B = f'{DATE_B} {TIME_B}'
        api_key = gmapsAPI()
        time_B = mapTimings(FROM_B, TO_B, start_str_B, api_key)
        hrs_B, mins_B = getDuration(time_B)
        calendar_entry_B = f"""
Order no: {ORDER_orig},
{NAME_B}, {PAX_B}, 
Phone: {PHONE_B},
Total: {TOTAL_B}, 
Deposit: {DEPOSIT_B},  
Extras: {EXTRAS_B}, 
Notes: {DETAILS_B}, 
Address: {ADDRESS_B}

Email body:
{BODY_B}
"""
        
        #add both to calendar
        calendarAddEvent(creds, start_str_A, hrs_A, mins_A, calendar_entry_A, FROM_A, TO_A)
        calendarAddEvent(creds, start_str_B, hrs_B, mins_B, calendar_entry_B, FROM_B, TO_B)
        #send one email
        available_email_return = f"""
Hello {NAME_A}, 

#ADD EMAIL TEXT HERE
"""
        SUBJECT_R = f"RE: Transfers Enquiry no: {ORDER_orig}"
        gmailSendMessage(CalID, creds, EMAIL_A, SUBJECT_R, MESSAGE_ID_A, txt=available_email_return)
        unstarMesage(creds, MESSAGE_ID_A)
        #send invoice
        sendInvoice(ORDER_orig) 
        #updating status in database
        updateStatus(ORDER_A, 'INVOICED')
        updateStatus(ORDER_B, 'INVOICED')
    else:
        #****** ONEWAY ROUTE **************************
        #get all the order details from database
        cur.execute(f"""SELECT * FROM Bookings WHERE `Order`= %s""", (ORDER,))
        #get the results
        results = cur.fetchall()
        #assign the results to variables
        DATE = results[0][1]
        TIME = results[0][2]
        FROM = results[0][3]
        TO = results[0][4]
        NAME = results[0][5]
        PAX = results[0][6]
        TOTAL = results[0][7]
        DEPOSIT = results[0][8]
        PHONE = results[0][9]
        EXTRAS = results[0][10]
        DETAILS = results[0][11]
        ADDRESS = results[0][12]
        BODY = results[0][13]
        EMAIL = results[0][14]
        MESSAGE_ID = results[0][15]
        #other variable creation - used in other functions but created again here so stand alone
        start_str = f'{DATE} {TIME}'
        api_key = gmapsAPI()
        time = mapTimings(FROM, TO, start_str, api_key)
        hrs, mins = getDuration(time)
        SUBJECT = f"RE: BTransfers Enquiry no: {ORDER}"
        calendar_entry = f"""
Order no: {ORDER},
{NAME}, {PAX}, 
Phone: {PHONE},
Total: {TOTAL}, 
Deposit: {DEPOSIT},  
Extras: {EXTRAS}, 
Notes: {DETAILS}, 
Address: {ADDRESS}

Email body:
{BODY}
"""
        available_email = f"""
Hello {NAME}, 

#ADD EMAIL TEXT HERE
"""
        
        #add to calendar
        calendarAddEvent(creds, start_str, hrs, mins, calendar_entry, FROM, TO)
        #send email
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=available_email)
        unstarMesage(creds, MESSAGE_ID)
        #send invoice
        sendInvoice(ORDER) 
        #updating status in database
        updateStatus(ORDER, 'INVOICED')

    cur.close()
    conn.close()
    #raise exit

####################################################
## CANCEL FUNCTION (covers return jobs )
#This function restarts from calendarAddEvent() if James clicks Reject on app

def rejectOrderReturn(ORDER):
    #variables
    CalID = os.getenv('CalID')
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/calendar"]
    creds = service_account.Credentials.from_service_account_file("admin-auth.json", scopes=SCOPES, subject=CalID)
    #finding out if its a return or oneway
    endings = ["-A", "-B"]
    reg =re.compile('|'.join(endings))
    cur, conn = connection()

    if reg.search(ORDER):
        #****** RETURN ROUTE **************************
        A = re.compile('|'.join('-A'))
        if A.search(ORDER):
            #getting the different order numbers
            ORDER_A = ORDER
            ORDER_B = ORDER.replace("-A", "-B")
            ORDER_orig = ORDER.replace("-A", "")
        else:
            #dealing with transfer B
            ORDER_B = ORDER
            ORDER_A = ORDER.replace("-B", "-A")
            ORDER_orig = ORDER.replace("-B", "")
                
        #ORDER_A details
        cur.execute(f"""SELECT * FROM Bookings WHERE `Order`= %s""", (ORDER_A,))
        #get the results
        results = cur.fetchall()
        #assign the results to variables
        NAME_A = results[0][5]
        EMAIL_A = results[0][14]
        MESSAGE_ID_A = results[0][15]
        #dont need order_B details

        SUBJECT_return = f"RE: Transfers Enquiry no: {ORDER_orig}"
        cancel_email_return = f"""
Hello {NAME_A},
#ADD EMAIL TEXT HERE
"""
        #send email
        gmailSendMessage(CalID, creds, EMAIL_A, SUBJECT_return, MESSAGE_ID_A, txt=cancel_email_return)
        #update the status in the booking database
        updateStatus(ORDER_A, "CANCELLED")
        updateStatus(ORDER_B, "CANCELLED")

    else:
        #****** ONEWAY ROUTE **************************
        #get all the order details from database
        cur, conn = connection() #connecting to the db - may not be required ??
        cur.execute(f"""SELECT * FROM Bookings WHERE `Order`= %s""", (ORDER,))
        #get the results
        results = cur.fetchall()
        #assign the results to variables
        NAME = results[0][1]
        DATE = results[0][2]
        EMAIL = results[0][14]
        MESSAGE_ID = results[0][15]

        SUBJECT = f"RE: Transfers Enquiry no: {ORDER}"
        cancel_email = f"""
Hello {NAME},

#ADD EMAIL TEXT HERE
"""
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=cancel_email)
        #update the status in the booking database
        updateStatus(ORDER, "CANCELLED")

    #close connection 
    cur.close()
    conn.close()
    #raise exit

#######################################################
### SEND INVOICE FUNCTION
#This function uses selenium to sends the invoice to the customer via WordPress

def sendInvoice(ORDER):
    #getting just the number from ORDER
    ORDER_UPDATED = re.findall(r'\d+', ORDER)[0]

    #driver = webdriver.Chrome()
    #getting rid of unnecesary logging warning
    options = webdriver.ChromeOptions()
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    driver = webdriver.Chrome(options=options)

    #going to WP login page
    driver.get(os.getenv('WPlogin')) 
    #entering log in details
    username = driver.find_element('xpath', '//*[@id="user_login"]')
    username.send_keys(os.getenv('WPuser'))
    passw = driver.find_element('xpath', '//*[@id="user_pass"]')
    passw.send_keys(os.getenv('WPpass'))
    #logging in
    driver.find_element('xpath', '//*[@id="wp-submit"]').click()
    #going thru the various links to get to the required order
    driver.find_element('xpath', '//*[@id="toplevel_page_woocommerce"]/a/div[3]').click() #opening woocom page
    driver.find_element('xpath', '//*[@id="toplevel_page_woocommerce"]/ul/li[3]/a').click() #opening orders page
    driver.find_element('xpath', f'//*[@id="post-{ORDER_UPDATED}"]/td[1]/a[2]/strong').click() #opening specific order
    #updating order status
    status = Select(driver.find_element(By.ID, "order_status")) 
    status.select_by_index(0) #changing status to Pending Payment
    button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="woocommerce-order-actions"]/div[2]/ul/li[2]/button'))) #dealing with delay in loading
    #driver.find_element('xpath', '//*[@id="woocommerce-order-actions"]/div[2]/ul/li[2]/button').click() #pressing the update button
    button.click() #pressing the update button
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "wc_order_action"))) #dealing with delay in loading
    #sending the invoice
    action = Select(driver.find_element(By.NAME, "wc_order_action")) 
    action.select_by_index(1) #selecting to email an invoice
    driver.find_element('xpath', '//*[@id="actions"]/button').click() #sending the invoice
    #exiting and closing the window
    driver.quit()


####################################################
### ONE WAY BOOKING PATH FUNCTION
#This function is used to process one way booking requests

def oneWayPath(data, BODY, STATUS, PushToken, James, CalID, creds, EMAIL,MESSAGE_ID):
    ORDER, NAME, DATE, TIME, FROM, TO, PAX, TOTAL, DEPOSIT, PHONE, EXTRAS, DETAILS, ADDRESS = map(data.get, ('Order', 'Name', 'Date', 'Time', 'From', 'To', 'Pax', 'Total', 'Deposit', 'Phone', 'Extras', 'Details', 'Address'))
    #add to database
    addToDatabase(ORDER, DATE, TIME, FROM, TO, NAME, PAX, TOTAL, DEPOSIT, PHONE, EXTRAS, DETAILS, ADDRESS, BODY, EMAIL, MESSAGE_ID, STATUS)
    #templates for alerts, emails etc used in oneway extras checks
    busy_email = f"""
Hello {NAME}, 

#ADD EMAIL TEXT HERE
"""
    SUBJECT = f"RE: Transfers Enquiry no: {ORDER}"
    last_min = f"Last minute enquiry received (order {ORDER}), please check : LINK TO ONHOLD PAGE"
    extras = f"Enquiry that requires extra checks recieved (order {ORDER}), please check : LINK TO ONHOLD PAGE"
    checks = extrasCheckSimple(PAX, DATE, TIME, EXTRAS)
    #checks & availability results
    if checks == 'EXTRAS_ISSUE':
        sendAlert(PushToken, James, extras) #call alert function
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, busy_email)#email client
        updateStatus(ORDER, 'ONHOLD') 
        starMesage(creds, MESSAGE_ID)
        return
    if checks == 'LAST_MINUTE':
        sendAlert(PushToken, James, last_min) #call alert function
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, busy_email)#email client
        updateStatus(ORDER, 'ONHOLD')
        starMesage(creds, MESSAGE_ID)
        return
    #check calendar for availability (includes map check)
    api_key = gmapsAPI()
    start_str = f'{DATE} {TIME}'
    time = mapTimings(FROM, TO, start_str, api_key)
    hrs, mins = getDuration(time)
    unavailable = f"Enquiry received for time when currently unavailable (order {ORDER}), please check : LINK TO ONHOLD PAGE"
    calcheck = calendarCheckSimple(CalID, creds, start_str, hrs, mins)
    if calcheck == False:
        sendAlert(PushToken, James, unavailable) #call alert function
        gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, busy_email)#email client
        updateStatus(ORDER, 'ONHOLD') 
        starMesage(creds, MESSAGE_ID)
        return
    #if all ok - add to calendar
    calendar_entry = f"""
Order no: {ORDER},
{NAME}, {PAX}, 
Phone: {PHONE},
Total: {TOTAL}, 
Deposit: {DEPOSIT},  
Extras: {EXTRAS}, 
Notes: {DETAILS}, 
Address: {ADDRESS}

Email body:
{BODY}
"""
    calendarAddEvent(creds, start_str, hrs, mins, calendar_entry, FROM, TO)
    #send availability email
    available_email = f"""
Hello {NAME}, 

#ADD EMAIL TEXT HERE
"""
    gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=available_email)
    #send invoice
    sendInvoice(ORDER) 
    #updating status in database
    updateStatus(ORDER, 'INVOICED')
    return

####################################################
### RETURN BOOKING PATH FUNCTION
#This function is used to process return booking requests

def returnPath(data, BODY, STATUS, PushToken, James, CalID, creds, EMAIL, MESSAGE_ID):
    #get variables and complete up to calendar check for Transfer A
        ORDER_A, NAME, DATE_A, TIME_A, FROM_A, TO_A, PAX_A, TOTAL, DEPOSIT, PHONE, EXTRAS_A, DETAILS_A, ADDRESS_A = map(data[0].get, ('Order', 'Name', 'Date', 'Time', 'From', 'To', 'Pax', 'Total', 'Deposit', 'Phone', 'Extras', 'Details', 'Address'))
        ORDER_orig = ORDER_A
        ORDER_A = f"{ORDER_A}-A" #giving both legs of transfer a unique order number
        #add to database
        addToDatabase(ORDER=ORDER_A, DATE=DATE_A, TIME=TIME_A, FROM=FROM_A, TO=TO_A, NAME=NAME, PAX=PAX_A, TOTAL=TOTAL, DEPOSIT=DEPOSIT, PHONE=PHONE, EXTRAS=EXTRAS_A, DETAILS=DETAILS_A, ADDRESS=ADDRESS_A, BODY=BODY, EMAIL=EMAIL, MESSAGE_ID=MESSAGE_ID, STATUS=STATUS)
        #check for extra etc
        Achecks = extrasCheckSimple(PAX=PAX_A, DATE=DATE_A, TIME=TIME_A, EXTRAS=EXTRAS_A)
        #check calendar for availability (includes map check)
        api_key = gmapsAPI()
        start_str_A = f'{DATE_A} {TIME_A}'
        time_A = mapTimings(FROM_A, TO_A, start_str_A, api_key)
        hrs_A, mins_A = getDuration(time_A)
        Acalcheck = calendarCheckSimple(CalID, creds, start_str_A, hrs_A, mins_A)

        #get variables and complete up to calendar check for Transfer B
        ORDER_B, NAME, DATE_B, TIME_B, FROM_B, TO_B, PAX_B, TOTAL, DEPOSIT, PHONE, EXTRAS_B, DETAILS_B, ADDRESS_B = map(data[1].get, ('Order', 'Name', 'Date', 'Time', 'From', 'To', 'Pax', 'Total', 'Deposit', 'Phone', 'Extras', 'Details', 'Address'))
        ORDER_B = f"{ORDER_B}-B" #giving both legs of transfer a unique order number
        #add to database
        addToDatabase(ORDER=ORDER_B, DATE=DATE_B, TIME=TIME_B, FROM=FROM_B, TO=TO_B, NAME=NAME, PAX=PAX_B, TOTAL=TOTAL, DEPOSIT=DEPOSIT, PHONE=PHONE, EXTRAS=EXTRAS_B, DETAILS=DETAILS_B, ADDRESS=ADDRESS_B, BODY=BODY, EMAIL=EMAIL, MESSAGE_ID=MESSAGE_ID, STATUS=STATUS)
        #check for extra etc
        Bchecks = extrasCheckSimple(PAX=PAX_B, DATE=DATE_B, TIME=TIME_B, EXTRAS=EXTRAS_B)
        #check calendar for availability (includes map check)
        api_key = gmapsAPI()
        start_str_B = f'{DATE_B} {TIME_B}'
        time_B = mapTimings(FROM_B, TO_B, start_str_B, api_key)
        hrs_B, mins_B = getDuration(time_B)
        Bcalcheck = calendarCheckSimple(CalID, creds, start_str_B, hrs_B, mins_B)

        #alert & email templates for return bookings
        SUBJECT = f"RE: Transfers Enquiry no: {ORDER_orig}"
        busy_email_return = f"""
Hello {NAME}, 

#ADD EMAIL TEXT HERE
"""
        last_min = f"Last minute enquiry received (order {ORDER_orig}), please check : LINK TO ONHOLD PAGE"
        extras = f"Enquiry that requires extra checks recieved (order {ORDER_orig}), please check : LINK TO ONHOLD PAGE"
        unavailable = f"Enquiry received for time when currently unavailable (order {ORDER_orig}: A or B), please check : LINK TO ONHOLD PAGE"
        
        #checking if there are any issues with either transfer
        if Achecks == 'EXTRAS_ISSUE' or Bchecks == 'EXTRAS_ISSUE':
            sendAlert(PushToken, James, extras) #call alert function
            gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=busy_email_return)#email client
            starMesage(creds, MESSAGE_ID)
            updateStatus(ORDER_A, 'ONHOLD')
            updateStatus(ORDER_B, 'ONHOLD')
            return
        elif Achecks == 'LAST_MIN_ISSUE' or Bchecks == 'LAST_MIN_ISSUE':
            sendAlert(PushToken, James, last_min) #call alert function
            gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=busy_email_return)#email client
            starMesage(creds, MESSAGE_ID)
            updateStatus(ORDER_A, 'ONHOLD') 
            updateStatus(ORDER_B, 'ONHOLD')
            return
        #confirming if available for both transfers
        if Acalcheck == False or Bcalcheck == False:
            sendAlert(PushToken, James, unavailable) #call alert function
            gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=busy_email_return)#email client
            starMesage(creds, MESSAGE_ID)
            updateStatus(ORDER_A, 'ONHOLD') 
            updateStatus(ORDER_B, 'ONHOLD')
            return
        #if both are fine then add to calendar
        if Acalcheck == True and Bcalcheck == True:
            #adding TransferB
            calendar_entry_B = f"""
Order no: {ORDER_B},
{NAME}, {PAX_B}, 
Phone: {PHONE},
Total: {TOTAL}, 
Deposit: {DEPOSIT},  
Extras: {EXTRAS_B}, 
Notes: {DETAILS_B}, 
Address: {ADDRESS_B}

RETURN BOOKING - ORIGINAL TRANSFER {DATE_A}

Email body:
{BODY}
"""
            calendarAddEvent(creds, start_str_B, hrs_B, mins_B, calendar_entry_B, FROM_B, TO_B)
            #adding TransferA 
            calendar_entry_A = f"""
Order no: {ORDER_A}
{NAME}, {PAX_A}, 
Phone: {PHONE},
Total: {TOTAL}, 
Deposit: {DEPOSIT},  
Extras: {EXTRAS_A}, 
Notes: {DETAILS_A}, 
Address: {ADDRESS_A}

RETURN BOOKING - SECOND TRANSFER {DATE_B}

Email body:
{BODY}
"""
            calendarAddEvent(creds, start_str_A, hrs_A, mins_A, calendar_entry_A, FROM_A, TO_A)
            #send availability email
            available_email_return = f"""
Hello {NAME}, 

#ADD EMAIL TEXT HERE
"""
            gmailSendMessage(CalID, creds, EMAIL, SUBJECT, MESSAGE_ID, txt=available_email_return)
            #send invoice
            sendInvoice(ORDER_orig) 
            #updating status for both legs in database
            updateStatus(ORDER_A, 'INVOICED')
            updateStatus(ORDER_B, 'INVOICED')
            return
