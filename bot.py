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
# ================================================================
RSS_SOURCES = [
    {"name": "ایرنا اقتصادی",   "url": "https://www.irna.ir/rss/economy/",             "priority": 3},
    {"name": "تسنیم اقتصادی",   "url": "https://www.tasnimnews.com/fa/rss/feed/0/5/0", "priority": 3},
    {"name": "فارس اقتصادی",    "url": "https://www.farsnews.ir/rss/economy",           "priority": 3},
    {"name": "ایسنا اقتصادی",   "url": "https://www.isna.ir/rss/tp-economy",            "priority": 3},
    {"name": "مهر اقتصادی",     "url": "https://www.mehrnews.com/rss/economy",          "priority": 3},
    {"name": "دنیای اقتصاد",    "url": "https://www.donya-e-eqtesad.com/rss",           "priority": 3},
    {"name": "اقتصادنیوز",      "url": "https://www.eghtesadnews.com/rss",              "priority": 3},
    {"name": "بانکداری ایران",   "url": "https://www.bankdari.ir/rss",                  "priority": 2},
    {"name": "بانک مرکزی",      "url": "https://www.cbi.ir/rss/news.aspx",              "priority": 3},
    {"name": "سازمان بورس",     "url": "https://www.seo.ir/rss",                        "priority": 3},
    {"name": "عصر ایران",       "url": "https://www.asriran.com/rss/economy",           "priority": 2},
    {"name": "اقتصاد آنلاین",   "url": "https://www.eghtesadonline.com/rss",            "priority": 3},
    {"name": "تجارت‌نیوز",      "url": "https://www.tejaratnews.com/rss",               "priority": 3},
    {"name": "ایبنا",           "url": "https://www.ibena.ir/rss",                      "priority": 3},
    {"name": "راه پرداخت",      "url": "https://way2pay.ir/feed",                       "priority": 3},
    {"name": "بورس‌نیوز",       "url": "https://www.boursenews.ir/rss",                 "priority": 3},
]
# ================================================================

# ================================================================
#  کلمات کلیدی مرتبط — خبر باید حداقل یکی از اینها را داشته باشد
# ================================================================
INCLUDE_KEYWORDS = [
    # بانک و اعتبار
    "بانک","بانکی","بانکداری","بانک مرکزی","شبکه بانکی","نظام بانکی",
    "وام","تسهیلات","اعتبار","سپرده","حساب","ضمانت‌نامه","ضمانتنامه",
    "نرخ سود","سود بانکی","بهره","کارمزد","ربا",
    "چک","برات","حواله","انتقال وجه","پرداخت",
    # پول و ارز
    "ارز","دلار","یورو","پوند","درهم","لیر","یوان","روبل",
    "ریال","تومان","نقدینگی","پایه پولی","حجم پول",
    "تورم","نرخ تورم","شاخص قیمت","CPI","گرانی",
    "صرافی","صرافان","بازار ارز","نرخ ارز",
    # بورس و سرمایه
    "بورس","فرابورس","سهام","سهامداران","شاخص بورس","شاخص کل",
    "اوراق","اوراق بهادار","اوراق قرضه","صکوک","اوراق مشارکت",
    "صندوق سرمایه‌گذاری","صندوق","ETF","عرضه اولیه","IPO",
    "سرمایه‌گذاری","سرمایه‌گذار","بازار سرمایه","بازار مالی",
    "معامله","معاملات","حجم معاملات","ارزش معاملات",
    "کارگزاری","ناشر","شرکت بورسی",
    # بیمه
    "بیمه","بیمه‌گر","بیمه‌گذار","بیمه‌نامه","خسارت بیمه",
    "بیمه عمر","بیمه درمان","بیمه اتومبیل","بیمه مرکزی",
    # فینتک و پرداخت
    "فینتک","فین‌تک","پرداخت الکترونیک","درگاه پرداخت",
    "رمزارز","ارز دیجیتال","بیت‌کوین","بلاکچین","کریپتو","توکن",
    "کارت بانکی","کارت اعتباری","پوز","pos","شتاب","سپام",
    "استارت‌آپ مالی","نئوبانک","بانک دیجیتال",
    # نهادها و قوانین مالی
    "سازمان بورس","بانک مرکزی","وزارت اقتصاد","وزارت امور اقتصادی",
    "مالیات","مالیاتی","سازمان مالیاتی","اداره مالیات",
    "گمرک","تعرفه","صادرات","واردات","تراز تجاری",
    "بودجه","قانون بودجه","درآمد دولت","هزینه دولت",
    "خصوصی‌سازی","سهام عدالت","صندوق توسعه ملی",
    # اقتصاد کلان مرتبط
    "اقتصاد","اقتصادی","رشد اقتصادی","رکود","رونق",
    "تولید ناخالص","GDP","سرمایه‌گذاری خارجی","FDI",
]

