import os, time, hashlib, logging, requests
from datetime import datetime, timezone, timedelta
import feedparser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID     = os.environ.get("CHANNEL_ID", "@financeconnectzone")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
TEHRAN         = timezone(timedelta(hours=3, minutes=30))

# ================================================================
#  لیست منابع — اینجا اضافه یا حذف کن
#  فرمت: {"name": "اسم", "url": "آدرس RSS", "priority": 1/2/3}
# ================================================================
RSS_SOURCES = [
    {"name": "ایرنا اقتصادی",  "url": "https://www.irna.ir/rss/economy/",             "priority": 3},
    {"name": "تسنیم اقتصادی",  "url": "https://www.tasnimnews.com/fa/rss/feed/0/5/0", "priority": 3},
    {"name": "فارس اقتصادی",   "url": "https://www.farsnews.ir/rss/economy",           "priority": 3},
    {"name": "ایسنا اقتصادی",  "url": "https://www.isna.ir/rss/tp-economy",            "priority": 3},
    {"name": "مهر اقتصادی",    "url": "https://www.mehrnews.com/rss/economy",          "priority": 3},
    {"name": "دنیای اقتصاد",   "url": "https://www.donya-e-eqtesad.com/rss",           "priority": 3},
    {"name": "اقتصادنیوز",     "url": "https://www.eghtesadnews.com/feeds",            "priority": 3},
    {"name": "بانکداری ایران",  "url": "https://www.bankdari.ir/rss",                  "priority": 2},
    {"name": "بانک مرکزی",     "url": "https://www.cbi.ir/rss/news.aspx",              "priority": 3},
    {"name": "سازمان بورس",    "url": "https://www.seo.ir/rss",                        "priority": 3},
    {"name": "عصر ایران",      "url": "https://www.asriran.com/rss/economy",           "priority": 2},
]
# ================================================================

KEYWORDS = [
    "بانک","بورس","سهام","ارز","دلار","تورم","نرخ سود","وام","اعتبار",
    "فین‌تک","فینتک","رمزارز","بیت‌کوین","کریپتو","بیمه","سپرده",
    "صندوق","اوراق","اقتصاد","مالی","پولی","تسهیلات","نقدینگی",
    "ریال","تومان","سرمایه","بودجه","مالیات","شاخص","معامله",
]

sent_hashes: set = set()


def is_finance(title, summary=""):
    return any(k in (title + summary) for k in KEYWORDS)


def titles_similar(t1, t2):
    w1, w2 = set(t1.split()), set(t2.split())
    if not w1 or not w2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= 0.55


def summarize(title, body):
    if not ANTHROPIC_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 150,
                  "messages": [{"role": "user", "content":
                      f"این خبر را در ۲ جمله کوتاه فارسی خلاصه کن. فقط خلاصه:\nعنوان: {title}\nمتن: {body[:500]}"}]},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"خلاصه: {e}")
    return ""


def send_telegram(msg):
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN is not set")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10,
        )

        if r.status_code == 200:
            logger.info(f"Telegram sent successfully to {CHANNEL_ID}")
            return True

        logger.error(f"Telegram failed: status={r.status_code}, response={r.text}")
        return False

    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def parse_date(entry):
    for a in ("published_parsed", "updated_parsed"):
        t = getattr(entry, a, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except:
                pass
    return datetime.now(timezone.utc)


def fetch(source):
    results = []
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    headers = {"User-Agent": ua, "Accept": "*/*"}
    try:
        resp = requests.get(source["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        count = 0
        for e in feed.entries[:20]:
            title   = (e.get("title") or "").strip()
            link    = (e.get("link") or "").strip()
            summary = e.get("summary") or ""
            if not title or not link:
                continue
            if not is_finance(title, summary):
                continue
            h = hashlib.md5((title + link).encode()).hexdigest()
            if h in sent_hashes:
                continue
            results.append({
                "title": title, "link": link, "body": summary,
                "source": source["name"], "priority": source["priority"],
                "hash": h, "date": parse_date(e),
            })
            count += 1
        logger.info(f"✓ {source['name']}: {count} خبر جدید (کل entries: {len(feed.entries)})")
    except requests.exceptions.ConnectionError:
        logger.warning(f"✗ {source['name']}: بلاک یا قطع اتصال")
    except requests.exceptions.Timeout:
        logger.warning(f"✗ {source['name']}: timeout")
    except Exception as e:
        logger.warning(f"✗ {source['name']}: {type(e).__name__}: {e}")
    return results


def dedupe(news_list):
    groups = []
    for n in news_list:
        placed = False
        for g in groups:
            if titles_similar(n["title"], g[0]["title"]):
                g.append(n)
                placed = True
                break
        if not placed:
            groups.append([n])
    out = []
    for g in groups:
        best = max(g, key=lambda x: x["priority"])
        best["also"] = [x["source"] for x in g if x["source"] != best["source"]]
        out.append(best)
    return out


def fmt(n):
    stars = "⭐" * n["priority"]
    dt    = n["date"].astimezone(TEHRAN).strftime("%Y/%m/%d  %H:%M")
    summ  = summarize(n["title"], n["body"])
    msg   = f"📰 <b>{n['title']}</b>\n\n"
    if summ:
        msg += f"📝 {summ}\n\n"
    msg += f"🕐 {dt}\n📡 {n['source']} {stars}\n"
    if n.get("also"):
        msg += f"🔁 همین خبر در: {' | '.join(n['also'])}\n"
    msg += f"\n🔗 <a href='{n['link']}'>مشاهده خبر</a>"
    return msg


def run():
    logger.info("=== شروع چرخه ===")
    all_news = []
    for src in RSS_SOURCES:
        all_news.extend(fetch(src))
        time.sleep(1)

    logger.info(f"جمع خبرهای جدید: {len(all_news)}")
    all_news.sort(key=lambda x: x["date"], reverse=True)
    unique = dedupe(all_news)[:15]
    logger.info(f"بعد از حذف تکراری: {len(unique)}")

    sent = 0
    for n in unique:
        if send_telegram(fmt(n)):
            sent_hashes.add(n["hash"])
            sent += 1
            time.sleep(2)
    logger.info(f"=== {sent} خبر ارسال شد ===")


def main():
    logger.info("ربات خبری v4 شروع به کار کرد")
    send_telegram("🚀 <b>ربات خبری مالی ایران v4</b> فعال شد")
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"خطای کلی: {e}", exc_info=True)
        logger.info(f"انتظار {CHECK_INTERVAL} ثانیه...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
