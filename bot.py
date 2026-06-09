import os, time, hashlib, logging, requests, json
from datetime import datetime, timezone, timedelta
import feedparser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID     = os.environ.get("CHANNEL_ID", "@financeconnectzone")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
TEHRAN         = timezone(timedelta(hours=3, minutes=30))

# بارگذاری منابع از فایل sources.json
def load_sources():
    try:
        with open("sources.json", encoding="utf-8") as f:
            all_sources = json.load(f)
        active = [s for s in all_sources if s.get("active", True)]
        logger.info(f"{len(active)} منبع فعال بارگذاری شد")
        return active
    except Exception as e:
        logger.error(f"خطا در بارگذاری sources.json: {e}")
        return []

INCLUDE_KEYWORDS = [
    "بانک","بانکی","بانکداری","بانک مرکزی","شبکه بانکی","نظام بانکی",
    "وام","تسهیلات","اعتبار","سپرده","حساب","ضمانت نامه",
    "نرخ سود","سود بانکی","بهره","کارمزد",
    "چک","برات","حواله","انتقال وجه","پرداخت",
    "ارز","دلار","یورو","پوند","درهم","لیر","یوان","روبل",
    "ریال","تومان","نقدینگی","پایه پولی","حجم پول",
    "تورم","نرخ تورم","شاخص قیمت","گرانی",
    "صرافی","بازار ارز","نرخ ارز",
    "بورس","فرابورس","سهام","سهامداران","شاخص بورس","شاخص کل",
    "اوراق","اوراق بهادار","صکوک","اوراق مشارکت",
    "صندوق سرمایه گذاری","صندوق","ETF","عرضه اولیه","IPO",
    "سرمایه گذاری","بازار سرمایه","بازار مالی",
    "معامله","معاملات","حجم معاملات","ارزش معاملات","کارگزاری",
    "بیمه","بیمه گر","بیمه نامه","بیمه مرکزی",
    "فینتک","پرداخت الکترونیک","درگاه پرداخت",
    "رمزارز","ارز دیجیتال","بیت کوین","بلاکچین","کریپتو",
    "کارت بانکی","کارت اعتباری","شتاب","سپام",
    "سازمان بورس","وزارت اقتصاد",
    "مالیات","مالیاتی","سازمان مالیاتی",
    "گمرک","تعرفه","صادرات","واردات","تراز تجاری",
    "بودجه","قانون بودجه","درآمد دولت",
    "خصوصی سازی","سهام عدالت","صندوق توسعه ملی",
    "اقتصاد","اقتصادی","رشد اقتصادی","رکود","رونق",
]

EXCLUDE_KEYWORDS = [
    "جنگ","حمله","موشک","پهپاد","سپاه","ارتش","نظامی",
    "انتخابات","رای","کاندیدا","حزب","استیضاح",
    "قوه قضاییه","دادگاه","زندان","اعدام","بازداشت","دستگیری",
    "فوتبال","ورزش","سینما","فیلم","موسیقی",
    "آموزش","مدرسه","کنکور","زلزله","سیل","آتش سوزی",
    "پزشکی","واکسن","بیمارستان",
]

STRONG_FINANCE = [
    "بانک","وام","تسهیلات","بورس","سهام","ارز","مالیات",
    "بیمه","سرمایه","پرداخت","اوراق","صندوق","نرخ سود",
]

sent_hashes: set = set()


def score_news(title, summary=""):
    text = title + " " + summary
    finance_hits = sum(1 for k in INCLUDE_KEYWORDS if k in text)
    if finance_hits == 0:
        return False, 0
    has_exclude = any(k in text for k in EXCLUDE_KEYWORDS)
    has_strong  = any(k in text for k in STRONG_FINANCE)
    if has_exclude and not has_strong:
        return False, 0
    title_hits = sum(2 for k in INCLUDE_KEYWORDS if k in title)
    return True, finance_hits + title_hits


def titles_similar(t1, t2):
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود",
            "می","شد","شده","کرد","کرده","خود","برای","های","هر","آن"}
    w1 = set(t1.split()) - stop
    w2 = set(t2.split()) - stop
    if len(w1) < 2 or len(w2) < 2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= 0.6


def summarize(title, body):
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
                      f"خبر زیر را در 1 تا 2 جمله کوتاه فارسی خلاصه کن. فقط خلاصه بنویس:\n{title}\n{body[:400]}"}]},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"خلاصه: {e}")
    return ""


def send_telegram(msg):
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Language": "fa-IR,fa;q=0.9",
    }
    try:
        resp = requests.get(source["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            feed = feedparser.parse(source["url"], request_headers=headers)
        accepted = rejected = 0
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
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": parse_date(e), "score": score,
            })
            accepted += 1
        logger.info(f"+ {source['name']}: {accepted} قبول | {rejected} رد")
    except requests.exceptions.ConnectionError:
        logger.warning(f"- {source['name']}: قطع اتصال")
    except requests.exceptions.Timeout:
        logger.warning(f"- {source['name']}: timeout")
    except Exception as e:
        logger.warning(f"- {source['name']}: {e}")
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
        best = max(g, key=lambda x: (x["score"], x["priority"]))
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
    msg += f"🕐 {dt}\n"
    msg += f"📡 {n['source']} {stars}\n"
    if n.get("also"):
        msg += f"🔁 همچنین در: {' | '.join(n['also'])}\n"
    msg += f"\n🔗 <a href='{n['link']}'>مشاهده خبر</a>"
    return msg


def run():
    sources = load_sources()
    if not sources:
        logger.error("هیچ منبعی بارگذاری نشد")
        return
    logger.info("=== شروع چرخه ===")
    all_news = []
    for src in sources:
        all_news.extend(fetch(src))
        time.sleep(0.8)
    logger.info(f"بعد از فیلتر موضوعی: {len(all_news)}")
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
    logger.info("ربات خبری مالی v6 شروع به کار کرد")
    send_telegram("🚀 <b>ربات خبری مالی ایران v6</b> فعال شد")
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"خطای کلی: {e}", exc_info=True)
        logger.info(f"انتظار {CHECK_INTERVAL} ثانیه...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
