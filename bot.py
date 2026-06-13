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
MAX_AGE_HOURS  = 24  # خبرهای بیشتر از ۲۴ ساعت نادیده گرفته می‌شن

CHANNELS = {
    "general":   "@financeconnectzone",
    "bank":      "@fcz_bank",
    "fintech":   "@fcz_fintech",
    "bourse":    "@fcz_bourse",
    "insurance": "@fcz_insurance",
    "lending":   "@fcz_lending",
    "business":  "@fcz_business",
}

HASHTAG_MAP = {
    "نرخ سود": "#نرخ_سود", "سود بانکی": "#نرخ_سود", "بهره": "#نرخ_سود",
    "سپرده": "#سپرده_گذاری", "وام مسکن": "#وام_مسکن", "وام خودرو": "#وام_خودرو",
    "وام ازدواج": "#وام_ازدواج", "وام اشتغال": "#وام_اشتغال", "وام": "#وام",
    "تسهیلات": "#تسهیلات", "چک": "#چک_بانکی", "قرض الحسنه": "#قرض_الحسنه",
    "بانک مرکزی": "#بانک_مرکزی", "بانک ملی": "#بانک_ملی",
    "بانک صادرات": "#بانک_صادرات", "بانک ملت": "#بانک_ملت",
    "بانک تجارت": "#بانک_تجارت", "بانک سپه": "#بانک_سپه",
    "بانک مسکن": "#بانک_مسکن", "بانک پارسیان": "#بانک_پارسیان",
    "بانک پاسارگاد": "#بانک_پاسارگاد", "موسسه اعتباری": "#موسسه_اعتباری",
    "فینتک": "#فینتک", "پرداخت الکترونیک": "#پرداخت_الکترونیک",
    "درگاه پرداخت": "#درگاه_پرداخت", "رمزارز": "#رمزارز",
    "ارز دیجیتال": "#ارز_دیجیتال", "بیت کوین": "#بیت_کوین",
    "بلاکچین": "#بلاکچین", "نئوبانک": "#نئوبانک", "شاپرک": "#شاپرک",
    "بورس": "#بورس", "فرابورس": "#فرابورس", "سهام": "#سهام",
    "شاخص کل": "#شاخص_کل", "عرضه اولیه": "#عرضه_اولیه",
    "صندوق سرمایه": "#صندوق_سرمایه_گذاری", "اوراق بهادار": "#اوراق_بهادار",
    "صکوک": "#صکوک", "بورس کالا": "#بورس_کالا", "کدال": "#کدال",
    "بیمه عمر": "#بیمه_عمر", "بیمه درمان": "#بیمه_درمان",
    "بیمه شخص ثالث": "#بیمه_شخص_ثالث", "بیمه مرکزی": "#بیمه_مرکزی",
    "حق بیمه": "#حق_بیمه", "لندتک": "#لندتک", "اعتبارسنجی": "#اعتبارسنجی",
    "تامین مالی جمعی": "#کراودفاندینگ", "تورم": "#تورم",
    "نرخ ارز": "#نرخ_ارز", "دلار": "#دلار", "نقدینگی": "#نقدینگی",
    "بودجه": "#بودجه", "مالیات": "#مالیات", "صادرات": "#صادرات",
    "واردات": "#واردات", "رشد اقتصادی": "#رشد_اقتصادی",
    "سهام عدالت": "#سهام_عدالت", "خصوصی سازی": "#خصوصی_سازی",
}

CATEGORY_KEYWORDS = {
    "bank":      ["بانک","بانکی","بانکداری","بانک مرکزی","سپرده","نرخ سود","سود بانکی","بهره","چک","موسسه اعتباری"],
    "fintech":   ["فینتک","پرداخت الکترونیک","درگاه پرداخت","رمزارز","ارز دیجیتال","بیت کوین","بلاکچین","نئوبانک","شاپرک"],
    "bourse":    ["بورس","فرابورس","سهام","شاخص کل","عرضه اولیه","اوراق بهادار","صکوک","کدال","کارگزاری"],
    "insurance": ["بیمه","بیمه عمر","بیمه درمان","بیمه شخص ثالث","حق بیمه","بیمه مرکزی"],
    "lending":   ["وام","تسهیلات","وام مسکن","وام خودرو","وام ازدواج","قرض الحسنه","لندتک","اعتبارسنجی"],
    "business":  ["مالیات","صادرات","واردات","بودجه","تورم","نرخ ارز","دلار","نقدینگی","رشد اقتصادی","سهام عدالت"],
}

