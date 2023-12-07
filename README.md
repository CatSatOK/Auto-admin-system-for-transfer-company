# Auto-admin-system-for-transfer-company
General steps to the automated proces:
- any unread emails are downloaded from Gmail
- if they are booking requests, the custom NER model is applied to get the necesssary booking details
- availability is checking via Google Calendar
- if available the booking is added, an invoice created and the client emailed, if not available the staff are alerted to check the booking
- onhold bookings can be accepted or rejected via the webapp
- all bookings and their current status stored in database
- invoices created via Selenium and their WordPress site
 

NER model creation file is steps to follow to create a custom NER 
functions.py as all the function created for this program
scheduled_auto_admin.py is the automated admin process, called every 10min via crontab
health_check.py is a daily check run via cron to check site is running
app.py is the web app 
