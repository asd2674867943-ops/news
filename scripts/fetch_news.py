#!/usr/bin/env python3
import os
import json
import datetime
import hashlib
import time
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "#!/usr/bin/env python3
import os
import json
import datetime
import hashlib
import time
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "data"
)

MAX_DAYS = 2

RSS_SOURCES = {
    "tech": [
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "lang": "en"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "lang": "en"},
        {"name": "Hacker News", "url": "https://hnrss.org/frontpage", "lang": "en"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "lang": "en"},
        {"name": "少数派", "url": "https://sspai.com/feed", "lang": "zh"},
        {"name": "InfoQ中文", "url": "https://feed.infoq.com/cn/", "lang": "zh"},
    ],
    "ai": [
        {"name": "The Batch", "url": "https://www.deeplearning.ai/the-batch/feed/", "lang": "en"},
        {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml", "lang": "en"},
        {"name": "Import AI", "url": "https://importai.substack.com/feed", "lang": "en"},
        {"name": "HN-AI", "url": "https://hnrss.org/newest?q=AI+LLM&count=20", "lang": "en"},
        {"name": "量子位", "url": "https://www.qbitai.com/feed", "lang": "zh"},
        {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "lang": "zh"},
    ],
    "cctv": [
        # 优化: 将 http 改为 https，防止重定向失败
        {"name": "人民网-要闻", "url": "https://www.people.com.cn/rss/politics.xml", "lang": "zh"},
        {"name": "Global Times", "url": "https://www.globaltimes.cn/rss/outbrain.xml", "lang": "en"},
    ]
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

_ua_idx = 0


def next_ua():
    global _ua_idx
    ua = USER_AGENTS[_ua_idx % len(USER_AGENTS)]
    _ua_idx += 1
    return ua


def fetch_url(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": next_ua(),
            "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  ⚠ HTTP {e.code} {url}")
        return None
    except Exception as e:
        print(f"  ⚠ 抓取失败 {url}: {e}")
        return None


def fetch_rss(url, timeout=20):
    for attempt in range(2):
        text = fetch_url(url, timeout)
        if text:
            return text
        if attempt == 0:
            time.sleep(2)
    return None


def _clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _try_parse_xml(xml_text):
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml_text)
        try:
            return ET.fromstring(cleaned)
        except ET.ParseError:
            return None


def _parse_date(date_str):
    if not date_str:
        return None

    date_str = date_str.strip()

    try:
        dt = parsedate_to_datetime(date_str)
    except Exception:
        try:
            clean_str = date_str.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(clean_str)
        except Exception:
            return None

    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc)
    else:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    return dt


def _is_recent(date_str, days=2):
    dt = _parse_date(date_str)
    if dt is None:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    return cutoff <= dt <= now


def _link_has_old_year(link, days=2):
    """
    防止 RSS 时间是新的，但链接实际是 2017、2018 这种旧文章。
    """
    if not link:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    years = re.findall(r"/(20\d{2})[-_/]", link)
    years += re.findall(r"(20\d{2})[-_/]\d{1,2}[-_/]\d{1,2}", link)

    for y in years:
        try:
            year = int(y)
            if year < cutoff.year:
                return True
        except Exception:
            pass

    return False


def _extract_page_date(html):
    if not html:
        return ""

    patterns = [
        r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})",
        r"Published:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+20\d{2})",
        # 修复: 删除了错误的 20\d{4} 正则，保留正确的 20\d{2} 正则
        r"更新时间[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日)",
    ]

    for p in patterns:
        m = re.search(p, html, re.I)
        if not m:
            continue

        text = m.group(0)

        ym = re.search(r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})", text)
        if ym:
            y, mo, d = ym.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d}T00:00:00+00:00"

        try:
            dt = parsedate_to_datetime(m.group(1))
            return dt.isoformat()
        except Exception:
            pass

    return ""


def _page_date_is_recent(link, days=2):
    """
    只给 cctv/要闻类使用。
    """
    html = fetch_url(link, timeout=15)
    page_date = _extract_page_date(html)

    # 修复: 如果没提取到网页时间，默认放宽限制返回 True，而不是直接干掉数据
    if not page_date:
        return True

    return _is_recent(page_date, days=days)


