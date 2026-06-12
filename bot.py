import os, time, hashlib, logging, requests, json
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import feedparser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
TEHRAN         = timezone(timedelta(hours=3, minutes=30))
MAX_AGE_HOURS  = 6

CHANNELS = {
    "general":   "@financeconnectzone",
    "bank":      "@fcz_bank",
    "fintech":   "@fcz_fintech",
    "bourse":    "@fcz_bourse",
    "insurance": "@fcz_insurance",
    "lending":   "@fcz_lending",
    "business":  "@fcz_business",
}

CATEGORY_KEYWORDS = {
    "bank": [
        "بانک","بانکی","بانکداری","بانک مرکزی","شبکه بانکی","نظام بانکی",
        "سپرده","حساب بانکی","کارت بانکی","شتاب","سپام",
        "بانک ملی","بانک صادرات","بانک ملت","بانک تجارت","بانک سپه",
        "بانک مسکن","بانک پارسیان","بانک پاسارگاد","بانک آینده","بانک سامان",
        "نرخ سود","سود بانکی","بهره","ربا","ذخیره قانونی",
        "چک","برات","حواله","انتقال وجه","کارمزد",
        "بانک خصوصی","بانک دولتی","موسسه اعتباری",
    ],
    "fintech": [
        "فینتک","فین‌تک","پرداخت الکترونیک","درگاه پرداخت","پرداختیار",
        "رمزارز","ارز دیجیتال","بیت کوین","بلاکچین","کریپتو","توکن",
        "استارتاپ مالی","نئوبانک","بانک دیجیتال","کیف پول دیجیتال",
        "پوز","pos","شاپرک","راه پرداخت","عصر تراکنش",
        "اینترنت بانک","موبایل بانک","پرداخت آنلاین","فناوری مالی",
    ],
    "bourse": [
        "بورس","فرابورس","سهام","سهامداران","شاخص بورس","شاخص کل",
        "اوراق بهادار","صکوک","اوراق مشارکت","اوراق خزانه",
        "صندوق سرمایه گذاری","ETF","عرضه اولیه","IPO",
        "بازار سرمایه","کارگزاری","بورس تهران","بورس کالا","بورس انرژی",
        "معامله","حجم معاملات","ارزش معاملات","کدال","سازمان بورس",
    ],
    "insurance": [
        "بیمه","بیمه گر","بیمه گذار","بیمه نامه","خسارت بیمه",
        "بیمه عمر","بیمه درمان","بیمه اتومبیل","بیمه شخص ثالث",
        "بیمه مرکزی","بیمه ایران","بیمه آسیا","بیمه البرز",
        "حق بیمه","پوشش بیمه","بیمه اجباری",
    ],
    "lending": [
        "وام","تسهیلات","اعتبار","قرض","قرض الحسنه",
        "لندتک","اعتبارسنجی","رتبه اعتباری",
        "ضمانت","وثیقه","وام مسکن","وام خودرو",
        "وام ازدواج","وام اشتغال","مالی خرد","میکروفایننس",
        "تامین مالی جمعی","کراودفاندینگ","وام آنلاین",
    ],
    "business": [
        "کسب و کار","شرکت","مدیرعامل","هیئت مدیره",
        "استارتاپ","کارآفرینی","سرمایه گذاری خطرپذیر",
        "مالیات","سازمان مالیاتی","معافیت مالیاتی",
        "گمرک","صادرات","واردات","تراز تجاری",
        "بودجه","درآمد دولت","خصوصی سازی","سهام عدالت",
        "تولید ناخالص","GDP","رشد اقتصادی","رکود","تورم","نقدینگی",
    ],
}

HASHTAGS = {
    "bank":      "#بانک",
    "fintech":   "#فینتک",
    "bourse":    "#بورس",
    "insurance": "#بیمه",
    "lending":   "#تسهیلات",
    "business":  "#کسب_و_کار",
}

FINANCE_KEYWORDS = list({kw for kws in CATEGORY_KEYWORDS.values() for kw in kws})
EXCLUDE_KEYWORDS = [
    "جنگ","حمله","موشک","پهپاد","سپاه","ارتش","نظامی",
    "انتخابات","کاندیدا","استیضاح","قوه قضاییه","دادگاه",
    "زندان","اعدام","بازداشت","دستگیری",
    "فوتبال","ورزش","سینما","فیلم","موسیقی",
    "مدرسه","کنکور","زلزله","سیل","واکسن","بیمارستان",
]
STRONG_FINANCE = [
    "بانک","وام","تسهیلات","بورس","سهام","ارز","مالیات",
    "بیمه","سرمایه","پرداخت","اوراق","صندوق","نرخ سود","فینتک",
]

