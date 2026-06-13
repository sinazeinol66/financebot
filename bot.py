import os, time, hashlib, logging, requests, json, re
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import feedparser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))
TEHRAN         = timezone(timedelta(hours=3, minutes=30))
MAX_AGE_HOURS  = 24

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

published_stories: dict = {}
sent_hashes: set = set()


def clean_text(text: str) -> str:
    """پاک‌سازی متن از ایموجی و کاراکترهای اضافه"""
    text = re.sub(r'[🔺🔻🔸🔹💠✅❌⚡️🎥📌📊💰🏦🔔⬇️⬆️➡️◀️▶️]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def make_title(raw_title: str) -> str:
    """
    ساخت تیتر خوانا از عنوان خام:
    - حذف ایموجی و علائم
    - اگر طولانیه، در اولین نقطه یا ؛ قطع کن
    - حداکثر ۶۰ کاراکتر
    """
    title = clean_text(raw_title)
    # قطع در نقطه‌گذاری
    for sep in ['؛', '|', '-', '–', ':', '،']:
        if sep in title:
            parts = title.split(sep)
            if len(parts[0].strip()) >= 15:
                title = parts[0].strip()
                break
    # حداکثر ۶۰ کاراکتر
    if len(title) > 65:
        words = title[:65].split()
        title = " ".join(words[:-1]) + "..."
    return title


def make_summary(title: str, body: str) -> str:
    """
    ساخت خلاصه از متن خبر:
    - اول جمله‌های مفید body رو پیدا کن
    - اگه body خالیه، از تیتر استفاده کن
    - حداکثر ۲ جمله
    """
    text = clean_text(body) if body else ""

    if len(text) < 30:
        return ""

    # پیدا کردن جملات
    sentences = re.split(r'[.!؟]\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    # فیلتر جملات تبلیغاتی
    junk = ["کلیک کن","بیشتر بخوانید","ادامه مطلب","برای اطلاعات","جهت اطلاع","منبع:","به گزارش"]
    sentences = [s for s in sentences if not any(j in s for j in junk)]

    if not sentences:
        return ""

    # ۲ جمله اول
    result = ". ".join(sentences[:2])
    if not result.endswith("."):
        result += "."

    # حداکثر ۲۰۰ کاراکتر
    if len(result) > 200:
        result = result[:197] + "..."

    return result


def fetch_article_body(url: str) -> str:
    """خواندن متن مقاله از صفحه خبر"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "fa-IR,fa;q=0.9"
        }
        resp = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(resp.content, "lxml")
        for tag in soup(["nav","footer","header","script","style","aside"]):
            tag.decompose()
        for selector in ["article", ".content", ".news-content", ".article-body",
                         ".post-content", ".text", "main p"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 80:
                    return text[:600]
        # fallback: همه پاراگراف‌ها
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
        return " ".join(paras[:3])[:600]
    except:
        return ""


def extract_hashtags(text: str) -> str:
    tags, seen = [], set()
    for phrase, tag in HASHTAG_MAP.items():
        if phrase in text and tag not in seen:
            tags.append(tag)
            seen.add(tag)
        if len(tags) >= 4:
            break
    return " ".join(tags)


def detect_categories(text: str) -> list:
    matched = sorted(
        [(c, sum(1 for k in kws if k in text)) for c, kws in CATEGORY_KEYWORDS.items()],
        key=lambda x: x[1], reverse=True
    )
    return [c for c, s in matched if s > 0][:2]


def score_news(title: str, summary: str = "") -> tuple:
    text = title + " " + summary
    hits = sum(1 for k in FINANCE_KEYWORDS if k in text)
    if hits == 0:
        return False, 0
    if any(k in text for k in EXCLUDE_KEYWORDS) and not any(k in text for k in STRONG_FINANCE):
        return False, 0
    return True, hits + sum(2 for k in FINANCE_KEYWORDS if k in title)


def story_key(title: str) -> str:
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود","می","شد","کرد","خود","برای","های","هر","آن","یک","هم"}
    words = [w for w in clean_text(title).split() if w not in stop]
    return " ".join(sorted(words[:6]))


def find_existing(title: str) -> str:
    stop = {"از","به","در","با","که","این","را","و","یا","است","بود","می","شد","کرد","خود","برای","های","هر","آن"}
    w1 = set(clean_text(title).split()) - stop
    for key, story in published_stories.items():
        w2 = set(clean_text(story["title"]).split()) - stop
        if len(w1) >= 2 and len(w2) >= 2:
            if len(w1 & w2) / min(len(w1), len(w2)) >= 0.55:
                return key
    return ""


def is_fresh(pub_date: datetime) -> bool:
    return (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600 <= MAX_AGE_HOURS


def is_valid_title(title: str) -> bool:
    t = clean_text(title)
    if len(t) < 15 or len(t.split()) < 3:
        return False
    junk = ["صفحه اصلی","ورود","ثبت نام","تماس با","درباره ما","آرشیو","بیشتر بخوانید","ادامه مطلب","دسته‌بندی","برچسب"]
    return not any(w in t for w in junk)


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


def build_msg(title: str, summary: str, sources: list, tags: str, link: str) -> str:
    main_src = sources[0] if sources else ""
    also = sources[1:3] if len(sources) > 1 else []

    msg  = f"<b>{title}</b>\n\n"
    if summary:
        msg += f"{summary}\n\n"
    msg += "—\n"
    msg += f"📡 {main_src}"
    if also:
        msg += f" · {' | '.join(also)}"
    msg += "\n"
    if tags:
        msg += f"{tags}\n"
    msg += f"🔗 <a href=\"{link}\">جزئیات خبر</a>"
    return msg


def tg_send(msg: str, channel: str) -> int:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": channel, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()["result"]["message_id"]
        logger.error(f"send {channel}: {r.text[:100]}")
    except Exception as e:
        logger.error(f"send {channel}: {e}")
    return 0


def tg_edit(msg: str, channel: str, message_id: int) -> bool:
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
        logger.error(f"edit: {e}")
        return False


def parse_rss_date(entry) -> datetime:
    for a in ("published_parsed", "updated_parsed"):
        t = getattr(entry, a, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except:
                pass
    return datetime.now(timezone.utc)


def fetch_source(source: dict) -> list:
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Accept-Language": "fa-IR,fa;q=0.9",
        "Referer": "https://www.google.com/",
    }
    try:
        resp = requests.get(source["url"], headers=headers, timeout=15)
        resp.raise_for_status()
        ct  = resp.headers.get("content-type", "")
        url = source["url"].lower()
        is_rss = "xml" in ct or "rss" in ct or any(x in url for x in ["rss","feed",".xml"])

        if is_rss:
            feed = feedparser.parse(resp.content)
            acc = stale = 0
            for e in feed.entries[:30]:
                title   = (e.get("title") or "").strip()
                link    = (e.get("link") or "").strip()
                summary = clean_text(e.get("summary") or "")
                if not title or not link or not is_valid_title(title):
                    continue
                pub = parse_rss_date(e)
                if not is_fresh(pub):
                    stale += 1
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
                    "hash": h, "date": pub, "score": score,
                    "categories": detect_categories(title + " " + summary),
                })
                acc += 1
            logger.info(f"RSS {source['name']}: {acc} | قدیمی:{stale}")
            return results

        soup = BeautifulSoup(resp.content, "lxml")
        base = urlparse(source["url"])
        seen, acc = set(), 0
        candidates = soup.find_all(["h2","h3","h4"]) or soup.find_all("a", href=True)
        for tag in candidates[:80]:
            a_tag = tag if tag.name == "a" else (tag.find("a", href=True) or tag.find_parent("a"))
            if not a_tag:
                continue
            title = tag.get_text(strip=True)
            href  = a_tag.get("href", "")
            if not is_valid_title(title):
                continue
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = f"{base.scheme}://{base.netloc}{href}"
            else:
                continue
            if full_url in seen:
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
            acc += 1
            if acc >= 10:
                break
        logger.info(f"WEB {source['name']}: {acc}")
    except requests.exceptions.ConnectionError:
        logger.warning(f"قطع: {source['name']}")
    except requests.exceptions.Timeout:
        logger.warning(f"timeout: {source['name']}")
    except Exception as e:
        logger.warning(f"خطا {source['name']}: {e}")
    return results


def fetch_telegram(source: dict) -> list:
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
            text = clean_text(div.get_text(strip=True))
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
            results.append({
                "title": text[:150], "link": link, "body": text,
                "source": source["name"], "priority": source.get("priority", 2),
                "hash": h, "date": pub, "score": score,
                "categories": detect_categories(text[:300]),
            })
            acc += 1
            if acc >= 5:
                break
        logger.info(f"TG {source['name']}: {acc} | قدیمی:{stale}")
    except Exception as e:
        logger.warning(f"TG {source['name']}: {e}")
    return results


def publish(news: dict):
    raw_title = news["title"]
    link      = news["link"]
    body      = news["body"]

    # اگر body خالیه، متن مقاله رو بگیر
    if not body.strip() and link.startswith("http"):
        body = fetch_article_body(link)

    title   = make_title(raw_title)
    summary = make_summary(raw_title, body)
    tags    = extract_hashtags(raw_title + " " + body)
    cats    = news.get("categories", [])

    existing_key = find_existing(raw_title)

    if existing_key and existing_key in published_stories:
        story = published_stories[existing_key]
        if news["source"] in story["sources"]:
            sent_hashes.add(news["hash"])
            return
        story["sources"].append(news["source"])
        msg = build_msg(title, summary, story["sources"], tags, story["link"])
        for channel, mid in story["msg_ids"].items():
            tg_edit(msg, channel, mid)
            time.sleep(1)
        sent_hashes.add(news["hash"])
        logger.info(f"ادیت ({len(story['sources'])} منبع): {title[:35]}")
    else:
        msg = build_msg(title, summary, [news["source"]], tags, link)
        msg_ids = {}
        mid = tg_send(msg, CHANNELS["general"])
        if mid:
            msg_ids["general"] = mid
            sent_hashes.add(news["hash"])
            time.sleep(1.5)
        for cat in cats:
            if cat in CHANNELS:
                mid = tg_send(msg, CHANNELS[cat])
                if mid:
                    msg_ids[cat] = mid
                time.sleep(1.5)
        if msg_ids:
            published_stories[story_key(raw_title)] = {
                "title": raw_title, "link": link,
                "sources": [news["source"]],
                "msg_ids": msg_ids,
                "time": datetime.now(timezone.utc),
            }
            logger.info(f"جدید: {title[:35]}")

    now = datetime.now(timezone.utc)
    old = [k for k, v in published_stories.items()
           if (now - v["time"]).total_seconds() > 86400]
    for k in old:
        del published_stories[k]


def run():
    websites, telegrams = load_sources()
    logger.info("=== شروع چرخه ===")
    all_news = []
    for src in websites:
        all_news.extend(fetch_source(src))
        time.sleep(1)
    for src in telegrams:
        all_news.extend(fetch_telegram(src))
        time.sleep(1)
    logger.info(f"کل: {len(all_news)}")

    stop = {"از","به","در","با","که","این","را","و","یا","است","بود","می","شد","کرد","خود","برای","های","هر","آن"}
    groups = []
    for n in all_news:
        w1 = set(clean_text(n["title"]).split()) - stop
        placed = False
        for g in groups:
            w2 = set(clean_text(g[0]["title"]).split()) - stop
            if len(w1) >= 2 and len(w2) >= 2 and len(w1&w2)/min(len(w1),len(w2)) >= 0.55:
                g.append(n)
                placed = True
                break
        if not placed:
            groups.append([n])

    groups.sort(key=lambda g: max(x["score"] for x in g), reverse=True)
    logger.info(f"یکتا: {len(groups)}")

    for g in groups[:15]:
        best = max(g, key=lambda x: (x["score"], x["priority"]))
        publish(best)

    logger.info("=== تمام ===")


def main():
    logger.info("ربات v17 شروع کرد")
    tg_send("🚀 <b>شبکه خبری مالی ایران v17</b> فعال شد", CHANNELS["general"])
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"خطا: {e}", exc_info=True)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
