# === main.py ===
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from datetime import datetime, timedelta
import requests
import hashlib
import os
import threading
from flask import Flask, request, jsonify
from openpyxl import Workbook

# === Config ===
CHROME_DRIVER_PATH = 'C:/Users/GAME/chromedriver-win64/chromedriver.exe'
TARGET_URL = "https://upi9.pro/merchant/withdrawls/"
REFRESH_INTERVAL = 15
LOG_FILE = "withdrawal_logs.txt"
SEEN_IDS_FILE = "seen_ids.txt"
SEEN_HASHES_FILE = "seen_hashes.txt"
ACTION_LOG_FILE = "action_log.txt"
BOT_TOKEN = "8280104776:AAFcJUHRUB2d2ouMp-0OE6Zru-AYYvV4FKU"
CHAT_ID = -1002559335031
ADMIN_ID = 8468186217

# === Setup ===
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=options)
driver.get(TARGET_URL)
input("🔐 Login manually and press ENTER to continue...")

app = Flask(__name__)
retry_delay = 3

# === Utilities ===
def hash_row_data(*args):
    return hashlib.sha256("|".join(args).strip().lower().encode()).hexdigest()

def load_seen_file(file_path):
    if not os.path.exists(file_path): return {}
    seen = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if '|' in line:
                key, timestamp = line.strip().split("|", 1)
                seen[key] = timestamp
    return seen

def save_seen_file(file_path, seen_dict):
    with open(file_path, "w", encoding="utf-8") as f:
        for k, v in seen_dict.items():
            f.write(f"{k}|{v}\n")

def cleanup_old_entries(seen_dict, days=10):
    now = datetime.now()
    return {
        k: v for k, v in seen_dict.items()
        if (now - datetime.strptime(v, "%Y-%m-%d %H:%M:%S.%f")).days < days
    }

def wait_for_loader():
    timeout = time.time() + 15
    while time.time() < timeout:
        if not driver.find_elements(By.XPATH, '//div[contains(text(),"Loading please wait")]'):
            return
        time.sleep(0.5)

def refresh_page():
    try:
        driver.execute_script("document.querySelector('button.refresh-btn').click()")
    except: pass
    wait_for_loader()

def send_to_telegram_with_button(data):
    text = (
        f"\U0001F464 User: {data['username']}\n"
        f"\U0001F4B0 Amount: {data['amount']}\n"
        f"\U0001F3E6 Bank Name: {data['bank_name']}\n"
        f"\U0001F4B2 Account Number: {data['acc_no']}\n"
        f"\U0001F46E Account Holder: {data['acc_holder']}\n"
        f"\U0001F520 IFSC Code: {data['ifsc']}\n\n"
        f"#REF: {data['ref']}\n"
        f"#HASH: {data['hash']}"
    )
    keyboard = {"inline_keyboard": [[{"text": "\U0001F9FE Take Slip", "callback_data": "take_slip"}]]}
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "reply_markup": keyboard, "parse_mode": "HTML"}
        )
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# === Action Functions ===
def approve_transaction(ref_id, expected_hash, utr):
    while True:
        refresh_page()
        time.sleep(2)
        rows = driver.find_elements(By.XPATH, '//div[@class="ag-center-cols-container"]/div[@role="row"]')
        for idx, row in enumerate(rows):
            try:
                cells = row.find_elements(By.XPATH, './/div[@role="gridcell"]')
                if len(cells) < 13: continue
                if cells[12].text.strip() == ref_id:
                    approve_buttons = driver.find_elements(By.XPATH, '//button[contains(text(), "Approve")]')
                    if idx < len(approve_buttons):
                        approve_buttons[idx].click()
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, '//input[@placeholder="Enter reference number"]'))
                        ).send_keys(utr)
                        WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, '//button[@type="submit" and contains(text(), "Approve")]'))
                        ).click()
                        return "✅ Approved on site"
            except: pass
        time.sleep(retry_delay)

def reject_transaction(ref_id, expected_hash, reason):
    while True:
        refresh_page()
        time.sleep(2)
        rows = driver.find_elements(By.XPATH, '//div[@class="ag-center-cols-container"]/div[@role="row"]')
        for idx, row in enumerate(rows):
            try:
                cells = row.find_elements(By.XPATH, './/div[@role="gridcell"]')
                if len(cells) < 13: continue
                if cells[12].text.strip() == ref_id:
                    reject_buttons = driver.find_elements(By.XPATH, '//button[contains(text(), "Reject")]')
                    if idx < len(reject_buttons):
                        reject_buttons[idx].click()
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, '//input[@placeholder="Enter the remark"]'))
                        ).send_keys(reason)
                        WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, '//button[@type="submit" and contains(text(), "Submit")]'))
                        ).click()
                        return "✅ Rejected on site"
            except: pass
        time.sleep(retry_delay)

