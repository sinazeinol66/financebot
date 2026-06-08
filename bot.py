import os
import time
import hashlib
import logging
import requests
from datetime import datetime
import feedparser
from anthropic import Anthropic

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@financeconnectzone")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "1800"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# ============================================================
# لیست منابع — اینجا ادیت کن
# هر منبع: name=اسم | url=آدرس RSS | priority=1تا3
# ============================================================
RSS_SOURCES = [
    {"name": "ایرنا اقتصادی",    "url": "https://www.irna.ir/rss/economy/",                    "priority": 3},
    {"name": "تسنیم اقتصادی",    "url": "https://www.tasnimnews.com/fa/rss/feed/0/5/0",         "priority": 3},
    {"name": "فارس اقتصادی",     "url": "https://www.farsnews.ir/rss/economy",                  "priority": 3},
    {"name": "ایسنا اقتصادی",    "url": "https://www.isna.ir/rss/tp-economy",                   "priority": 3},
    {"name": "مهر اقتصادی",      "url": "https://www.mehrnews.com/rss/economy",                 "priority": 3},
    {"name": "دنیای اقتصاد",     "url": "https://www.donya-e-eqtesad.com/rss",                  "priority": 3},
    {"name": "اقتصادنیوز",       "url": "https://www.eghtesadnews.com/rss",                     "priority": 3},
    {"name": "بانکداری ایران",    "url": "https://www.bankdari.ir/rss",                          "priority": 2},
    {"name": "بانک مرکزی",       "url": "https://www.cbi.ir/rss/news.aspx",                     "priority": 3},
    {"name": "سازمان بورس",      "url": "https://www.seo.ir/rss",                               "priority": 3},
    {"name": "عصر ایران",        "url": "https://www.asriran.com/rss/economy",                  "priority": 2},
    {"name": "فینتو",            "url": "https://www.fintoo.ir/rss",                            "priority": 2},
]
# ============================================================

FINANCE_KEYWORDS = [
    "بانک","بورس","سهام","ارز","دلار","تورم","نرخ سود","وام","اعتبار",
    "فین‌تک","فینتک","رمزارز","بیت‌کوین","کریپتو","بیمه","سپرده",
    "صندوق","اوراق","اقتصاد","مالی","پولی","بانک مرکزی","بورس اوراق",
    "تسهیلات","نقدینگی","ریال","تومان","سرمایه","سرمایه‌گذاری",
    "خزانه","بودجه","مالیات","شاخص","معامله","عرضه اولیه","درآمد",
]

# عنوان خبر → لیست منابعی که همان خبر را پوشش دادند
title_to_sources: dict[str, list] = {}
sent_hashes: set[str] = set()


def is_finance_related(title, summary=""):
    text = title + " " + summary
    return any(kw in text for kw in FINANCE_KEYWORDS)


def normalize_title(title: str) -> str:
    """حذف کلمات کم‌اهمیت برای مقایسه تکراری"""
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود"}
    words = [w for w in title.split() if w not in stop]
    return " ".join(words[:6])


def titles_similar(t1: str, t2: str) -> bool:
    w1 = set(normalize_title(t1).split())
    w2 = set(normalize_title(t2).split())
    if not w1 or not w2:
        return False
    overlap = len(w1 & w2) / min(len(w1), len(w2))
    return overlap >= 0.6


def summarize(title: str, body: str) -> str:
    if not anthropic_client:
        return ""
    try:
        resp = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"خبر زیر را در ۲ تا ۳ جمله کوتاه به فارسی خلاصه کن. "
                    f"فقط خلاصه بنویس، هیچ مقدمه‌ای نداشته باش.\n\n"
                    f"عنوان: {title}\n"
                    f"متن: {body[:800]}"
                ),
            }],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"خطا در خلاصه‌سازی: {e}")
        return ""


def send_to_telegram(message: str) -> bool:
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


def parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6])
            except Exception:
                pass
    return datetime.utcnow()


def fetch_rss(source: dict) -> list:
    results = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; FinanceBot/2.0)"}
        feed = feedparser.parse(source["url"], request_headers=headers)
        for entry in feed.entries[:15]:
            title   = entry.get("title", "").strip()
            link    = entry.get("link", "").strip()
            summary = entry.get("summary", "")
            if not title or not link:
                continue
            if not is_finance_related(title, summary):
                continue
            news_hash = hashlib.md5((title + link).encode()).hexdigest()
            if news_hash in sent_hashes:
                continue
            pub_date = parse_date(entry)
            results.append({
                "title":    title,
                "link":     link,
                "summary":  summary,
                "source":   source["name"],
                "priority": source["priority"],
                "hash":     news_hash,
                "date":     pub_date,
            })
    except Exception as e:
        logger.error(f"خطا در {source['name']}: {e}")
    return results


def format_message(news: dict, also_covered: list) -> str:
    stars   = "⭐" * news["priority"]
    pub     = news["date"]
    # تبدیل UTC به تهران (UTC+3:30)
    from datetime import timezone, timedelta
    tehran  = timezone(timedelta(hours=3, minutes=30))
    local   = pub.replace(tzinfo=timezone.utc).astimezone(tehran)
    date_str = local.strftime("%Y/%m/%d — %H:%M")

    summary = summarize(news["title"], news["summary"])

    msg  = f"📰 <b>{news['title']}</b>\n\n"
    if summary:
        msg += f"📝 {summary}\n\n"
    msg += f"🕐 {date_str}\n"
    msg += f"📡 منبع: {news['source']} {stars}\n"
    if also_covered:
        msg += f"🔁 همین خبر در: {' | '.join(also_covered)}\n"
    msg += f"\n🔗 <a href='{news['link']}'>مشاهده خبر</a>"
    return msg


def deduplicate(all_news: list) -> list:
    """گروه‌بندی اخبار مشابه — فقط یکی ارسال می‌شود"""
    groups: list[list] = []
    for news in all_news:
        placed = False
        for group in groups:
            if titles_similar(news["title"], group[0]["title"]):
                group.append(news)
                placed = True
                break
        if not placed:
            groups.append([news])

    unique = []
    for group in groups:
        best = max(group, key=lambda x: x["priority"])
        also = [n["source"] for n in group if n["source"] != best["source"]]
        best["also_covered"] = also
        unique.append(best)
    return unique


def check_all_sources():
    logger.info("--- شروع بررسی منابع ---")
    all_news = []
    for source in RSS_SOURCES:
        news_list = fetch_rss(source)
        all_news.extend(news_list)
        time.sleep(1)

    all_news.sort(key=lambda x: x["date"], reverse=True)
    unique_news = deduplicate(all_news)
    unique_news = unique_news[:10]

    sent_count = 0
    for news in unique_news:
        msg = format_message(news, news.get("also_covered", []))
        success = send_to_telegram(msg)
        if success:
            sent_hashes.add(news["hash"])
            sent_count += 1
            time.sleep(3)

    logger.info(f"{sent_count} خبر ارسال شد")


def main():
    logger.info("ربات خبری مالی v2 شروع به کار کرد")
    send_to_telegram("🚀 <b>ربات خبری مالی ایران — نسخه ۲</b>\nبه‌روزرسانی هر ۳۰ دقیقه | خلاصه‌سازی هوشمند فعال")
    while True:
        try:
            check_all_sources()
        except Exception as e:
            logger.error(f"خطای کلی: {e}")
        logger.info(f"انتظار {CHECK_INTERVAL} ثانیه...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
