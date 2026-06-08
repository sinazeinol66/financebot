import os, time, hashlib, logging, requests
from datetime import datetime, timezone, timedelta
import feedparser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID      = os.environ.get("CHANNEL_ID", "@financeconnectzone")
CHECK_INTERVAL  = int(os.environ.get("CHECK_INTERVAL", "120"))

# ================================================================
#  لیست منابع RSS — اینجا اضافه یا حذف کن
#  فرمت هر خط:
#  {"name": "اسم فارسی", "url": "آدرس RSS", "priority": 1/2/3}
# ================================================================
RSS_SOURCES = [
    {"name": "ایرنا اقتصادی",   "url": "https://www.irna.ir/rss/economy/",                   "priority": 3},
    {"name": "تسنیم اقتصادی",   "url": "https://www.tasnimnews.com/fa/rss/feed/0/5/0",        "priority": 3},
    {"name": "فارس اقتصادی",    "url": "https://www.farsnews.ir/rss/economy",                 "priority": 3},
    {"name": "ایسنا اقتصادی",   "url": "https://www.isna.ir/rss/tp-economy",                  "priority": 3},
    {"name": "مهر اقتصادی",     "url": "https://www.mehrnews.com/rss/economy",                "priority": 3},
    {"name": "دنیای اقتصاد",    "url": "https://www.donya-e-eqtesad.com/rss",                 "priority": 3},
    {"name": "اقتصادنیوز",      "url": "https://www.eghtesadnews.com/rss",                    "priority": 3},
    {"name": "بانکداری ایران",   "url": "https://www.bankdari.ir/rss",                         "priority": 2},
    {"name": "بانک مرکزی",      "url": "https://www.cbi.ir/rss/news.aspx",                    "priority": 3},
    {"name": "سازمان بورس",     "url": "https://www.seo.ir/rss",                              "priority": 3},
    {"name": "عصر ایران",       "url": "https://www.asriran.com/rss/economy",                 "priority": 2},
]
# ================================================================

FINANCE_KEYWORDS = [
    "بانک","بورس","سهام","ارز","دلار","تورم","نرخ سود","وام","اعتبار",
    "فین‌تک","فینتک","رمزارز","بیت‌کوین","کریپتو","بیمه","سپرده",
    "صندوق","اوراق","اقتصاد","مالی","پولی","بانک مرکزی",
    "تسهیلات","نقدینگی","ریال","تومان","سرمایه","سرمایه‌گذاری",
    "خزانه","بودجه","مالیات","شاخص","معامله","عرضه اولیه",
]

TEHRAN = timezone(timedelta(hours=3, minutes=30))
sent_hashes: set = set()
# عنوان → لیست منابع برای تشخیص تکراری
seen_titles: list = []


def is_finance(title, summary=""):
    text = title + " " + summary
    return any(kw in text for kw in FINANCE_KEYWORDS)


def titles_similar(t1, t2):
    words1 = set(t1.split())
    words2 = set(t2.split())
    if not words1 or not words2:
        return False
    return len(words1 & words2) / min(len(words1), len(words2)) >= 0.55


def summarize_with_api(title, body):
    """خلاصه‌سازی با Anthropic API — بدون کتابخانه، فقط requests"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 150,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"این خبر را در ۲ جمله کوتاه فارسی خلاصه کن. فقط خلاصه بنویس:\n"
                        f"عنوان: {title}\nمتن: {body[:600]}"
                    )
                }]
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.error(f"خطا خلاصه‌سازی: {e}")
    return ""


def send_telegram(message):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": message,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10,
        )
        ok = r.status_code == 200
        if not ok:
            logger.error(f"تلگرام: {r.text}")
        return ok
    except Exception as e:
        logger.error(f"خطای تلگرام: {e}")
        return False


def parse_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except:
                pass
    return datetime.now(timezone.utc)


def fetch_source(source):
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "fa-IR,fa;q=0.9",
    }
    try:
        # دانلود مستقیم RSS با requests برای bypass فیلترهای احتمالی
        raw = requests.get(source["url"], headers=headers, timeout=12)
        raw.encoding = "utf-8"
        feed = feedparser.parse(raw.text)
        
        if not feed.entries:
            # تلاش دوم با feedparser مستقیم
            feed = feedparser.parse(source["url"], request_headers=headers)

        for entry in feed.entries[:20]:
            title   = entry.get("title", "").strip()
            link    = entry.get("link", "").strip()
            summary = entry.get("summary", "")
            if not title or not link:
                continue
            if not is_finance(title, summary):
                continue
            h = hashlib.md5((title + link).encode()).hexdigest()
            if h in sent_hashes:
                continue
            results.append({
                "title":    title,
                "link":     link,
                "body":     summary,
                "source":   source["name"],
                "priority": source["priority"],
                "hash":     h,
                "date":     parse_date(entry),
            })
        logger.info(f"{source['name']}: {len(results)} خبر جدید")
    except Exception as e:
        logger.warning(f"{source['name']}: {e}")
    return results


def deduplicate(news_list):
    groups = []
    for news in news_list:
        placed = False
        for g in groups:
            if titles_similar(news["title"], g[0]["title"]):
                g.append(news)
                placed = True
                break
        if not placed:
            groups.append([news])
    result = []
    for g in groups:
        best = max(g, key=lambda x: x["priority"])
        best["also"] = [n["source"] for n in g if n["source"] != best["source"]]
        result.append(best)
    return result


def format_msg(news):
    stars   = "⭐" * news["priority"]
    local   = news["date"].astimezone(TEHRAN)
    date_s  = local.strftime("%Y/%m/%d  %H:%M")
    summary = summarize_with_api(news["title"], news["body"])

    msg  = f"📰 <b>{news['title']}</b>\n\n"
    if summary:
        msg += f"📝 {summary}\n\n"
    msg += f"🕐 {date_s}\n"
    msg += f"📡 {news['source']} {stars}\n"
    if news.get("also"):
        msg += f"🔁 همین خبر در: {' | '.join(news['also'])}\n"
    msg += f"\n🔗 <a href='{news['link']}'>مشاهده خبر</a>"
    return msg


def run_cycle():
    logger.info("=== شروع چرخه بررسی ===")
    all_news = []
    for src in RSS_SOURCES:
        all_news.extend(fetch_source(src))
        time.sleep(0.5)

    all_news.sort(key=lambda x: x["date"], reverse=True)
    unique = deduplicate(all_news)[:15]
    logger.info(f"خبرهای یکتا: {len(unique)}")

    sent = 0
    for news in unique:
        if send_telegram(format_msg(news)):
            sent_hashes.add(news["hash"])
            sent += 1
            time.sleep(2)
    logger.info(f"{sent} خبر ارسال شد")


def main():
    logger.info("ربات خبری مالی v3 شروع به کار کرد")
    send_telegram("🚀 <b>ربات خبری مالی ایران</b> فعال شد\nبه‌روزرسانی هر ۲ دقیقه")
    while True:
        try:
            run_cycle()
        except Exception as e:
            logger.error(f"خطای کلی: {e}")
        logger.info(f"انتظار {CHECK_INTERVAL} ثانیه...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