# === Retry Handler ===
def log_and_retry(data, attempt=1):
    with open(ACTION_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | Attempt {attempt} | {data}\n")
    if data["action"] == "approve":
        result = approve_transaction(data["ref"], data["hash"], data["utr"])
    elif data["action"] == "reject":
        result = reject_transaction(data["ref"], data["hash"], data["reason"])
    else:
        result = "❌ Unknown action"
    print(f"📝 Attempt {attempt}: {result}")

# === Flask API ===
@app.route("/act", methods=["POST"])
def act():
    data = request.json
    if not data: return jsonify({"status": "error", "msg": "No data"})
    threading.Thread(target=log_and_retry, args=(data,), daemon=True).start()
    return jsonify({"status": "ok", "queued": True})

def flask_thread():
    app.run(port=9999)

threading.Thread(target=flask_thread, daemon=True).start()

# === Summary Threads ===
def generate_excel_summary(hours, target_id, send_text=False):
    cutoff = datetime.now() - timedelta(hours=hours)
    approvals = []
    try:
        with open(ACTION_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if '"action": "approve"' not in line:
                    continue
                try:
                    parts = line.strip().split("|")
                    timestamp = datetime.strptime(parts[0].strip(), "%Y-%m-%d %H:%M:%S.%f")
                    if timestamp < cutoff:
                        continue
                    data_str = parts[2].strip()
                    if "utr" not in data_str or "amount" not in data_str:
                        continue
                    utr = data_str.split('"utr":')[1].split(",")[0].replace('"', '').strip()
                    tg_user = data_str.split('"tg_user":')[1].split(",")[0].replace('"', '').strip() if '"tg_user":' in data_str else "N/A"
                    amount = float(data_str.split('"amount":')[1].split(",")[0].replace('"', '').replace('₹', '').replace(',', '').strip())
                    approvals.append([utr, tg_user, amount])
                except: continue
    except: return

    if not approvals:
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["UTR", "User", "Amount"])
    for row in approvals:
        ws.append(row)
    total_amt = sum([row[2] for row in approvals])
    ws.append(["", "Total Approved", len(approvals)])
    ws.append(["", "Total Amount", total_amt])
    filename = f"summary_{hours}h_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
    wb.save(filename)

    try:
        with open(filename, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                files={"document": (filename, f)},
                data={"chat_id": target_id, "caption": f"📊 {hours}-hour Approval Summary"}
            )
    except Exception as e:
        print(f"❌ Failed to send Excel: {e}")
    os.remove(filename)

def summary_5min():
    while True:
        generate_excel_summary(0.084, CHAT_ID, send_text=True)
        time.sleep(300)

def summary_24h():
    while True:
        generate_excel_summary(24, ADMIN_ID, send_text=False)
        time.sleep(86400)

threading.Thread(target=summary_5min, daemon=True).start()
threading.Thread(target=summary_24h, daemon=True).start()

print("\u2705 Flask API running at http://127.0.0.1:9999")

seen_ids = load_seen_file(SEEN_IDS_FILE)
seen_hashes = load_seen_file(SEEN_HASHES_FILE)

while True:
    try:
        refresh_page()
        rows = driver.find_elements(By.XPATH, '//div[@class="ag-center-cols-container"]/div[@role="row"]')
        for row in rows:
            try:
                cells = row.find_elements(By.XPATH, './/div[@role="gridcell"]')
                if len(cells) < 13: continue
                username = cells[0].text.strip()
                amount = cells[6].text.strip()
                bank = cells[8].text.strip()
                acc_no = cells[9].text.strip()
                acc_holder = cells[10].text.strip()
                ifsc = cells[11].text.strip()
                transfer_id = cells[12].text.strip()
                if not all([amount, bank, acc_no, acc_holder, ifsc, transfer_id]): continue
                if "₹" not in amount: continue
                if any(word in username.lower() for word in ["am", "pm", "august"]): username = "N/A"
                if not username: username = "N/A"
                if transfer_id in seen_ids: continue
                row_hash = hash_row_data(transfer_id, amount, acc_no, ifsc)
                if row_hash in seen_hashes: continue
                send_to_telegram_with_button({
                    "username": username, "amount": amount, "bank_name": bank,
                    "acc_no": acc_no, "acc_holder": acc_holder,
                    "ifsc": ifsc, "ref": transfer_id, "hash": row_hash
                })
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now()} | {transfer_id} | {row_hash}\n")
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                seen_ids[transfer_id] = now_str
                seen_hashes[row_hash] = now_str
            except: continue
        seen_ids = cleanup_old_entries(seen_ids, 10)
        seen_hashes = cleanup_old_entries(seen_hashes, 10)
        save_seen_file(SEEN_IDS_FILE, seen_ids)
        save_seen_file(SEEN_HASHES_FILE, seen_hashes)
    except Exception as e:
        print(f"❌ Main loop error: {e}")
    time.sleep(REFRESH_INTERVAL)
