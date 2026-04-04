#!/usr/bin/env python3
"""
新闻聚合抓取脚本 - 修复版
"""

import os
import json
import datetime
import hashlib
import time
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "data")
MAX_DAYS = 15

RSS_SOURCES = {
    "tech": [
        {"name": "The Verge",       "url": "https://www.theverge.com/rss/index.xml",         "lang": "en"},
        {"name": "TechCrunch",      "url": "https://techcrunch.com/feed/",                    "lang": "en"},
        {"name": "Wired",           "url": "https://www.wired.com/feed/rss",                  "lang": "en"},
        {"name": "Ars Technica",    "url": "https://feeds.arstechnica.com/arstechnica/index", "lang": "en"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/",          "lang": "en"},
        {"name": "36氪",            "url": "https://36kr.com/feed",                           "lang": "zh"},
    ],
    "ai": [
        {"name": "量子位",          "url": "https://www.qbitai.com/feed",                     "lang": "zh"},
        {"name": "机器之心",        "url": "https://www.jiqizhixin.com/rss",                  "lang": "zh"},
        {"name": "HN-AI",           "url": "https://hnrss.org/newest?q=AI+LLM&count=20",     "lang": "en"},
        {"name": "OpenAI Blog",     "url": "https://openai.com/blog/rss.xml",                 "lang": "en"},
        {"name": "Anthropic News",  "url": "https://www.anthropic.com/news/rss.xml",          "lang": "en"},
        {"name": "DeepMind Blog",   "url": "https://deepmind.google/blog/rss.xml",            "lang": "en"},
    ],
    "cctv": [
        {"name": "新华社",          "url": "https://rsshub.app/xinhua/world",                 "lang": "zh"},
        {"name": "央视新闻",        "url": "https://rsshub.app/cctv/category/china",          "lang": "zh"},
        {"name": "人民网",          "url": "https://rsshub.app/people/politics",              "lang": "zh"},
        {"name": "环球时报",        "url": "https://rsshub.app/huanqiu",                      "lang": "zh"},
    ]
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, application/atom+xml, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
}

def fetch_rss(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            encoding = resp.headers.get_content_charset() or "utf-8"
            try:
                return raw.decode(encoding, errors="replace")
            except (LookupError, UnicodeDecodeError):
                return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  ⚠ 抓取失败 {url}: HTTP {e.code} {e.reason}")
        return None
    except Exception as e:
        print(f"  ⚠ 抓取失败 {url}: {e}")
        return None

def clean_xml(text):
    if not text:
        return text
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = text.replace('&nbsp;', ' ').replace('&copy;', '©').replace('&trade;', '™')
    return text

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_rss(xml_text, source_name, category):
    items = []
    if not xml_text:
        return items

    xml_text = clean_xml(xml_text)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  ⚠ XML 解析错误 {source_name}: {e}")
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}

    entries = root.findall(".//atom:entry", ns)
    if not entries:
        entries = root.findall(".//item")

    for entry in entries[:10]:
        title_el = entry.find("title") or entry.find("atom:title", ns)
        title = strip_html(title_el.text) if title_el is not None and title_el.text else ""

        link = ""
        link_el = entry.find("link")
        if link_el is not None:
            link = link_el.get("href", "") or (link_el.text or "")
        if not link:
            atom_link = entry.find("atom:link", ns)
            if atom_link is not None:
                link = atom_link.get("href", "")

        desc = ""
        for tag in ["description", "summary", "atom:summary"]:
            el = entry.find(tag, ns) if tag.startswith("atom:") else entry.find(tag)
            if el is not None and el.text:
                desc = strip_html(el.text)[:400]
                break

        pub_date = ""
        for tag in ["pubDate", "published", "updated"]:
            el = entry.find(tag)
            if el is not None and el.text:
                pub_date = el.text.strip()
                break

        if title and len(title) > 3:
            items.append({
                "id": hashlib.md5(f"{title}{link}".encode()).hexdigest()[:12],
                "title": title,
                "link": link.strip(),
                "description": desc,
                "source": source_name,
                "category": category,
                "pub_date": pub_date
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
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
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
    titles_text = "\n".join([f"- {a['title']} ({a['source']})" for a in articles[:15]])
    if category_name == "cctv":
        prompt = f"""以下是今日国内新闻报道标题，请用简洁的中文总结今日要闻，提炼3-5个核心内容：

{titles_text}

请用以下格式输出：
📺 今日新闻要点

1. [要点一]
2. [要点二]
3. [要点三]

最后用一句话总结今日重点。"""
    else:
        prompt = f"""以下是今日{category_name}领域新闻标题，请用中文总结，提炼最重要的3-5个趋势或事件：

{titles_text}

请用以下格式输出：
🔬 今日{category_name}动态摘要

1. [重点事件/趋势]
2. [重点事件/趋势]
3. [重点事件/趋势]

最后用一句话总结今日最值得关注的发展。"""
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
    print(f"\n{'='*50}")
    print(f"📰 新闻聚合开始 - {today}")
    print(f"{'='*50}")

    os.makedirs(DATA_DIR, exist_ok=True)

    result = {
        "date": today,
        "generated_at": datetime.datetime.now().isoformat(),
        "categories": {
            "tech": {"articles": [], "summary": "", "count": 0},
            "ai":   {"articles": [], "summary": "", "count": 0},
            "cctv": {"articles": [], "summary": "", "count": 0}
        }
    }

    for cat, sources in RSS_SOURCES.items():
        cat_labels = {"tech": "科技", "ai": "AI", "cctv": "新闻联播"}
        print(f"\n📡 抓取 {cat_labels[cat]} 新闻...")
        all_articles = []

        for src in sources:
            print(f"  → {src['name']}: {src['url'][:70]}...")
            xml = fetch_rss(src["url"])
            arts = parse_rss(xml, src["name"], cat)
            print(f"     获取 {len(arts)} 条")
            all_articles.extend(arts)
            time.sleep(1)

        seen = set()
        unique = []
        for a in all_articles:
            if a["id"] not in seen:
                seen.add(a["id"])
                unique.append(a)

        result["categories"][cat]["articles"] = unique[:30]
        result["categories"][cat]["count"] = len(unique)

        print(f"  📝 总结 {cat_labels[cat]} 新闻（共{len(unique)}条）...")
        result["categories"][cat]["summary"] = summarize_news(unique, cat_labels[cat])

    out_path = os.path.join(DATA_DIR, f"news_{today}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 今日数据已保存: {out_path}")

    clean_old_data()

    dates = get_date_list()
    index = {"latest": today, "dates": dates, "updated_at": datetime.datetime.now().isoformat()}
    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"📋 索引更新完成，共 {len(dates)} 天数据")
    print(f"\n{'='*50}\n✨ 抓取完成！\n{'='*50}\n")

if __name__ == "__main__":
    main()
