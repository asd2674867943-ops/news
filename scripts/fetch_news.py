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

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "docs", "data")

MAX_DAYS = 2

RSS_SOURCES = {
    "tech": [
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/"},
        {"name": "少数派", "url": "https://sspai.com/feed"},
        {"name": "InfoQ中文", "url": "https://feed.infoq.com/cn/"},
    ],
    "ai": [
        {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml"},
        {"name": "HN-AI", "url": "https://hnrss.org/newest?q=AI+LLM&count=20"},
        {"name": "量子位", "url": "https://www.qbitai.com/feed"},
        {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss"},
    ],
    "cctv": [
        {"name": "人民网-时政", "url": "http://www.people.com.cn/rss/politics.xml"},
        {"name": "人民网-国际", "url": "http://www.people.com.cn/rss/world.xml"},
        {"name": "人民网-社会", "url": "http://www.people.com.cn/rss/society.xml"},
        {"name": "人民网-军事", "url": "http://www.people.com.cn/rss/military.xml"},
        {"name": "人民网-要闻", "url": "http://www.people.com.cn/rss/ywkx.xml"},
        {"name": "Global Times", "url": "https://www.globaltimes.cn/rss/outbrain.xml"},
    ],
}


def fetch_url(url, timeout=20):
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()

            for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
                try:
                    return raw.decode(enc)
                except Exception:
                    continue

            return raw.decode("utf-8", errors="ignore")

        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            print(f"  ⚠ 抓取失败: {url} - {e}")
            return None

    return None


def clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def try_parse_xml(xml_text):
    if not xml_text:
        return None

    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml_text)
        try:
            return ET.fromstring(cleaned)
        except ET.ParseError:
            return None


def parse_date(date_str):
    if not date_str:
        return None

    date_str = date_str.strip()

    try:
        dt = parsedate_to_datetime(date_str)
    except Exception:
        try:
            dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    return dt


def is_recent(date_str, days):
    dt = parse_date(date_str)
    if dt is None:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    return cutoff <= dt <= now


def link_has_old_year(link):
    if not link:
        return False

    current_year = datetime.datetime.now().year
    years = re.findall(r"20\d{2}", link)

    for y in years:
        year = int(y)
        if year < current_year - 1:
            return True

    return False


def get_child_text(entry, tags, ns):
    for tag in tags:
        el = entry.find(tag, ns) if ":" in tag else entry.find(tag)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def get_link(entry, ns):
    link_el = entry.find("link")
    if link_el is not None:
        link = (link_el.get("href") or link_el.text or "").strip()
        if link:
            return link

    atom_link = entry.find("atom:link", ns)
    if atom_link is not None:
        return atom_link.get("href", "").strip()

    return ""


def parse_rss(xml_text, source_name, category, relaxed=False):
    items = []

    root = try_parse_xml(xml_text)
    if root is None:
        print(f"  ⚠ XML解析失败: {source_name}")
        return items

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "dc": "http://purl.org/dc/elements/1.1/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    entries = root.findall(".//item")
    if not entries:
        entries = root.findall(".//atom:entry", ns)

    days_limit = 10 if category == "cctv" else 2

    for entry in entries:
        pub_date = get_child_text(
            entry,
            ("pubDate", "published", "atom:published", "updated", "atom:updated", "dc:date"),
            ns
        )

        if category != "cctv":
            if not is_recent(pub_date, days_limit):
                continue
        else:
            if pub_date and not is_recent(pub_date, days_limit):
                continue
            if not pub_date and not relaxed:
                continue

        title = clean_html(get_child_text(entry, ("title", "atom:title"), ns))
        link = get_link(entry, ns)

        if link_has_old_year(link):
            print(f"     跳过旧链接: {title[:30]} {link}")
            continue

        desc = clean_html(get_child_text(
            entry,
            ("description", "summary", "atom:summary", "content:encoded", "atom:content"),
            ns
        ))[:600]

        if title and len(title) > 3:
            items.append({
                "id": hashlib.md5(f"{title}{link}".encode("utf-8")).hexdigest()[:12],
                "title": title,
                "link": link,
                "description": desc,
                "source": source_name,
                "category": category,
                "pub_date": pub_date,
            })

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
        f"- {a['title']}（{a['source']}）"
        for a in articles[:15]
    ])

    prompt = f"""以下是今日{category_name}新闻标题，请用中文总结，提炼3-5个核心内容：

{titles_text}

格式：
今日{category_name}动态摘要

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


def dedupe_articles(articles):
    seen = set()
    unique = []

    for article in articles:
        key = article["id"]
        if key not in seen:
            seen.add(key)
            unique.append(article)

    return unique


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

    rss_cache = {}

    for cat, sources in RSS_SOURCES.items():
        print(f"\n📡 抓取 {cat_labels[cat]} 新闻...")
        all_articles = []

        for src in sources:
            print(f"  → {src['name']}: {src['url']}")
            xml = fetch_url(src["url"])
            rss_cache[(cat, src["name"])] = xml

            articles = parse_rss(xml, src["name"], cat, relaxed=False)
            print(f"     获取 {len(articles)} 条")
            all_articles.extend(articles)
            time.sleep(1)

        unique = dedupe_articles(all_articles)

        if cat == "cctv" and len(unique) == 0:
            print("  ⚠ 新闻联播严格模式为0，启用兜底模式...")
            fallback_articles = []

            for src in sources:
                xml = rss_cache.get((cat, src["name"]))
                articles = parse_rss(xml, src["name"], cat, relaxed=True)
                fallback_articles.extend(articles)

            unique = dedupe_articles(fallback_articles)[:20]

        result["categories"][cat]["articles"] = unique
        result["categories"][cat]["count"] = len(unique)
        result["categories"][cat]["summary"] = summarize_news(unique, cat_labels[cat])

    out_path = os.path.join(DATA_DIR, f"news_{today}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 今日数据已保存: {out_path}")

    clean_old_data()

    index = {
        "latest": today,
        "dates": get_date_list(),
        "updated_at": datetime.datetime.now().isoformat(),
    }

    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print("📋 索引更新完成")
    print(f"\n{'=' * 50}\n✨ 抓取完成！\n{'=' * 50}\n")


if __name__ == "__main__":
    main()
