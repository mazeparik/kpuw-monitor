import os
import sys
import time
import datetime
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "45"))
TARGET_URL = os.getenv("TARGET_URL", "https://uw.bezkolejki.eu/kpuw_bydgoszcz/Reservation")
MAX_RUNTIME_MINUTES = int(os.getenv("MAX_RUNTIME_MINUTES", "0"))  # 0 = без обмежень

# Підтримка декількох ID через кому: "123456, 789012"
CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.replace(";", ",").split(",") if cid.strip()]

if not TELEGRAM_BOT_TOKEN or not CHAT_IDS:
    print("❌ Помилка: Вкажіть TELEGRAM_BOT_TOKEN та TELEGRAM_CHAT_ID у .env або GitHub Secrets")
    sys.exit(1)


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def send_telegram_message(text: str, disable_preview: bool = True):
    """Надсилає повідомлення всім зазначеним Chat ID."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": disable_preview,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                log(f"✅ Сповіщення надіслано користувачу {chat_id}")
            else:
                log(f"⚠️ Telegram помилка для {chat_id}: {resp.text}")
        except Exception as e:
            log(f"❌ Помилка надсилання в Telegram ({chat_id}): {e}")


def send_telegram_alert(dates: list):
    dates_str = ", ".join(str(d) for d in dates)
    message = (
        f"🚨 *З'явилися вільні терміни на відбитки пальців!* 🚨\n\n"
        f"🏛 *Ужонд:* KPUW Bydgoszcz\n"
        f"📅 *Доступні дати:* `{dates_str}`\n\n"
        f"👉 [Швидко перейти до бронювання]({TARGET_URL})"
    )
    send_telegram_message(message, disable_preview=False)


def run_monitor():
    log("🚀 Запуск моніторингу черги KPUW Bydgoszcz...")
    log(f"👥 Отримувачі сповіщень: {CHAT_IDS}")
    log(f"🔗 Сторінка: {TARGET_URL}")
    log(f"⏱️ Інтервал перевірки: {CHECK_INTERVAL_SECONDS} секунд")
    if MAX_RUNTIME_MINUTES > 0:
        log(f"⏳ Ліміт часу роботи сесії: {MAX_RUNTIME_MINUTES} хв")

    # Надсилаємо сповіщення про успішний старт сесії
    startup_msg = (
        "🟢 *[KPUW Monitor] Сесію моніторингу запущено!*\n\n"
        "🏛 *Ужонд:* KPUW Bydgoszcz (Odciski palców)\n"
        f"⏱️ Перевірка кожні {CHECK_INTERVAL_SECONDS} сек.\n"
        "Щойно з'явиться вільне віконце — миттєво прийде повідомлення!"
    )
    send_telegram_message(startup_msg)

    start_time = time.time()
    detected_days = []
    last_alerted_days = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        def handle_response(response):
            nonlocal detected_days
            if "GetAvailableDaysForOperation" in response.url:
                try:
                    data = response.json()
                    days = data.get("availableDays", [])
                    if days:
                        detected_days = days
                        log(f"📩 Сервер повернув вільні дати: {days}")
                    else:
                        detected_days = []
                except Exception as e:
                    log(f"Не вдалося розпарсити відповідь від сервера: {e}")

        page.on("response", handle_response)

        check_count = 0
        while True:
            if MAX_RUNTIME_MINUTES > 0:
                elapsed_minutes = (time.time() - start_time) / 60
                if elapsed_minutes >= MAX_RUNTIME_MINUTES:
                    log(f"🏁 Досягнуто ліміту сесії {MAX_RUNTIME_MINUTES} хв. Завершення.")
                    break

            check_count += 1
            detected_days = []
            log(f"--- Перевірка #{check_count} ---")
            try:
                page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)

                card = page.locator(".select-card", has_text="Odciski palców")
                if card.count() > 0:
                    card.first.click()
                    page.wait_for_timeout(4000)
                else:
                    log("⚠️ Картку 'Odciski palców' не знайдено на сторінці.")

                if detected_days:
                    log(f"🔥 ЗНАЙДЕНО ВІЛЬНІ МІСЦЯ: {detected_days}")
                    if detected_days != last_alerted_days:
                        send_telegram_alert(detected_days)
                        last_alerted_days = detected_days
                    else:
                        log("ℹ️ Сповіщення про ці дати вже надсилалося.")
                    time.sleep(120)
                else:
                    log("⚪ Вільних місць наразі немає.")

            except Exception as err:
                log(f"⚠️ Помилка під час перевірки: {err}")

            log(f"💤 Очікування {CHECK_INTERVAL_SECONDS} сек...\n")
            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run_monitor()
    except KeyboardInterrupt:
        print("\n[!] Моніторинг зупинено.")
