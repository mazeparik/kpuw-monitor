import os
import sys
import time
import datetime
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Спроба імпорту звукового сигналу для Windows
try:
    import winsound
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8679764400:AAE4RS7dJre_fRdkpBEgrrpicfLSiRAVSCo").strip()
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "6426530276, 6764361976, 6315959355").strip()
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "40"))
TARGET_URL = os.getenv("TARGET_URL", "https://uw.bezkolejki.eu/kpuw_bydgoszcz/Reservation")

CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.replace(";", ",").split(",") if cid.strip()]


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def play_alarm():
    """Гучний звуковий сигнал на комп'ютері"""
    if HAS_SOUND:
        try:
            for _ in range(5):
                winsound.Beep(1200, 400)
                time.sleep(0.1)
                winsound.Beep(1600, 500)
                time.sleep(0.1)
        except Exception:
            pass


def send_telegram_message(text: str, disable_preview: bool = True):
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
                log(f"✅ Сповіщення надіслано на ID {chat_id}")
            else:
                log(f"ℹ️ Статус надсилання для {chat_id}: {resp.status_code}")
        except Exception as e:
            log(f"❌ Помилка Telegram ({chat_id}): {e}")


def send_slot_alert(details: str = ""):
    message = (
        "🚨🚨🚨 *УВАГА! ВІЛЬНІ МІСЦЯ НА ВІДБИТКИ!* 🚨🚨🚨\n\n"
        "🏛 *Ужонд:* KPUW Bydgoszcz (Odciski palców)\n"
        f"⚡️ *Сигнал:* {details}\n\n"
        f"👉 [ШВИДКО ПЕРЕХОДЬТЕ ДО БРОНЮВАННЯ]({TARGET_URL})\n\n"
        "⏱️ Відкривайте сайт, проходьте капчу і займайте час!"
    )
    send_telegram_message(message, disable_preview=False)
    play_alarm()


def is_captcha_triggered(page) -> bool:
    """Перевіряє, чи вискочила на сторінці інтерактивна капча"""
    try:
        # Шукаємо bframe (вікно пазлу reCAPTCHA), видимі iframe капчі або модальні вікна
        selectors = [
            'iframe[src*="google.com/recaptcha/api2/bframe"]',
            'iframe[title*="recaptcha"]',
            'iframe[src*="challenges.cloudflare.com"]',
            '.g-recaptcha-bubble',
            'div[style*="visibility: visible"] iframe[src*="recaptcha"]',
        ]
        for sel in selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                for i in range(loc.count()):
                    if loc.nth(i).is_visible():
                        return True
    except Exception:
        pass
    return False


def run_monitor():
    log("🚀 Запуск ЛОКАЛЬНОГО моніторингу черги KPUW Bydgoszcz...")
    log(f"👥 Отримувачі сповіщень у Telegram: {CHAT_IDS}")
    log(f"🔗 Сторінка: {TARGET_URL}")
    log(f"⏱️ Інтервал опитування: {CHECK_INTERVAL_SECONDS} секунд")

    startup_msg = (
        "🟢 *[KPUW Monitor] Локальний моніторинг запущено на комп'ютері!*\n\n"
        "🏛 *Ужонд:* KPUW Bydgoszcz (Odciski palców)\n"
        f"⏱️ Інтервал: кожні {CHECK_INTERVAL_SECONDS} сек.\n"
        f"👥 Сповіщення отримують: `{len(CHAT_IDS)}` акаунтів.\n\n"
        "Щойно з'являться вільні дні або вискочить вікно капчі — сюди миттєво прилетить тривожне сповіщення!"
    )
    send_telegram_message(startup_msg)

    detected_days = []

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
                        log(f"📩 Сервер повернув дні: {days}")
                    else:
                        detected_days = []
                except Exception as e:
                    log(f"Помилка парсингу JSON відповіді: {e}")

        page.on("response", handle_response)

        check_count = 0
        while True:
            check_count += 1
            detected_days = []
            log(f"--- Перевірка #{check_count} ---")
            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_selector(".select-card", timeout=12000)

                card = page.locator(".select-card", has_text="Odciski palców")
                if card.count() > 0:
                    card.first.click()
                    page.wait_for_timeout(4000)
                else:
                    log("⚠️ Картку 'Odciski palców' не знайдено.")

                # Сигнал 1: У відповіді API повернулися конкретні вільні дні
                if detected_days:
                    log(f"🔥 ЗНАЙДЕНО ВІЛЬНІ ДНІ: {detected_days}")
                    send_slot_alert(f"Знайдено вільні дні: `{', '.join(str(d) for d in detected_days)}`")
                    log("💤 Пауза 3 хвилини після знахідки для спокійного бронювання...")
                    time.sleep(180)
                    continue

                # Сигнал 2: Вискочило вікно капчі (reCAPTCHA puzzle / challenge)
                if is_captcha_triggered(page):
                    log("🔥 СПРАЦЮВАЛА КАПЧА! Це означає появу вільних слотів!")
                    send_slot_alert("На сайті з'явилося вікно капчі! Ймовірно, викинуто слоти.")
                    log("💤 Пауза 3 хвилини для вирішення капчі та бронювання...")
                    time.sleep(180)
                    continue

                log("⚪ Наразі вільних віконець немає (капча не спрацювала).")

            except Exception as err:
                log(f"⚠️ Помилка перевірки: {err}")

            log(f"💤 Очікування {CHECK_INTERVAL_SECONDS} сек...\n")
            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run_monitor()
    except KeyboardInterrupt:
        print("\n[!] Моніторинг зупинено користувачем.")