FINANCE_KEYWORDS = list({kw for kws in CATEGORY_KEYWORDS.values() for kw in kws})
EXCLUDE_KEYWORDS = [
    "جنگ","حمله","موشک","پهپاد","سپاه","ارتش","نظامی",
    "انتخابات","کاندیدا","استیضاح","دادگاه","زندان","اعدام","بازداشت",
    "فوتبال","ورزش","سینما","فیلم","موسیقی","مدرسه","کنکور",
    "زلزله","سیل","واکسن","بیمارستان",
]
STRONG_FINANCE = [
    "بانک","وام","تسهیلات","بورس","سهام","ارز","مالیات",
    "بیمه","سرمایه","پرداخت","اوراق","صندوق","نرخ سود","فینتک",
]

# ذخیره خبرهای ارسال شده: story_key → {msg_ids, sources, title, text}
published_stories: dict = {}
sent_hashes: set = set()


def story_key(title: str) -> str:
    """کلید یکتا برای تشخیص خبر تکراری"""
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود","می","شد","شده","کرد","کرده","خود","برای","های","هر","آن","یک","هم"}
    words = [w for w in title.split() if w not in stop]
    return " ".join(sorted(words[:6]))


def stories_similar(t1: str, t2: str) -> bool:
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود","می","شد","شده","کرد","کرده","خود","برای","های","هر","آن"}
    w1 = set(t1.split()) - stop
    w2 = set(t2.split()) - stop
    if len(w1) < 2 or len(w2) < 2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= 0.55


def find_existing_story(title: str) -> str | None:
    """پیدا کردن خبر مشابه قبلاً منتشر شده"""
    for key, story in published_stories.items():
        if stories_similar(title, story["title"]):
            return key
    return None


def load_sources():
    try:
        with open("sources.json", encoding="utf-8") as f:
            all_s = json.load(f)
        active    = [s for s in all_s if s.get("active", True)]
        websites  = [s for s in active if s.get("type") != "telegram"]
        telegrams = [s for s in active if s.get("type") == "telegram"]
        logger.info(f"{len(websites)} سایت + {len(telegrams)} کانال")
        return websites, telegrams
    except Exception as e:
        logger.error(f"خطا: {e}")
        return [], []


def is_fresh(pub_date: datetime) -> bool:
    return (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600 <= MAX_AGE_HOURS


def is_valid_title(title: str) -> bool:
    if not title or len(title) < 15 or len(title.split()) < 4:
        return False
    junk = ["صفحه اصلی","ورود","ثبت نام","تماس","درباره","آرشیو","بیشتر بخوانید","ادامه مطلب"]
    return not any(w in title for w in junk)


def extract_hashtags(title: str, body: str = "") -> str:
    text = title + " " + body
    tags, seen = [], set()
    for phrase, tag in HASHTAG_MAP.items():
        if phrase in text and tag not in seen:
            tags.append(tag)
            seen.add(tag)
        if len(tags) >= 5:
            break
    return " ".join(tags)


def detect_categories(title: str, body: str = "") -> list:
    text = title + " " + body
    matched = sorted(
        [(c, sum(1 for k in kws if k in text)) for c, kws in CATEGORY_KEYWORDS.items()],
        key=lambda x: x[1], reverse=True
    )
    return [c for c, s in matched if s > 0][:2]


def score_news(title: str, summary: str = ""):
    text = title + " " + summary
    hits = sum(1 for k in FINANCE_KEYWORDS if k in text)
    if hits == 0:
        return False, 0
    if any(k in text for k in EXCLUDE_KEYWORDS) and not any(k in text for k in STRONG_FINANCE):
        return False, 0
    return True, hits + sum(2 for k in FINANCE_KEYWORDS if k in title)


def ai_format(title: str, body: str) -> tuple:
    """تیتر ۵ کلمه + خلاصه ۳ جمله"""
    if not ANTHROPIC_KEY:
        words = title.split()
        return " ".join(words[:5]) + ("..." if len(words) > 5 else ""), ""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 250,
                  "messages": [{"role": "user", "content":
                      f"برای این خبر دقیقاً این دو خروجی را بنویس:\n\n"
                      f"TITLE: یک تیتر فارسی حداکثر ۵ کلمه. موضوع، فاعل و نتیجه باید مشخص باشد.\n"
                      f"SUMMARY: خلاصه خبر در ۲ تا ۳ جمله کوتاه فارسی. کاربر باید بفهمد چه اتفاقی افتاده و چه تاثیری دارد.\n\n"
                      f"مثال خوب:\n"
                      f"TITLE: بانک مرکزی نرخ سود افزایش داد\n"
                      f"SUMMARY: بانک مرکزی نرخ سود سپرده‌های کوتاه‌مدت را ۲ درصد افزایش داد. این تصمیم از اول ماه آینده اجرا می‌شود. بانک‌ها موظف به اجرای این دستورالعمل هستند.\n\n"
                      f"عنوان: {title}\nمتن: {body[:600]}\n\n"
                      f"فقط TITLE و SUMMARY را بنویس، هیچ چیز دیگری نه:"}]},
            timeout=15,
        )
        if r.status_code == 200:
            text = r.json()["content"][0]["text"].strip()
            title_out = summary_out = ""
            for line in text.split("\n"):
                if line.startswith("TITLE:"):
                    title_out = line.replace("TITLE:", "").strip()
                elif line.startswith("SUMMARY:"):
                    summary_out = line.replace("SUMMARY:", "").strip()
            if title_out:
                return title_out, summary_out
    except Exception as e:
        logger.warning(f"AI: {e}")
    words = title.split()
    return " ".join(words[:5]) + ("..." if len(words) > 5 else ""), ""