def parse_rss(xml_text, source_name, category):
    items = []

    if not xml_text:
        return items

    root = _try_parse_xml(xml_text)

    if root is None:
        print(f"  ⚠ XML 无法解析，跳过 {source_name}")
        return items

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    entries = root.findall(".//atom:entry", ns) or root.findall(".//item")
    days_limit = 5 if category == "cctv" else 2

    for entry in entries:
        pub_date = ""

        for tag in ("pubDate", "published", "atom:published", "updated", "dc:date"):
            el = entry.find(tag, ns) if ":" in tag else entry.find(tag)
            if el is not None and el.text:
                pub_date = el.text.strip()
                break

        if not _is_recent(pub_date, days=days_limit):
            continue

        title = ""

        for tag in ("title", "atom:title"):
            el = entry.find(tag, ns) if ":" in tag else entry.find(tag)
            if el is not None and el.text:
                title = _clean_html(el.text)
                break

        link = ""

        link_el = entry.find("link")
        if link_el is not None:
            link = (link_el.get("href") or link_el.text or "").strip()

        if not link:
            al = entry.find("atom:link", ns)
            if al is not None:
                link = al.get("href", "").strip()

        if _link_has_old_year(link, days=days_limit):
            print(f"     跳过旧链接: {title[:30]} {link}")
            continue

        if category == "cctv" and link:
            if not _page_date_is_recent(link, days=days_limit):
                print(f"     跳过页面日期不合格: {title[:30]}")
                continue

        desc = ""

        for tag in ("description", "summary", "atom:summary", "content:encoded", "atom:content"):
            el = entry.find(tag, ns) if ":" in tag else entry.find(tag)
            if el is not None and el.text:
                desc = _clean_html(el.text)[:600]
                break

        if title and len(title) > 3:
            items.append({
                "id": hashlib.md5(f"{title}{link}".encode()).hexdigest()[:12],
                "title": title,
                "link": link,
                "description": desc,
                "source": source_name,
                "category": category,
                "pub_date": pub_date,
            })

        time.sleep(0.5)

    return items


def call_deepseek(prompt, max_tokens=1500):
    if not DEEPSEEK_API_KEY:
        return "（未配置 DeepSeek API Key，跳过 AI 总结）"

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠ DeepSeek API 错误: {e}")
        return "（AI 总结暂时不可用）"


def summarize_news(articles, category_name):
    # 修复: 当无相关新闻时返回空字符串，避免前端渲染空红框
    if not articles:
        return ""

    titles_text = "\n".join([
        f"- {a['title']} ({a['source']})"
        for a in articles[:15]
    ])

    if category_name == "新闻联播":
        prompt = f"""以下是最近国内外要闻标题，请用简洁的中文总结，提炼3-5个核心内容：

{titles_text}

格式：
📺 今日要闻要点

1. [要点一]
2. [要点二]
3. [要点三]

最后一句话总结今日重点。"""
    else:
        prompt = f"""以下是今日{category_name}领域新闻标题，请用中文总结，提炼3-5个重要趋势或事件：

{titles_text}

格式：
🔬 今日{category_name}动态摘要

1. [重点]
2. [重点]
3. [重点]

最后一句话总结今日最值得关注的发展。"""

    print(f"  → 调用 DeepSeek 总结 {category_name}...")
    return call_deepseek(prompt)


def clean_old_data():
    if not os.path.exists(DATA_DIR):
        return

    cutoff = datetime.date.today() - datetime.timedelta(days=MAX_DAYS)

    for fname in os.listdir(DATA_DIR):
        if fname.startswith("news_") and fname.endswith(".json"):
            try:
                file_date = datetime.date.fromisoformat(fname[5:15])
                if file_date < cutoff:
                    os.remove(os.path.join(DATA_DIR, fname))
                    print(f"  🗑 清理旧数据: {fname}")
            except Exception:
                pass


def get_date_list():
    dates = []

    if not os.path.exists(DATA_DIR):
        return dates

    for fname in sorted(os.listdir(DATA_DIR), reverse=True):
        if fname.startswith("news_") and fname.endswith(".json"):
            try:
                datetime.date.fromisoformat(fname[5:15])
                dates.append(fname[5:15])
            except Exception:
                pass

    return dates[:MAX_DAYS]


