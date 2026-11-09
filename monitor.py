import os
import sys
import time
import datetime
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# Отримуємо токен (з захистом від порожнього рядка з Secrets та префіксу "bot")
raw_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
if not raw_token:
    raw_token = "8679764400:AAE4RS7dJre_fRdkpBEgrrpicfLSiRAVSCo"
if raw_token.startswith("bot"):
    raw_token = raw_token[3:]
TELEGRAM_BOT_TOKEN = raw_token

RAW_CHAT_IDS = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
if not RAW_CHAT_IDS:
    RAW_CHAT_IDS = "6426530276, 6764361976"

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "45"))
TARGET_URL = os.getenv("TARGET_URL", "https://uw.bezkolejki.eu/kpuw_bydgoszcz/Reservation")

# Отримувачі (розділені комою)
CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.replace(";", ",").split(",") if cid.strip()]


def get_poland_time() -> datetime.datetime:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    is_summer = 4 <= now_utc.month <= 9 or (now_utc.month == 3 and now_utc.day >= 25) or (now_utc.month == 10 and now_utc.day < 25)
    offset_hours = 2 if is_summer else 1
    return now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=offset_hours)))


def log(msg: str):
    pl_time = get_poland_time().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{pl_time} PL] {msg}", flush=True)


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
                log(f"✅ Сповіщення надіслано користувачу {chat_id}")
            else:
                log(f"ℹ️ Статус надсилання для {chat_id}: {resp.status_code} ({resp.text})")
        except Exception as e:
            log(f"❌ Помилка Telegram ({chat_id}): {e}")


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
    pl_now = get_poland_time()
    log("🚀 Ініціалізація KPUW Slot Monitor...")
    log(f"🔑 Bot Token довжина: {len(TELEGRAM_BOT_TOKEN)} символів (початок: {TELEGRAM_BOT_TOKEN[:6]}...)")
    log(f"👥 Список отримувачів: {CHAT_IDS}")
    log(f"🕒 Час у Польщі: {pl_now.strftime('%H:%M:%S')} ({pl_now.strftime('%A')})")

    is_outside_working_hours = (pl_now.weekday() >= 5) or (pl_now.hour < 8 or pl_now.hour >= 17)

    if is_outside_working_hours:
        log("🌙 Зараз неробочий час у Польщі (робочий графік: Пн-Пт 08:00–17:00).")
        log("🧪 Виконуємо 1 разову тестову перевірку сайту KPUW для діагностики...")

        site_status = "невідомо"
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            page = browser.new_page()
            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                log(f"Сторінка відкрилась: '{page.title()}', URL: {page.url}")

                # Очікуємо появи карток (до 20 сек для повільного з'єднання)
                page.wait_for_selector(".select-card", timeout=20000)
                card = page.locator(".select-card", has_text="Odciski palców")
                found = card.count() > 0
                log(f"Тест сайту: знайдено картку 'Odciski palców' = {found}")
                site_status = "✅ Сайт KPUW доступний, картка черги знайдена"
            except Exception as e:
                log(f"Тест сайту: помилка = {e}")
                log(f"Заголовок: '{page.title()}', текст: {page.inner_text('body')[:200] if page else 'немає'}")
                site_status = f"⚠️ Помилка завантаження: {e}"
            finally:
                browser.close()

        test_msg = (
            "🧪 *[KPUW Monitor] Діагностичне сповіщення*\n\n"
            f"{site_status}\n"
            f"🕒 Поточний польський час: `{pl_now.strftime('%H:%M')}`\n\n"
            "⏰ *Автоматичний моніторинг черги увімкнеться за розкладом о 08:00 ранку!*"
        )
        send_telegram_message(test_msg)
        log("🏁 Тестова перевірка завершена.")
        return

    # Робочий час (08:00 - 17:00)
    startup_msg = (
        "🟢 *[KPUW Monitor] Моніторинг черги розпочато!*\n\n"
        "🏛 *Ужонд:* KPUW Bydgoszcz (Odciski palców)\n"
        f"🕒 Польський час: `{pl_now.strftime('%H:%M')}` (робота до 17:00)\n"
        f"⏱️ Інтервал: кожні {CHECK_INTERVAL_SECONDS} сек.\n\n"
        "Як тільки з'явиться віконце — сюди миттєво надійде посилання!"
    )
    send_telegram_message(startup_msg)

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
            current_pl = get_poland_time()
            if current_pl.hour >= 17 or current_pl.hour < 8:
                log(f"⏹️ Настав час завершення ({current_pl.strftime('%H:%M')} PL). Зупинка скрипта до 08:00.")
                stop_msg = (
                    "🔴 *[KPUW Monitor] Робочий день завершено.*\n\n"
                    f"🕒 Польський час: `{current_pl.strftime('%H:%M')}`.\n"
                    "Скрипт вимикається до 08:00 наступного робочого дня."
                )
                send_telegram_message(stop_msg)
                break

            check_count += 1
            detected_days = []
            log(f"--- Перевірка #{check_count} ---")
            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector(".select-card", timeout=15000)

                card = page.locator(".select-card", has_text="Odciski palców")
                if card.count() > 0:
                    card.first.click()
                    page.wait_for_timeout(4000)
                else:
                    log("⚠️ Картку 'Odciski palców' не знайдено.")

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