# ================================================================
#  کلمات حذفی — اگر خبر این کلمات را داشت، حذف می‌شود
#  (مگر اینکه کلمه مالی قوی هم باشد)
# ================================================================
EXCLUDE_KEYWORDS = [
    # سیاسی و نظامی
    "جنگ","حمله","موشک","پهپاد","سپاه","ارتش","نظامی","دفاعی",
    "انتخابات","رأی","کاندیدا","حزب","مجلس","دولت","رئیس‌جمهور",
    "وزیر","نماینده","استیضاح","قوه قضاییه","دادگاه","محاکمه",
    "زندان","اعدام","بازداشت","دستگیری","کیفری",
    "تحریم سیاسی","مذاکرات هسته‌ای","برجام","هسته‌ای",
    # اجتماعی و فرهنگی
    "طلاق","ازدواج","فوتبال","ورزش","سینما","فیلم","موسیقی",
    "آموزش","مدرسه","دانشگاه","کنکور","امتحان",
    "آب‌وهوا","زلزله","سیل","آتش‌سوزی","حادثه",
    "پزشکی","بهداشت","واکسن","بیمارستان","جراحی",
    "مسکن","خانه","اجاره","رهن",  # مگر با کلمات مالی
    "خودرو","ماشین","خودروسازی",  # مگر با تسهیلات/لیزینگ
]

# کلمات مالی قوی که حتی اگر کلمه حذفی باشد، خبر را نگه می‌دارد
STRONG_FINANCE = [
    "بانک","وام","تسهیلات","بورس","سهام","ارز","مالیات",
    "بیمه","سرمایه","پرداخت","اوراق","صندوق","نرخ سود",
]
# ================================================================

sent_hashes: set = set()


def score_news(title: str, summary: str = "") -> tuple[bool, int]:
    """
    returns (should_publish, score)
    score: بالاتر = مرتبط‌تر
    """
    text = title + " " + summary

    # تعداد کلمات مالی مرتبط
    finance_hits = sum(1 for k in INCLUDE_KEYWORDS if k in text)
    if finance_hits == 0:
        return False, 0

    # بررسی کلمات حذفی
    has_exclude = any(k in text for k in EXCLUDE_KEYWORDS)
    has_strong  = any(k in text for k in STRONG_FINANCE)

    if has_exclude and not has_strong:
        return False, 0

    # امتیاز: هر کلمه مالی = 1 امتیاز، اگر در عنوان = 2 امتیاز
    title_hits = sum(2 for k in INCLUDE_KEYWORDS if k in title)
    score = finance_hits + title_hits
    return True, score


def titles_similar(t1: str, t2: str) -> bool:
    """تشخیص اخبار تکراری با مقایسه کلمات"""
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود",
            "می","شد","شده","کرد","کرده","خود","برای","های","هر","آن"}
    w1 = set(t1.split()) - stop
    w2 = set(t2.split()) - stop
    if len(w1) < 2 or len(w2) < 2:
        return False
    overlap = len(w1 & w2) / min(len(w1), len(w2))
    return overlap >= 0.6


