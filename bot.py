import os, time, hashlib, logging, requests, json
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
TEHRAN         = timezone(timedelta(hours=3, minutes=30))

# ================================================================
#  کانال‌ها — برای اضافه کردن رسته جدید:
#  1. یه کانال تلگرام بساز
#  2. ربات رو admin کن
#  3. یه آیتم جدید اینجا اضافه کن
# ================================================================
CHANNELS = {
    "general":   "@financeconnectzone",
    "bank":      "@fcz_bank",
    "fintech":   "@fcz_fintech",
    "bourse":    "@fcz_bourse",
    "insurance": "@fcz_insurance",
    "lending":   "@fcz_lending",
    "business":  "@fcz_business",
}

# ================================================================
#  کلمات کلیدی هر رسته — برای دسته‌بندی خودکار خبرها
# ================================================================
CATEGORY_KEYWORDS = {
    "bank": [
        "بانک","بانکی","بانکداری","بانک مرکزی","شبکه بانکی","نظام بانکی",
        "سپرده","حساب بانکی","کارت بانکی","شتاب","سپام","بانک ملی",
        "بانک صادرات","بانک ملت","بانک تجارت","بانک سپه","بانک مسکن",
        "بانک پارسیان","بانک پاسارگاد","بانک آینده","بانک سامان",
        "نرخ سود","سود بانکی","بهره","ربا","ذخیره قانونی",
        "چک","برات","حواله","انتقال وجه","کارمزد",
        "بانک خصوصی","بانک دولتی","موسسه اعتباری",
    ],
    "fintech": [
        "فینتک","فین‌تک","پرداخت الکترونیک","درگاه پرداخت","پرداختیار",
        "رمزارز","ارز دیجیتال","بیت کوین","بلاکچین","کریپتو","توکن","NFT",
        "استارتاپ مالی","نئوبانک","بانک دیجیتال","کیف پول دیجیتال",
        "پوز","pos","شاپرک","راه پرداخت","عصر تراکنش",
        "اینترنت بانک","موبایل بانک","پرداخت آنلاین",
        "فناوری مالی","دیجیتال","اپلیکیشن مالی",
    ],
    "bourse": [
        "بورس","فرابورس","سهام","سهامداران","شاخص بورس","شاخص کل",
        "اوراق بهادار","صکوک","اوراق مشارکت","اوراق خزانه",
        "صندوق سرمایه گذاری","ETF","عرضه اولیه","IPO",
        "بازار سرمایه","کارگزاری","ناشر","شرکت بورسی",
        "معامله","حجم معاملات","ارزش معاملات","پرتفو",
        "سازمان بورس","بورس تهران","فرابورس","بورس کالا","بورس انرژی",
        "تحلیل تکنیکال","تحلیل بنیادی","کدال",
    ],
    "insurance": [
        "بیمه","بیمه گر","بیمه گذار","بیمه نامه","خسارت بیمه",
        "بیمه عمر","بیمه درمان","بیمه اتومبیل","بیمه شخص ثالث",
        "بیمه مرکزی","بیمه ایران","بیمه آسیا","بیمه البرز",
        "بیمه پاسارگاد","بیمه ملت","بیمه دی","بیمه نوین",
        "حق بیمه","پوشش بیمه","بیمه اجباری","بیمه اختیاری",
    ],
    "lending": [
        "وام","تسهیلات","اعتبار","قرض","قرض الحسنه",
        "لندتک","لنداپ","فین‌لند","اعتبارسنجی","رتبه اعتباری",
        "ضمانت","ضامن","وثیقه","رهن","وام مسکن","وام خودرو",
        "وام ازدواج","وام فرزندآوری","وام اشتغال",
        "مالی خرد","میکروفایننس","تامین مالی جمعی","کراودفاندینگ",
        "وام بدون ضامن","وام آنلاین","اعطای تسهیلات",
    ],
    "business": [
        "کسب و کار","شرکت","سازمان","مدیرعامل","هیئت مدیره",
        "استارتاپ","کارآفرینی","سرمایه گذاری خطرپذیر","VC",
        "مالیات","سازمان مالیاتی","اظهارنامه","معافیت مالیاتی",
        "گمرک","صادرات","واردات","تراز تجاری","تجارت خارجی",
        "بودجه","قانون بودجه","درآمد دولت","یارانه",
        "خصوصی سازی","سهام عدالت","صندوق توسعه ملی",
        "تولید ناخالص","GDP","رشد اقتصادی","رکود","رونق",
        "نرخ ارز","دلار","تورم","نقدینگی",
    ],
}

FINANCE_KEYWORDS = [kw for kws in CATEGORY_KEYWORDS.values() for kw in kws]

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
        active = [s for s in all_s if s.get("active", True)]
        websites  = [s for s in active if s.get("type") != "telegram"]
        telegrams = [s for s in active if s.get("type") == "telegram"]
        logger.info(f"{len(websites)} سایت + {len(telegrams)} کانال تلگرام")
        return websites, telegrams
    except Exception as e:
        logger.error(f"خطا در sources.json: {e}")
        return [], []


def detect_categories(title: str, body: str = "") -> list:
    """تشخیص رسته‌های مرتبط با خبر — ممکنه چند رسته باشه"""
    text = title + " " + body
    matched = []
    for cat, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for k in keywords if k in text)
        if hits >= 1:
            matched.append((cat, hits))
    matched.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in matched[:2]]  # حداکثر ۲ رسته


