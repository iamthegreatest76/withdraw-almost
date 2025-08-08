# selenium_interface.py

from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
import time
from main import driver, hash_row_data  # use your running Selenium session

def refresh_page_and_wait():
    try:
        refresh_btn = driver.find_element(By.XPATH, '//button[contains(text(),"Refresh")]')
        refresh_btn.click()
    except Exception as e:
        print(f"⚠️ Could not click refresh: {e}")

    loader_xpath = '//div[contains(@class,"loader") and contains(.,"Loading please wait")]'
    timeout = time.time() + 15
    while time.time() < timeout:
        try:
            if not driver.find_elements(By.XPATH, loader_xpath):
                break
            time.sleep(0.5)
        except StaleElementReferenceException:
            break

def find_row_by_ref_and_hash(ref_id, expected_hash):
    rows = driver.find_elements(By.XPATH, '//div[contains(@class,"ag-center-cols-container")]/div[@role="row"]')
    for row in rows:
        try:
            cells = row.find_elements(By.XPATH, './/div[@role="gridcell"]')
            if len(cells) < 13:
                continue

            transfer_id = cells[12].text.strip()
            if transfer_id != ref_id:
                continue

            amount = cells[6].text.strip()
            acc_no = cells[9].text.strip()
            ifsc = cells[11].text.strip()
            row_hash = hash_row_data(transfer_id, amount, acc_no, ifsc)
            if row_hash == expected_hash:
                return row
        except Exception as e:
            print(f"⚠️ Error parsing row: {e}")
            continue
    return None

def approve_transaction(ref_id, expected_hash, utr):
    print("🔍 Attempting Selenium Approve")
    refresh_page_and_wait()
    row = find_row_by_ref_and_hash(ref_id, expected_hash)
    if not row:
        return False, "❌ Row not found or hash mismatch"

    try:
        approve_button = row.find_element(By.XPATH, './/button[1]')
        approve_button.click()
        time.sleep(1)

        utr_input = driver.find_element(By.XPATH, '//*[@id="__next"]/div[1]/div/div/div/div[3]/div/div/div[2]/div/form/div/div[1]/div[1]/div/div/input')
        utr_input.send_keys(utr)

        approve_submit = driver.find_element(By.XPATH, '//*[@id="__next"]/div[1]/div/div/div/div[3]/div/div/div[2]/div/form/div/div[2]/button')
        approve_submit.click()

        return True, "✅ Site Approved"
    except Exception as e:
        return False, f"❌ Approve Error: {str(e)}"

def reject_transaction(ref_id, expected_hash, reason):
    print("🔍 Attempting Selenium Reject")
    refresh_page_and_wait()
    row = find_row_by_ref_and_hash(ref_id, expected_hash)
    if not row:
        return False, "❌ Row not found or hash mismatch"

    try:
        reject_button = row.find_element(By.XPATH, './/button[2]')
        reject_button.click()
        time.sleep(1)

        remark_input = driver.find_element(By.XPATH, '//*[@id="__next"]/div[1]/div/div/div/div[3]/div/div/div[2]/form/div/div[1]/div/div/div/input')
        remark_input.send_keys(reason)

        reject_submit = driver.find_element(By.XPATH, '//*[@id="__next"]/div[1]/div/div/div/div[3]/div/div/div[2]/form/div/div[2]/button')
        reject_submit.click()

        return True, "✅ Site Rejected"
    except Exception as e:
        return False, f"❌ Reject Error: {str(e)}"