sent_hashes: set = set()


def load_sources():
    try:
        with open("sources.json", encoding="utf-8") as f:
            all_s = json.load(f)
        active    = [s for s in all_s if s.get("active", True)]
        websites  = [s for s in active if s.get("type") != "telegram"]
        telegrams = [s for s in active if s.get("type") == "telegram"]
        logger.info(f"{len(websites)} سایت + {len(telegrams)} کانال تلگرام")
        return websites, telegrams
    except Exception as e:
        logger.error(f"خطا: {e}")
        return [], []


def is_fresh(pub_date: datetime) -> bool:
    age = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
    return age <= MAX_AGE_HOURS


def detect_categories(title: str, body: str = "") -> list:
    text = title + " " + body
    matched = [(cat, sum(1 for k in kws if k in text))
               for cat, kws in CATEGORY_KEYWORDS.items()]
    matched = [(c, s) for c, s in matched if s > 0]
    matched.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in matched[:2]]


def score_news(title: str, summary: str = ""):
    text = title + " " + summary
    hits = sum(1 for k in FINANCE_KEYWORDS if k in text)
    if hits == 0:
        return False, 0
    if any(k in text for k in EXCLUDE_KEYWORDS) and not any(k in text for k in STRONG_FINANCE):
        return False, 0
    return True, hits + sum(2 for k in FINANCE_KEYWORDS if k in title)


def titles_similar(t1: str, t2: str) -> bool:
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود",
            "می","شد","شده","کرد","کرده","خود","برای","های","هر","آن"}
    w1 = set(t1.split()) - stop
    w2 = set(t2.split()) - stop
    if len(w1) < 2 or len(w2) < 2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= 0.6


def make_headline(title: str, body: str) -> str:
    """ساخت تیتر ۱۰ کلمه‌ای با AI"""
    if not ANTHROPIC_KEY:
        # بدون AI: ۱۰ کلمه اول عنوان
        words = title.split()
        return " ".join(words[:10]) + ("..." if len(words) > 10 else "")
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 60,
                  "messages": [{"role": "user", "content":
                      f"این خبر را در دقیقاً ۱۰ کلمه فارسی خلاصه کن. "
                      f"باید مضمون اصلی خبر کاملاً مشخص باشد. "
                      f"فقط همان ۱۰ کلمه، بدون نقطه یا علامت اضافه:\n"
                      f"{title}\n{body[:300]}"}]},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"AI: {e}")
    words = title.split()
    return " ".join(words[:10]) + ("..." if len(words) > 10 else "")