def main():
    today = datetime.date.today().isoformat()

    print(f"\n{'=' * 50}")
    print(f"📰 新闻聚合开始 - {today}")
    print(f"{'=' * 50}")

    os.makedirs(DATA_DIR, exist_ok=True)

    result = {
        "date": today,
        "generated_at": datetime.datetime.now().isoformat(),
        "categories": {
            "tech": {"articles": [], "summary": "", "count": 0},
            "ai": {"articles": [], "summary": "", "count": 0},
            "cctv": {"articles": [], "summary": "", "count": 0},
        }
    }

    cat_labels = {
        "tech": "科技",
        "ai": "AI",
        "cctv": "新闻联播"
    }

    for cat, sources in RSS_SOURCES.items():
        print(f"\n📡 抓取 {cat_labels[cat]} 新闻...")
        all_articles = []

        for src in sources:
            print(f"  → {src['name']}: {src['url'][:70]}...")
            xml = fetch_rss(src["url"])
            arts = parse_rss(xml, src["name"], cat)
            print(f"     获取近期新闻 {len(arts)} 条")
            all_articles.extend(arts)
            time.sleep(1)

        seen = set()
        unique = []

        for a in all_articles:
            if a["id"] not in seen:
                seen.add(a["id"])
                unique.append(a)

        result["categories"][cat]["articles"] = unique
        result["categories"][cat]["count"] = len(unique)

        print(f"  📝 总结 {cat_labels[cat]} 新闻（共{len(unique)}条）...")
        result["categories"][cat]["summary"] = summarize_news(unique, cat_labels[cat])

    out_path = os.path.join(DATA_DIR, f"news_{today}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 今日数据已保存: {out_path}")

    clean_old_data()

    dates = get_date_list()

    index = {
        "latest": today,
        "dates": dates,
        "updated_at": datetime.datetime.now().isoformat(),
    }

    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"📋 索引更新完成，共 {len(dates)} 天数据")
    print(f"\n{'=' * 50}\n✨ 抓取完成！\n{'=' * 50}\n")


if __name__ == "__main__":
    main()")

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "data"
)

MAX_DAYS = 2

RSS_SOURCES = {
    "tech": [
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "lang": "en"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "lang": "en"},
        {"name": "Hacker News", "url": "https://hnrss.org/frontpage", "lang": "en"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "lang": "en"},
        {"name": "少数派", "url": "https://sspai.com/feed", "lang": "zh"},
        {"name": "InfoQ中文", "url": "https://feed.infoq.com/cn/", "lang": "zh"},
    ],
    "ai": [
        {"name": "The Batch", "url": "https://www.deeplearning.ai/the-batch/feed/", "lang": "en"},
        {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml", "lang": "en"},
        {"name": "Import AI", "url": "https://importai.substack.com/feed", "lang": "en"},
        {"name": "HN-AI", "url": "https://hnrss.org/newest?q=AI+LLM&count=20", "lang": "en"},
        {"name": "量子位", "url": "https://www.qbitai.com/feed", "lang": "zh"},
        {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "lang": "zh"},
    ],
    "cctv": [
        {"name": "人民网-要闻", "url": "http://www.people.com.cn/rss/politics.xml", "lang": "zh"},
        {"name": "Global Times", "url": "https://www.globaltimes.cn/rss/outbrain.xml", "lang": "en"},
    ]
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

_ua_idx = 0


def next_ua():
    global _ua_idx
    ua = USER_AGENTS[_ua_idx % len(USER_AGENTS)]
    _ua_idx += 1
    return ua


def fetch_url(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": next_ua(),
            "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  ⚠ HTTP {e.code} {url}")
        return None
    except Exception as e:
        print(f"  ⚠ 抓取失败 {url}: {e}")
        return None


def fetch_rss(url, timeout=20):
    for attempt in range(2):
        text = fetch_url(url, timeout)
        if text:
            return text
        if attempt == 0:
            time.sleep(2)
    return None


def _clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _try_parse_xml(xml_text):
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml_text)
        try:
            return ET.fromstring(cleaned)
        except ET.ParseError:
            return None