def summarize(title: str, body: str) -> str:
    if not ANTHROPIC_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 120,
                  "messages": [{"role": "user", "content":
                      f"خبر زیر را در ۱ تا ۲ جمله کوتاه فارسی خلاصه کن. "
                      f"فقط خلاصه بنویس، بدون مقدمه:\n{title}\n{body[:400]}"}]},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"خلاصه: {e}")
    return ""


def send_telegram(msg: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHANNEL_ID, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10,
        )
        if r.status_code != 200:
            logger.error(f"تلگرام: {r.text}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"تلگرام: {e}")
        return False


def parse_date(entry) -> datetime:
    for a in ("published_parsed", "updated_parsed"):
        t = getattr(entry, a, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except:
                pass
    return datetime.now(timezone.utc)


def fetch(source: dict) -> list:
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
               "Accept": "*/*"}
    try:
        resp = requests.get(source["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        if not feed.entries:
            feed = feedparser.parse(source["url"], request_headers=headers)

        accepted = 0
        rejected = 0
        for e in feed.entries[:25]:
            title   = (e.get("title") or "").strip()
            link    = (e.get("link") or "").strip()
            summary = e.get("summary") or ""
            if not title or not link:
                continue

            h = hashlib.md5((title + link).encode()).hexdigest()
            if h in sent_hashes:
                continue

            ok, score = score_news(title, summary)
            if not ok:
                rejected += 1
                continue

            results.append({
                "title": title, "link": link, "body": summary,
                "source": source["name"], "priority": source["priority"],
                "hash": h, "date": parse_date(e), "score": score,
            })
            accepted += 1

        logger.info(f"✓ {source['name']}: {accepted} قبول | {rejected} رد")
    except requests.exceptions.ConnectionError:
        logger.warning(f"✗ {source['name']}: قطع اتصال")
    except requests.exceptions.Timeout:
        logger.warning(f"✗ {source['name']}: timeout")
    except Exception as e:
        logger.warning(f"✗ {source['name']}: {e}")
    return results


def dedupe(news_list: list) -> list:
    """حذف اخبار تکراری — بهترین نسخه هر خبر باقی می‌ماند"""
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
        # بهترین: اول score، بعد priority
        best = max(g, key=lambda x: (x["score"], x["priority"]))
        best["also"] = [x["source"] for x in g if x["source"] != best["source"]]
        out.append(best)
    return out


def fmt(n: dict) -> str:
    stars = "⭐" * n["priority"]
    dt    = n["date"].astimezone(TEHRAN).strftime("%Y/%m/%d  %H:%M")
    summ  = summarize(n["title"], n["body"])

    msg  = f"📰 <b>{n['title']}</b>\n\n"
    if summ:
        msg += f"📝 {summ}\n\n"
    msg += f"🕐 {dt}\n"
    msg += f"📡 {n['source']} {stars}\n"
    if n.get("also"):
        msg += f"🔁 پوشش داده شده در: {' | '.join(n['also'])}\n"
    msg += f"\n🔗 <a href='{n['link']}'>مشاهده خبر</a>"
    return msg


def run():
    logger.info("=== شروع چرخه ===")
    all_news = []
    for src in RSS_SOURCES:
        all_news.extend(fetch(src))
        time.sleep(0.8)

    logger.info(f"جمع بعد از فیلتر موضوعی: {len(all_news)}")
    all_news.sort(key=lambda x: (x["score"], x["date"].timestamp()), reverse=True)
    unique = dedupe(all_news)[:12]
    logger.info(f"بعد از حذف تکراری: {len(unique)}")

    sent = 0
    for n in unique:
        if send_telegram(fmt(n)):
            sent_hashes.add(n["hash"])
            sent += 1
            time.sleep(2)
    logger.info(f"=== {sent} خبر ارسال شد ===")


def main():
    logger.info("ربات خبری مالی v5 شروع به کار کرد")
    send_telegram("🚀 <b>ربات خبری مالی ایران v5</b>\nفیلتر هوشمند موضوعی فعال شد ✅")
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"خطای کلی: {e}", exc_info=True)
        logger.info(f"انتظار {CHECK_INTERVAL} ثانیه...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
