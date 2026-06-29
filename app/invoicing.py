"""WooCommerce/WordPress invoicing via Selenium browser automation.

The transfer company's invoicing lives in WooCommerce with no public API, so the
invoice is sent by driving the WordPress admin UI: log in, open the order, set it
to 'Pending Payment', and trigger the 'email invoice' order action.
"""

import os
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


def sendInvoice(ORDER):
    """Email the customer their invoice by automating the WooCommerce admin."""
    order_number = re.findall(r"\d+", ORDER)[0]

    options = webdriver.ChromeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    driver = webdriver.Chrome(options=options)
    try:
        # Log in to WordPress admin
        driver.get(os.getenv("WPlogin"))
        driver.find_element("xpath", '//*[@id="user_login"]').send_keys(os.getenv("WPuser"))
        driver.find_element("xpath", '//*[@id="user_pass"]').send_keys(os.getenv("WPpass"))
        driver.find_element("xpath", '//*[@id="wp-submit"]').click()

        # Navigate WooCommerce -> Orders -> this order
        driver.find_element("xpath", '//*[@id="toplevel_page_woocommerce"]/a/div[3]').click()
        driver.find_element("xpath", '//*[@id="toplevel_page_woocommerce"]/ul/li[3]/a').click()
        driver.find_element(
            "xpath", f'//*[@id="post-{order_number}"]/td[1]/a[2]/strong'
        ).click()

        # Set status to Pending Payment and save
        Select(driver.find_element(By.ID, "order_status")).select_by_index(0)
        button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable(
                (By.XPATH, '//*[@id="woocommerce-order-actions"]/div[2]/ul/li[2]/button')
            )
        )
        button.click()

        # Trigger the 'email invoice' order action
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.NAME, "wc_order_action"))
        )
        Select(driver.find_element(By.NAME, "wc_order_action")).select_by_index(1)
        driver.find_element("xpath", '//*[@id="actions"]/button').click()
    finally:
        driver.quit()