def build_msg(short_title: str, summary: str, source: str,
              tags: str, link: str, also_sources: list = None) -> str:
    msg  = f"<b>{short_title}</b>\n\n"
    if summary:
        msg += f"{summary}\n\n"
    msg += "—\n"
    msg += f"📡 {source}"
    if also_sources:
        msg += f" · {' | '.join(also_sources[:3])}"
    msg += "\n"
    if tags:
        msg += f"{tags}\n"
    msg += f"🔗 <a href='{link}'>جزئیات خبر</a>"
    return msg


def send_new(msg: str, channel: str) -> int | None:
    """ارسال پیام جدید — برمی‌گردونه message_id"""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": channel, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()["result"]["message_id"]
        logger.error(f"send {channel}: {r.text}")
    except Exception as e:
        logger.error(f"send {channel}: {e}")
    return None


def edit_msg(msg: str, channel: str, message_id: int) -> bool:
    """ادیت پیام قبلی"""
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText",
            json={"chat_id": channel, "message_id": message_id,
                  "text": msg, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.error(f"edit {channel}: {e}")
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


def fetch_source(source: dict) -> list:
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
               "Accept": "*/*", "Accept-Language": "fa-IR,fa;q=0.9",
               "Referer": "https://www.google.com/"}
    try:
        resp = requests.get(source["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        ct  = resp.headers.get("content-type", "")
        url = source["url"].lower()

        if "xml" in ct or "rss" in ct or any(x in url for x in ["rss","feed",".xml"]):
            feed = feedparser.parse(resp.content)
            acc = stale = 0
            for e in feed.entries[:30]:
                title   = (e.get("title") or "").strip()
                link    = (e.get("link") or "").strip()
                summary = e.get("summary") or ""
                if not title or not link or not is_valid_title(title):
                    continue
                pub = parse_rss_date(e) or datetime.now(timezone.utc)
                if not is_fresh(pub):
                    stale += 1
                    continue
                h = hashlib.md5((title + link).encode()).hexdigest()
                if h in sent_hashes:
                    continue
                ok, score = score_news(title, summary)
                if not ok:
                    continue
                results.append({"title": title, "link": link, "body": summary,
                    "source": source["name"], "priority": source.get("priority", 2),
                    "hash": h, "date": pub, "score": score,
                    "categories": detect_categories(title, summary)})
                acc += 1
            logger.info(f"+ {source['name']} RSS: {acc} | قدیمی: {stale}")
            return results

        soup = BeautifulSoup(resp.content, "lxml")
        base = urlparse(source["url"])
        seen, acc = set(), 0
        candidates = soup.find_all(["h2","h3","h4"]) or soup.find_all("a", href=True)
        for tag in candidates[:60]:
            a_tag = tag if tag.name == "a" else (tag.find("a", href=True) or tag.find_parent("a"))
            if not a_tag:
                continue
            title = tag.get_text(strip=True)
            href  = a_tag.get("href","")
            if not is_valid_title(title):
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
            results.append({"title": title, "link": full_url, "body": "",
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": datetime.now(timezone.utc),
                "score": score, "categories": detect_categories(title)})
            acc += 1
            if acc >= 10:
                break
        logger.info(f"+ {source['name']} WEB: {acc}")
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
        url  = source["url"].replace("t.me/", "t.me/s/")
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        acc = stale = 0
        for wrap in soup.find_all("div", class_="tgme_widget_message_wrap"):
            time_tag = wrap.find("time")
            pub = datetime.now(timezone.utc)
            if time_tag and time_tag.get("datetime"):
                try:
                    pub = datetime.fromisoformat(time_tag["datetime"].replace("Z","+00:00"))
                except:
                    pass
            if not is_fresh(pub):
                stale += 1
                continue
            div = wrap.find("div", class_="tgme_widget_message_text")
            if not div:
                continue
            text = div.get_text(strip=True)
            if not text or len(text) < 20:
                continue
            link = source["url"]
            a = wrap.find("a", class_="tgme_widget_message_date")
            if a:
                link = a.get("href", link)
            h = hashlib.md5((text[:100]+link).encode()).hexdigest()
            if h in sent_hashes:
                continue
            ok, score = score_news(text[:200])
            if not ok:
                continue
            results.append({"title": text[:200], "link": link, "body": text,
                "source": source["name"], "priority": source.get("priority",2),
                "hash": h, "date": pub, "score": score,
                "categories": detect_categories(text[:300])})
            acc += 1
            if acc >= 5:
                break
        logger.info(f"+ {source['name']} TG: {acc} | قدیمی: {stale}")
    except Exception as e:
        logger.warning(f"- {source['name']} TG: {e}")
    return results


def publish_or_update(news: dict):
    """اگر خبر مشابه قبلاً منتشر شده، ادیت کن. وگرنه جدید بفرست."""
    existing_key = find_existing_story(news["title"])
    short_title, summary = ai_format(news["title"], news["body"])
    tags = extract_hashtags(news["title"], news["body"])
    cats = news.get("categories", [])

    if existing_key and existing_key in published_stories:
        # خبر تکراری — ادیت پیام قبلی
        story = published_stories[existing_key]
        if news["source"] in story["sources"]:
            logger.info(f"تکراری کامل: {news['title'][:40]}")
            sent_hashes.add(news["hash"])
            return

        story["sources"].append(news["source"])
        also = story["sources"][1:]  # منابع بعد از اولی

        msg = build_msg(short_title, summary, story["sources"][0], tags,
                        story["link"], also)

        for channel, mid in story["msg_ids"].items():
            edit_msg(msg, channel, mid)
            time.sleep(1)

        story["title"] = news["title"]
        sent_hashes.add(news["hash"])
        logger.info(f"ادیت شد ({len(story['sources'])} منبع): {short_title}")

    else:
        # خبر جدید
        msg = build_msg(short_title, summary, news["source"], tags, news["link"])
        msg_ids = {}

        mid = send_new(msg, CHANNELS["general"])
        if mid:
            msg_ids["general"] = mid
            sent_hashes.add(news["hash"])
            time.sleep(1.5)

        for cat in cats:
            if cat in CHANNELS:
                mid = send_new(msg, CHANNELS[cat])
                if mid:
                    msg_ids[cat] = mid
                time.sleep(1.5)

        if msg_ids:
            key = story_key(news["title"])
            published_stories[key] = {
                "title":   news["title"],
                "link":    news["link"],
                "sources": [news["source"]],
                "msg_ids": msg_ids,
                "time":    datetime.now(timezone.utc),
            }
            logger.info(f"جدید: {short_title}")

    # پاک کردن خبرهای قدیمی‌تر از ۲۴ ساعت از حافظه
    now = datetime.now(timezone.utc)
    old_keys = [k for k, v in published_stories.items()
                if (now - v["time"]).total_seconds() > 86400]
    for k in old_keys:
        del published_stories[k]


def run():
    websites, telegrams = load_sources()
    logger.info("=== شروع چرخه ===")
    all_news = []
    for src in websites:
        all_news.extend(fetch_source(src))
        time.sleep(1)
    for src in telegrams:
        all_news.extend(fetch_telegram_channel(src))
        time.sleep(1)
    logger.info(f"بعد از فیلتر: {len(all_news)}")

    # گروه‌بندی اخبار مشابه — بهترین رو اول بفرست
    groups = []
    for n in all_news:
        placed = False
        for g in groups:
            if stories_similar(n["title"], g[0]["title"]):
                g.append(n)
                placed = True
                break
        if not placed:
            groups.append([n])

    # مرتب بر اساس امتیاز
    groups.sort(key=lambda g: max(x["score"] for x in g), reverse=True)
    logger.info(f"گروه‌های یکتا: {len(groups)}")

    for g in groups[:15]:
        best = max(g, key=lambda x: (x["score"], x["priority"]))
        # منابع اضافه
        others = [x["source"] for x in g if x["source"] != best["source"]]
        best["also"] = others
        publish_or_update(best)

    logger.info("=== تمام ===")


def main():
    logger.info("ربات خبری v15 شروع به کار کرد")
    send_new("🚀 <b>شبکه خبری مالی ایران v15</b> فعال شد", CHANNELS["general"])
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"خطا: {e}", exc_info=True)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
