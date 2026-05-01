#!/usr/bin/env python3
import os
import json
import datetime
import hashlib
import time
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "data"
)

MAX_DAYS = 2

RSS_SOURCES = {
    "tech": [
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
    ],
    "ai": [
        {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml"},
        {"name": "Import AI", "url": "https://importai.substack.com/feed"},
    ],
    "cctv": [
        {"name": "央视中国", "url": "https://news.cctv.com/rss/china.xml"},
        {"name": "央视国际", "url": "https://news.cctv.com/rss/world.xml"},
        {"name": "人民网", "url": "http://www.people.com.cn/rss/politics.xml"},
        {"name": "环球网", "url": "https://world.huanqiu.com/rss/world.xml"},
    ]
}


# ======================
# 工具函数
# ======================

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  ⚠ 抓取失败: {url}")
        return None


def _clean_html(text):
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except:
        return None


def _is_recent(date_str, days=2):
    dt = _parse_date(date_str)
    if not dt:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    return cutoff <= dt <= now


def _link_has_old_year(link):
    if not link:
        return False

    years = re.findall(r"20\d{2}", link)
    for y in years:
        if int(y) < 2023:
            return True
    return False


# ======================
# 核心解析
# ======================

def parse_rss(xml_text, source_name, category):
    items = []

    if not xml_text:
        return items

    try:
        root = ET.fromstring(xml_text)
    except:
        print(f"  ⚠ XML解析失败: {source_name}")
        return items

    entries = root.findall(".//item")

    # ⭐关键：新闻联播放宽
    days_limit = 10 if category == "cctv" else 2

    for entry in entries:
        pub_date = ""
        el = entry.find("pubDate")
        if el is not None and el.text:
            pub_date = el.text.strip()

        if not _is_recent(pub_date, days=days_limit):
            continue

        title = ""
        el = entry.find("title")
        if el is not None:
            title = _clean_html(el.text)

        link = ""
        el = entry.find("link")
        if el is not None:
            link = el.text.strip()

        # ⭐关键：过滤旧新闻
        if _link_has_old_year(link):
            continue

        desc = ""
        el = entry.find("description")
        if el is not None:
            desc = _clean_html(el.text)

        if title:
            items.append({
                "id": hashlib.md5((title + link).encode()).hexdigest()[:12],
                "title": title,
                "link": link,
                "description": desc,
                "source": source_name,
                "category": category,
                "pub_date": pub_date,
            })

    return items


# ======================
# 主流程
# ======================

def main():
    today = datetime.date.today().isoformat()

    print(f"\n📰 开始抓取新闻 {today}\n")

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

    for cat, sources in RSS_SOURCES.items():
        print(f"\n📡 {cat} ...")

        for src in sources:
            print(f"  → {src['name']}")

            xml = fetch_url(src["url"])
            items = parse_rss(xml, src["name"], cat)

            print(f"     获取 {len(items)} 条")

            result["categories"][cat].extend(items)

            time.sleep(1)

    # 去重
    for cat in result["categories"]:
        seen = set()
        new_list = []
        for a in result["categories"][cat]:
            if a["id"] not in seen:
                seen.add(a["id"])
                new_list.append(a)
        result["categories"][cat] = new_list

    # 保存
    path = os.path.join(DATA_DIR, f"news_{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成: {path}")


if __name__ == "__main__":
    main()
