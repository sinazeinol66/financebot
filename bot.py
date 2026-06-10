import os, time, hashlib, logging, requests, json
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID     = os.environ.get("CHANNEL_ID", "@financeconnectzone")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
TEHRAN         = timezone(timedelta(hours=3, minutes=30))

def load_sources():
    try:
        with open("sources.json", encoding="utf-8") as f:
            all_s = json.load(f)
        active = [s for s in all_s if s.get("active", True)]
        websites = [s for s in active if s.get("type") != "telegram"]
        telegrams = [s for s in active if s.get("type") == "telegram"]
        logger.info(f"{len(websites)} سایت + {len(telegrams)} کانال تلگرام بارگذاری شد")
        return websites, telegrams
    except Exception as e:
        logger.error(f"خطا در sources.json: {e}")
        return [], []

INCLUDE_KEYWORDS = [
    "بانک","بانکی","بانکداری","بانک مرکزی","وام","تسهیلات","اعتبار","سپرده",
    "نرخ سود","سود بانکی","بهره","کارمزد","چک","حواله","انتقال وجه","پرداخت",
    "ارز","دلار","یورو","پوند","درهم","ریال","تومان","نقدینگی","پایه پولی",
    "تورم","نرخ تورم","شاخص قیمت","صرافی","بازار ارز","نرخ ارز",
    "بورس","فرابورس","سهام","شاخص بورس","شاخص کل","اوراق","اوراق بهادار",
    "صکوک","صندوق سرمایه گذاری","صندوق","ETF","عرضه اولیه","IPO",
    "سرمایه گذاری","بازار سرمایه","بازار مالی","معامله","کارگزاری",
    "بیمه","بیمه مرکزی","فینتک","پرداخت الکترونیک","درگاه پرداخت",
    "رمزارز","ارز دیجیتال","بیت کوین","بلاکچین","کارت بانکی","شتاب",
    "سازمان بورس","وزارت اقتصاد","مالیات","گمرک","صادرات","واردات",
    "بودجه","خصوصی سازی","سهام عدالت","صندوق توسعه ملی",
    "اقتصاد","اقتصادی","رشد اقتصادی","رکود","رونق",
]

EXCLUDE_KEYWORDS = [
    "جنگ","حمله","موشک","پهپاد","سپاه","ارتش","نظامی",
    "انتخابات","کاندیدا","استیضاح","قوه قضاییه","دادگاه",
    "زندان","اعدام","بازداشت","دستگیری",
    "فوتبال","ورزش","سینما","فیلم","موسیقی",
    "مدرسه","کنکور","زلزله","سیل","واکسن","بیمارستان",
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
                      f"خبر زیر را در 1 تا 2 جمله کوتاه فارسی خلاصه کن. فقط خلاصه:\n{title}\n{body[:400]}"}]},
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

def fetch_website(source):
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }
    try:
        resp = requests.get(source["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        base = urlparse(source["url"])
        seen_urls = set()
        accepted = rejected = 0
        for a in soup.find_all("a", href=True):
            href  = a["href"].strip()
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = f"{base.scheme}://{base.netloc}{href}"
            else:
                continue
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            h = hashlib.md5((title + full_url).encode()).hexdigest()
            if h in sent_hashes:
                continue
            ok, score = score_news(title)
            if not ok:
                rejected += 1
                continue
            results.append({
                "title": title, "link": full_url, "body": "",
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": datetime.now(timezone.utc), "score": score,
            })
            accepted += 1
            if accepted >= 10:
                break
        logger.info(f"+ {source['name']}: {accepted} قبول | {rejected} رد")
    except requests.exceptions.ConnectionError:
        logger.warning(f"- {source['name']}: قطع اتصال")
    except requests.exceptions.Timeout:
        logger.warning(f"- {source['name']}: timeout")
    except Exception as e:
        logger.warning(f"- {source['name']}: {e}")
    return results

def fetch_telegram_channel(source):
    """خواندن پیام‌های عمومی کانال تلگرام از طریق t.me"""
    results = []
    try:
        # تبدیل t.me/channel به t.me/s/channel برای نمایش وب
        url = source["url"].replace("t.me/", "t.me/s/")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,*/*",
            "Accept-Language": "fa-IR,fa;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")

        accepted = rejected = 0
        for msg_div in soup.find_all("div", class_="tgme_widget_message_text"):
            text = msg_div.get_text(strip=True)
            if not text or len(text) < 15:
                continue
            # لینک پیام
            msg_wrap = msg_div.find_parent("div", class_="tgme_widget_message_wrap")
            link = ""
            if msg_wrap:
                a = msg_wrap.find("a", class_="tgme_widget_message_date")
                if a:
                    link = a.get("href", "")
            if not link:
                link = source["url"]

            h = hashlib.md5((text[:100] + link).encode()).hexdigest()
            if h in sent_hashes:
                continue
            ok, score = score_news(text[:200])
            if not ok:
                rejected += 1
                continue
            results.append({
                "title": text[:120] + ("..." if len(text) > 120 else ""),
                "link": link, "body": text,
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": datetime.now(timezone.utc), "score": score,
            })
            accepted += 1
            if accepted >= 5:
                break
        logger.info(f"+ {source['name']} (TG): {accepted} قبول | {rejected} رد")
    except Exception as e:
        logger.warning(f"- {source['name']} (TG): {e}")
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
    websites, telegrams = load_sources()
    logger.info("=== شروع چرخه ===")
    all_news = []

    for src in websites:
        all_news.extend(fetch_website(src))
        time.sleep(1)

    for src in telegrams:
        all_news.extend(fetch_telegram_channel(src))
        time.sleep(1)

    logger.info(f"بعد از فیلتر: {len(all_news)}")
    all_news.sort(key=lambda x: (x["score"], x["priority"]), reverse=True)
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
    logger.info("ربات خبری مالی v9 شروع به کار کرد")
    send_telegram("🚀 <b>ربات خبری مالی ایران v9</b>\n45 سایت + 18 کانال تلگرام فعال شد")
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"خطای کلی: {e}", exc_info=True)
        logger.info(f"انتظار {CHECK_INTERVAL} ثانیه...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
