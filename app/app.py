#getting all the intall requirements
#pip install -r requirements.txt

#Imports
import os
from flask import Flask, render_template, redirect, url_for, request
#for login
from flask_login import login_user, LoginManager, login_required
#for Google API connection
from google.oauth2 import service_account
#for secret key
import secrets

#loading .env file to access the passwords
from dotenv import load_dotenv  
load_dotenv()

#Variables & scopes etc to be used in various Google API callsc
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/calendar"]
service_auth_file = "admin-auth.json"
creds = service_account.Credentials.from_service_account_file(service_auth_file, scopes=SCOPES, subject=os.getenv('CalID'))

#getting all the functions from functions.py
from functions import *

#create app
app = Flask(__name__)
#getting the secret key from .env file
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(16))

#login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
#login user loader
@login_manager.user_loader
def load_user(username):
    return User()
#login User class
class User():
    def __init__(self):
        self.username = os.getenv('UserN')
        self.password = os.getenv('PassW')
    def is_active(self):
        return True
    def get_id(self):
        return self.username
    def is_authenticated(self):
        return True
    def is_anonymous(self):
        return False
    
#login page
@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        #verifying credentials without exposing environment variables
        if not (username == os.getenv('UserN') and password == os.getenv('PassW')):
            error = 'Invalid Credentials. Please try again.'
        else:
            user = User()
            login_user(user)
            return redirect(url_for('bookings'))
    return render_template('login.html', error=error)

# bookings page
@app.route('/bookings', methods=['GET'])
@login_required
def bookings():
  if request.method == 'GET' :
    cur, conn = connection()
    cur.execute("SELECT * FROM Bookings")
    lines = cur.fetchall()
    cur.close() 
    conn.close()  
    return render_template('bookings.html',rows=lines) 
  else:
    return render_template("bookings.html", error="Data not found")
  
#on hold page route
@app.route('/onhold', methods=['GET', 'POST'])
@login_required
def onhold():
  if request.method == 'GET' :
    cur, conn = connection()
    cur.execute("SELECT * FROM Bookings WHERE Status = 'ONHOLD'")
    lines = cur.fetchall()
    cur.close() 
    conn.close()
    return render_template('onhold.html',rows=lines) 
  elif request.method == 'POST' :
    status = request.form.get("status")
    ORDER = request.form.get("orderid")
    if status == "Accept":
      restartReturn(ORDER)
      return render_template("confirm.html")
    elif status == "Reject":
      rejectOrderReturn(ORDER)
      return render_template("cancel.html")
  else:
    return render_template("onhold.html", error="Data Error")

#confirmation page after booking is accepted
@app.route('/confirm')
@login_required
def confirm():  
  return render_template("confirm.html")

#cancel page after booking is rejected
@app.route('/cancel')
@login_required
def cancel():  
  return render_template("cancel.html")

#launching
if __name__ == "__main__":
  #only run directly like this if not production
  app.run(host="0.0.0.0", port=5000) 
  
