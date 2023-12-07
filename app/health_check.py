import requests
import os
from functions import logger, sendAlert

#site health check function - run daily via crontab
def site_check(url='http://127.0.0.1:8080/', max_response_time=3):
    try:
        response = requests.get(url, timeout=max_response_time)
        status_code = response.status_code
        response_time = response.elapsed.total_seconds()

        if status_code == 200 and response_time < max_response_time:
            logger.info("Website health good")
            return True
        else:
            #send alert if site is down
            logger.error("Website loading issue found. Status code: %s, Response time: %s", 
                         status_code, response_time)
            sendAlert(PushToken=os.getenv("PushToken"), user=os.getenv("PushJames"), 
                      msg="Website loading issue found, check logfile")
            return False
    except requests.RequestException as e:
        logger.error("Error during site check: %s", e)
        sendAlert(PushToken=os.getenv("PushToken"), user=os.getenv("PushJames"), 
                  msg="Error during site check, check logfile")
        return False


if __name__ == "__main__":
    site_check()