def _parse_date(date_str):
    if not date_str:
        return None

    date_str = date_str.strip()

    try:
        dt = parsedate_to_datetime(date_str)
    except Exception:
        try:
            clean_str = date_str.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(clean_str)
        except Exception:
            return None

    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc)
    else:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    return dt


def _is_recent(date_str, days=2):
    dt = _parse_date(date_str)
    if dt is None:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    return cutoff <= dt <= now


def _link_has_old_year(link, days=2):
    """
    防止 RSS 时间是新的，但链接实际是 2017、2018 这种旧文章。
    """
    if not link:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    years = re.findall(r"/(20\d{2})[-_/]", link)
    years += re.findall(r"(20\d{2})[-_/]\d{1,2}[-_/]\d{1,2}", link)

    for y in years:
        try:
            year = int(y)
            if year < cutoff.year:
                return True
        except Exception:
            pass

    return False


def _extract_page_date(html):
    if not html:
        return ""

    patterns = [
        r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})",
        r"Published:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+20\d{2})",
        r"更新时间[:：]\s*(20\d{4}年\d{1,2}月\d{1,2}日)",
        r"更新时间[:：]\s*(20\d{2}年\d{1,2}月\d{1,2}日)",
    ]

    for p in patterns:
        m = re.search(p, html, re.I)
        if not m:
            continue

        text = m.group(0)

        ym = re.search(r"(20\d{2})[-年/](\d{1,2})[-月/](\d{1,2})", text)
        if ym:
            y, mo, d = ym.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d}T00:00:00+00:00"

        try:
            dt = parsedate_to_datetime(m.group(1))
            return dt.isoformat()
        except Exception:
            pass

    return ""


def _page_date_is_recent(link, days=2):
    """
    只给 cctv/要闻类使用。
    如果页面能提取到日期，就严格验证。
    如果提取不到日期，不保留，防止旧文章混入。
    """
    html = fetch_url(link, timeout=15)
    page_date = _extract_page_date(html)

    if not page_date:
        return False

    return _is_recent(page_date, days=days)


def parse_rss(xml_text, source_name, category):
    items = []

    if not xml_text:
        return items

    root = _try_parse_xml(xml_text)

    if root is None:
        print(f"  ⚠ XML 无法解析，跳过 {source_name}")
        return items

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    entries = root.findall(".//atom:entry", ns) or root.findall(".//item")
    days_limit = 5 if category == "cctv" else 2

    for entry in entries:
        pub_date = ""

        for tag in ("pubDate", "published", "atom:published", "updated", "dc:date"):
            el = entry.find(tag, ns) if ":" in tag else entry.find(tag)
            if el is not None and el.text:
                pub_date = el.text.strip()
                break

        if not _is_recent(pub_date, days=days_limit):
            continue

        title = ""

        for tag in ("title", "atom:title"):
            el = entry.find(tag, ns) if ":" in tag else entry.find(tag)
            if el is not None and el.text:
                title = _clean_html(el.text)
                break

        link = ""

        link_el = entry.find("link")
        if link_el is not None:
            link = (link_el.get("href") or link_el.text or "").strip()

        if not link:
            al = entry.find("atom:link", ns)
            if al is not None:
                link = al.get("href", "").strip()

        if _link_has_old_year(link, days=days_limit):
            print(f"     跳过旧链接: {title[:30]} {link}")
            continue

        if category == "cctv" and link:
            if not _page_date_is_recent(link, days=days_limit):
                print(f"     跳过页面日期不合格: {title[:30]}")
                continue

        desc = ""

        for tag in ("description", "summary", "atom:summary", "content:encoded", "atom:content"):
            el = entry.find(tag, ns) if ":" in tag else entry.find(tag)
            if el is not None and el.text:
                desc = _clean_html(el.text)[:600]
                break

        if title and len(title) > 3:
            items.append({
                "id": hashlib.md5(f"{title}{link}".encode()).hexdigest()[:12],
                "title": title,
                "link": link,
                "description": desc,
                "source": source_name,
                "category": category,
                "pub_date": pub_date,
            })

        time.sleep(0.5)

    return items