def score_news(title: str, summary: str = ""):
    text = title + " " + summary
    finance_hits = sum(1 for k in FINANCE_KEYWORDS if k in text)
    if finance_hits == 0:
        return False, 0
    has_exclude = any(k in text for k in EXCLUDE_KEYWORDS)
    has_strong  = any(k in text for k in STRONG_FINANCE)
    if has_exclude and not has_strong:
        return False, 0
    title_hits = sum(2 for k in FINANCE_KEYWORDS if k in title)
    return True, finance_hits + title_hits


def titles_similar(t1: str, t2: str) -> bool:
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود",
            "می","شد","شده","کرد","کرده","خود","برای","های","هر","آن"}
    w1 = set(t1.split()) - stop
    w2 = set(t2.split()) - stop
    if len(w1) < 2 or len(w2) < 2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= 0.6


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
                      f"خبر زیر را در 1 تا 2 جمله کوتاه فارسی خلاصه کن. فقط خلاصه:\n{title}\n{body[:400]}"}]},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"خلاصه: {e}")
    return ""


def send_telegram(msg: str, channel: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": channel, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10,
        )
        if r.status_code != 200:
            logger.error(f"تلگرام {channel}: {r.text}")
        return r.status_code == 200
    except Exception as e:
        logger.error(f"تلگرام {channel}: {e}")
        return False


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
            cats = detect_categories(title)
            results.append({
                "title": title, "link": full_url, "body": "",
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": datetime.now(timezone.utc),
                "score": score, "categories": cats,
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


def fetch_telegram_channel(source: dict) -> list:
    results = []
    try:
        url = source["url"].replace("t.me/", "t.me/s/")
        headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "fa-IR,fa;q=0.9"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        accepted = rejected = 0
        for msg_div in soup.find_all("div", class_="tgme_widget_message_text"):
            text = msg_div.get_text(strip=True)
            if not text or len(text) < 15:
                continue
            msg_wrap = msg_div.find_parent("div", class_="tgme_widget_message_wrap")
            link = source["url"]
            if msg_wrap:
                a = msg_wrap.find("a", class_="tgme_widget_message_date")
                if a:
                    link = a.get("href", source["url"])
            h = hashlib.md5((text[:100] + link).encode()).hexdigest()
            if h in sent_hashes:
                continue
            ok, score = score_news(text[:200])
            if not ok:
                rejected += 1
                continue
            cats = detect_categories(text[:300])
            results.append({
                "title": text[:120] + ("..." if len(text) > 120 else ""),
                "link": link, "body": text,
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": datetime.now(timezone.utc),
                "score": score, "categories": cats,
            })
            accepted += 1
            if accepted >= 5:
                break
        logger.info(f"+ {source['name']} (TG): {accepted} قبول | {rejected} رد")
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
        # ادغام رسته‌های همه نسخه‌های تکراری
        all_cats = []
        for item in g:
            all_cats.extend(item.get("categories", []))
        best["categories"] = list(dict.fromkeys(all_cats))
        out.append(best)
    return out


CAT_LABELS = {
    "bank":      "🏦 بانک و اعتبار",
    "fintech":   "💳 فینتک و پرداخت",
    "bourse":    "📈 بورس و سرمایه",
    "insurance": "🛡 بیمه",
    "lending":   "💰 تسهیلات و لندتک",
    "business":  "🏢 کسب و کار",
}


def fmt(n: dict) -> str:
    stars  = "⭐" * n["priority"]
    dt     = n["date"].astimezone(TEHRAN).strftime("%Y/%m/%d  %H:%M")
    summ   = summarize(n["title"], n["body"])
    cats   = " | ".join(CAT_LABELS.get(c, c) for c in n.get("categories", []))

    msg  = f"📰 <b>{n['title']}</b>\n\n"
    if summ:
        msg += f"📝 {summ}\n\n"
    if cats:
        msg += f"🏷 {cats}\n"
    msg += f"🕐 {dt}\n"
    msg += f"📡 {n['source']} {stars}\n"
    if n.get("also"):
        msg += f"🔁 همچنین در: {' | '.join(n['also'])}\n"
    msg += f"\n🔗 <a href='{n['link']}'>مشاهده خبر</a>"
    return msg


def publish(news: dict):
    """ارسال به کانال جنرال + کانال‌های تخصصی مرتبط"""
    msg = fmt(news)

    # همیشه به کانال جنرال
    if send_telegram(msg, CHANNELS["general"]):
        sent_hashes.add(news["hash"])
        time.sleep(1.5)

    # به کانال‌های تخصصی
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
    all_news.sort(key=lambda x: (x["score"], x["priority"]), reverse=True)
    unique = dedupe(all_news)[:15]
    logger.info(f"بعد از حذف تکراری: {len(unique)}")

    for n in unique:
        publish(n)

    logger.info(f"=== چرخه تمام شد ===")


def main():
    logger.info("ربات خبری مالی v10 شروع به کار کرد")
    send_telegram(
        "🚀 <b>شبکه کانال‌های خبری مالی ایران فعال شد</b>\n\n"
        "📡 کانال‌های فعال:\n"
        "🔹 جنرال: @financeconnectzone\n"
        "🏦 بانک: @fcz_bank\n"
        "💳 فینتک: @fcz_fintech\n"
        "📈 بورس: @fcz_bourse\n"
        "🛡 بیمه: @fcz_insurance\n"
        "💰 تسهیلات: @fcz_lending\n"
        "🏢 کسب‌وکار: @fcz_business",
        CHANNELS["general"]
    )
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"خطای کلی: {e}", exc_info=True)
        logger.info(f"انتظار {CHECK_INTERVAL} ثانیه...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