def send_telegram(msg: str, channel: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": channel, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        if r.status_code != 200:
            logger.error(f"{channel}: {r.text}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"{channel}: {e}")
        return False


def parse_rss_date(entry) -> datetime | None:
    for a in ("published_parsed", "updated_parsed"):
        t = getattr(entry, a, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except:
                pass
    return None


def fetch_website(source: dict) -> list:
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,*/*",
        "Accept-Language": "fa-IR,fa;q=0.9",
        "Referer": "https://www.google.com/",
    }
    try:
        resp = requests.get(source["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "xml" in ct or "rss" in ct:
            feed = feedparser.parse(resp.content)
            for e in feed.entries[:20]:
                title   = (e.get("title") or "").strip()
                link    = (e.get("link") or "").strip()
                summary = e.get("summary") or ""
                if not title or not link:
                    continue
                pub_date = parse_rss_date(e) or datetime.now(timezone.utc)
                if not is_fresh(pub_date):
                    continue
                h = hashlib.md5((title + link).encode()).hexdigest()
                if h in sent_hashes:
                    continue
                ok, score = score_news(title, summary)
                if not ok:
                    continue
                results.append({
                    "title": title, "link": link, "body": summary,
                    "source": source["name"], "priority": source.get("priority", 2),
                    "hash": h, "date": pub_date, "score": score,
                    "categories": detect_categories(title, summary),
                })
            logger.info(f"+ {source['name']} (RSS): {len(results)} خبر تازه")
            return results

        soup = BeautifulSoup(resp.content, "lxml")
        base = urlparse(source["url"])
        seen = set()
        accepted = 0
        for a in soup.find_all("a", href=True):
            href  = a["href"].strip()
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            full_url = href if href.startswith("http") else (
                f"{base.scheme}://{base.netloc}{href}" if href.startswith("/") else None)
            if not full_url or full_url in seen:
                continue
            seen.add(full_url)
            h = hashlib.md5((title + full_url).encode()).hexdigest()
            if h in sent_hashes:
                continue
            ok, score = score_news(title)
            if not ok:
                continue
            results.append({
                "title": title, "link": full_url, "body": "",
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": datetime.now(timezone.utc),
                "score": score, "categories": detect_categories(title),
            })
            accepted += 1
            if accepted >= 10:
                break
        logger.info(f"+ {source['name']}: {accepted} خبر")
    except requests.exceptions.ConnectionError:
        logger.warning(f"- {source['name']}: قطع اتصال")
    except requests.exceptions.Timeout:
        logger.warning(f"- {source['name']}: timeout")
    except Exception as e:
        logger.warning(f"- {source['name']}: {e}")
    return results


def fetch_telegram_channel(source: dict) -> list:
    results = []
    try:
        url = source["url"].replace("t.me/", "t.me/s/")
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        accepted = 0
        for wrap in soup.find_all("div", class_="tgme_widget_message_wrap"):
            time_tag = wrap.find("time")
            pub_date = datetime.now(timezone.utc)
            if time_tag and time_tag.get("datetime"):
                try:
                    pub_date = datetime.fromisoformat(
                        time_tag["datetime"].replace("Z", "+00:00"))
                except:
                    pass
            if not is_fresh(pub_date):
                continue
            msg_div = wrap.find("div", class_="tgme_widget_message_text")
            if not msg_div:
                continue
            text = msg_div.get_text(strip=True)
            if not text or len(text) < 15:
                continue
            link = source["url"]
            a = wrap.find("a", class_="tgme_widget_message_date")
            if a:
                link = a.get("href", link)
            h = hashlib.md5((text[:100] + link).encode()).hexdigest()
            if h in sent_hashes:
                continue
            ok, score = score_news(text[:200])
            if not ok:
                continue
            results.append({
                "title": text[:150], "link": link, "body": text,
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": pub_date, "score": score,
                "categories": detect_categories(text[:300]),
            })
            accepted += 1
            if accepted >= 5:
                break
        logger.info(f"+ {source['name']} (TG): {accepted} خبر")
    except Exception as e:
        logger.warning(f"- {source['name']} (TG): {e}")
    return results


def dedupe(news_list: list) -> list:
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
        all_cats = []
        for item in g:
            all_cats.extend(item.get("categories", []))
        best["categories"] = list(dict.fromkeys(all_cats))
        out.append(best)
    return out


def fmt(n: dict) -> str:
    headline = make_headline(n["title"], n["body"])
    cats  = n.get("categories", [])
    tags  = " ".join(HASHTAGS.get(c, "") for c in cats).strip()
    also  = " | ".join(n["also"]) if n.get("also") else ""

    msg  = f"<b>{headline}</b>\n"
    msg += f"<i>{n['source']}</i>"
    if also:
        msg += f" · {also}"
    msg += "\n"
    if tags:
        msg += f"{tags}\n"
    msg += f"🔗 <a href='{n['link']}'>جزئیات خبر</a>"
    return msg


def publish(news: dict):
    msg = fmt(news)
    if send_telegram(msg, CHANNELS["general"]):
        sent_hashes.add(news["hash"])
        time.sleep(1.5)
    for cat in news.get("categories", []):
        if cat in CHANNELS:
            send_telegram(msg, CHANNELS[cat])
            time.sleep(1.5)


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
    unique = dedupe(sorted(all_news, key=lambda x: (x["score"], x["priority"]), reverse=True))[:15]
    logger.info(f"بعد از حذف تکراری: {len(unique)}")
    for n in unique:
        publish(n)
    logger.info("=== تمام ===")


def main():
    logger.info("ربات خبری v12 شروع به کار کرد")
    send_telegram("🚀 <b>شبکه خبری مالی ایران v12</b> فعال شد", CHANNELS["general"])
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"خطا: {e}", exc_info=True)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