def call_deepseek(prompt, max_tokens=1500):
    if not DEEPSEEK_API_KEY:
        return "（未配置 DeepSeek API Key，跳过 AI 总结）"

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠ DeepSeek API 错误: {e}")
        return "（AI 总结暂时不可用）"


def summarize_news(articles, category_name):
    if not articles:
        return "今日暂无相关新闻。"

    titles_text = "\n".join([
        f"- {a['title']} ({a['source']})"
        for a in articles[:15]
    ])

    if category_name == "新闻联播":
        prompt = f"""以下是最近国内外要闻标题，请用简洁的中文总结，提炼3-5个核心内容：

{titles_text}

格式：
📺 今日要闻要点

1. [要点一]
2. [要点二]
3. [要点三]

最后一句话总结今日重点。"""
    else:
        prompt = f"""以下是今日{category_name}领域新闻标题，请用中文总结，提炼3-5个重要趋势或事件：

{titles_text}

格式：
🔬 今日{category_name}动态摘要

1. [重点]
2. [重点]
3. [重点]

最后一句话总结今日最值得关注的发展。"""

    print(f"  → 调用 DeepSeek 总结 {category_name}...")
    return call_deepseek(prompt)


def clean_old_data():
    if not os.path.exists(DATA_DIR):
        return

    cutoff = datetime.date.today() - datetime.timedelta(days=MAX_DAYS)

    for fname in os.listdir(DATA_DIR):
        if fname.startswith("news_") and fname.endswith(".json"):
            try:
                file_date = datetime.date.fromisoformat(fname[5:15])
                if file_date < cutoff:
                    os.remove(os.path.join(DATA_DIR, fname))
                    print(f"  🗑 清理旧数据: {fname}")
            except Exception:
                pass


def get_date_list():
    dates = []

    if not os.path.exists(DATA_DIR):
        return dates

    for fname in sorted(os.listdir(DATA_DIR), reverse=True):
        if fname.startswith("news_") and fname.endswith(".json"):
            try:
                datetime.date.fromisoformat(fname[5:15])
                dates.append(fname[5:15])
            except Exception:
                pass

    return dates[:MAX_DAYS]


def main():
    today = datetime.date.today().isoformat()

    print(f"\n{'=' * 50}")
    print(f"📰 新闻聚合开始 - {today}")
    print(f"{'=' * 50}")

    os.makedirs(DATA_DIR, exist_ok=True)

    result = {
        "date": today,
        "generated_at": datetime.datetime.now().isoformat(),
        "categories": {
            "tech": {"articles": [], "summary": "", "count": 0},
            "ai": {"articles": [], "summary": "", "count": 0},
            "cctv": {"articles": [], "summary": "", "count": 0},
        }
    }

    cat_labels = {
        "tech": "科技",
        "ai": "AI",
        "cctv": "新闻联播"
    }

    for cat, sources in RSS_SOURCES.items():
        print(f"\n📡 抓取 {cat_labels[cat]} 新闻...")
        all_articles = []

        for src in sources:
            print(f"  → {src['name']}: {src['url'][:70]}...")
            xml = fetch_rss(src["url"])
            arts = parse_rss(xml, src["name"], cat)
            print(f"     获取近期新闻 {len(arts)} 条")
            all_articles.extend(arts)
            time.sleep(1)

        seen = set()
        unique = []

        for a in all_articles:
            if a["id"] not in seen:
                seen.add(a["id"])
                unique.append(a)

        result["categories"][cat]["articles"] = unique
        result["categories"][cat]["count"] = len(unique)

        print(f"  📝 总结 {cat_labels[cat]} 新闻（共{len(unique)}条）...")
        result["categories"][cat]["summary"] = summarize_news(unique, cat_labels[cat])

    out_path = os.path.join(DATA_DIR, f"news_{today}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 今日数据已保存: {out_path}")

    clean_old_data()

    dates = get_date_list()

    index = {
        "latest": today,
        "dates": dates,
        "updated_at": datetime.datetime.now().isoformat(),
    }

    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"📋 索引更新完成，共 {len(dates)} 天数据")
    print(f"\n{'=' * 50}\n✨ 抓取完成！\n{'=' * 50}\n")


if __name__ == "__main__":
    main()
