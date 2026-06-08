import os
import time
import hashlib
import logging
import requests
from datetime import datetime
import feedparser
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@financeconnectzone")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "1800"))

RSS_SOURCES = [
    {"name": "ایرنا اقتصادی", "url": "https://www.irna.ir/rss/economy/", "priority": 3},
    {"name": "تسنیم اقتصادی", "url": "https://www.tasnimnews.com/fa/rss/feed/0/5/0", "priority": 3},
    {"name": "فارس اقتصادی", "url": "https://www.farsnews.ir/rss/economy", "priority": 3},
    {"name": "ایسنا اقتصادی", "url": "https://www.isna.ir/rss/tp-economy", "priority": 3},
    {"name": "مهر اقتصادی", "url": "https://www.mehrnews.com/rss/economy", "priority": 3},
    {"name": "دنیای اقتصاد", "url": "https://www.donya-e-eqtesad.com/rss", "priority": 3},
    {"name": "اقتصادنیوز", "url": "https://www.eghtesadnews.com/rss", "priority": 3},
    {"name": "بانکداری ایران", "url": "https://www.bankdari.ir/rss", "priority": 2},
    {"name": "بانک مرکزی", "url": "https://www.cbi.ir/rss/news.aspx", "priority": 3},
    {"name": "سازمان بورس", "url": "https://www.seo.ir/rss", "priority": 3},
]

FINANCE_KEYWORDS = [
    "بانک", "بورس", "سهام", "ارز", "دلار", "تورم", "نرخ سود", "وام", "اعتبار",
    "فین‌تک", "فینتک", "رمزارز", "بیت‌کوین", "کریپتو", "بیمه", "سپرده",
    "صندوق", "اوراق", "اقتصاد", "مالی", "پولی", "بانک مرکزی", "بورس اوراق",
    "تسهیلات", "نقدینگی", "تراز", "ریال", "تومان", "سرمایه", "سرمایه‌گذاری",
    "خزانه", "بودجه", "مالیات", "گمرک", "صادرات", "واردات", "تجارت",
    "شاخص", "معامله", "عرضه اولیه", "ETF", "درآمد", "هزینه",
]

sent_hashes = set()

def is_finance_related(title, summary=""):
    text = (title + " " + summary).lower()
    return any(kw in text for kw in FINANCE_KEYWORDS)

def get_news_hash(title, link):
    return hashlib.md5((title + link).encode()).hexdigest()

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            logger.info("پیام ارسال شد")
            return True
        else:
            logger.error(f"خطا در ارسال: {r.text}")
            return False
    except Exception as e:
        logger.error(f"خطای اتصال: {e}")
        return False

def fetch_rss(source):
    results = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
        feed = feedparser.parse(source["url"], request_headers=headers)
        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", "")
            if not title or not link:
                continue
            if not is_finance_related(title, summary):
                continue
            news_hash = get_news_hash(title, link)
            if news_hash in sent_hashes:
                continue
            results.append({
                "title": title,
                "link": link,
                "source": source["name"],
                "priority": source["priority"],
                "hash": news_hash,
            })
    except Exception as e:
        logger.error(f"خطا در {source['name']}: {e}")
    return results

def format_message(news):
    stars = "⭐" * news["priority"]
    now = datetime.now().strftime("%H:%M")
    msg = f"📰 <b>{news['title']}</b>\n\n"
    msg += f"🔗 <a href='{news['link']}'>مشاهده خبر</a>\n"
    msg += f"📡 {news['source']} {stars}\n"
    msg += f"🕐 {now}"
    return msg

def check_all_sources():
    logger.info("--- شروع بررسی منابع ---")
    all_news = []
    for source in RSS_SOURCES:
        news_list = fetch_rss(source)
        all_news.extend(news_list)
        time.sleep(1)

    all_news.sort(key=lambda x: x["priority"], reverse=True)

    sent_count = 0
    for news in all_news:
        if sent_count >= 10:
            break
        success = send_to_telegram(format_message(news))
        if success:
            sent_hashes.add(news["hash"])
            sent_count += 1
            time.sleep(2)

    logger.info(f"{sent_count} خبر ارسال شد")

def main():
    logger.info("ربات خبری مالی شروع به کار کرد")
    send_to_telegram("🚀 <b>ربات خبری مالی ایران فعال شد</b>\nبه‌روزرسانی هر ۳۰ دقیقه یک‌بار")
    
    while True:
        try:
            check_all_sources()
        except Exception as e:
            logger.error(f"خطای کلی: {e}")
        logger.info(f"انتظار {CHECK_INTERVAL} ثانیه...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
