#!/usr/bin/env python3
"""
新闻聚合抓取脚本
抓取科技/AI新闻 + 新闻联播，使用 DeepSeek API 总结
新增功能：严格限制仅抓取“今日”与“昨日”的新闻，不限制具体条数
"""

import os
import json
import datetime
import hashlib
import time
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime # 新增：用于解析 RSS/Atom 的标准时间

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "data")
MAX_DAYS = 2

# ============================================================
# RSS 源配置（2026年4月验证可用）
# ============================================================
RSS_SOURCES = {
    "tech": [
        {"name": "The Verge",       "url": "https://www.theverge.com/rss/index.xml",              "lang": "en"},
        {"name": "Ars Technica",    "url": "https://feeds.arstechnica.com/arstechnica/index",      "lang": "en"},
        {"name": "Hacker News",     "url": "https://hnrss.org/frontpage",                          "lang": "en"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/",               "lang": "en"},
        {"name": "少数派",          "url": "https://sspai.com/feed",                               "lang": "zh"},
        {"name": "InfoQ中文",       "url": "https://feed.infoq.com/cn/",                           "lang": "zh"},
    ],
    "ai": [
        {"name": "The Batch",        "url": "https://www.deeplearning.ai/the-batch/feed/",         "lang": "en"},
        {"name": "Hugging Face",     "url": "https://huggingface.co/blog/feed.xml",                "lang": "en"},
        {"name": "Import AI",        "url": "https://importai.substack.com/feed",                  "lang": "en"},
        {"name": "HN-AI",            "url": "https://hnrss.org/newest?q=AI+LLM&count=20",          "lang": "en"},
        {"name": "量子位",           "url": "https://www.qbitai.com/feed",                         "lang": "zh"},
        {"name": "机器之心",         "url": "https://www.jiqizhixin.com/rss",                      "lang": "zh"},
    ],
    "cctv": [
        {"name": "人民网-要闻",     "url": "http://www.people.com.cn/rss/politics.xml",            "lang": "zh"},
        {"name": "人民网-科技",     "url": "http://www.people.com.cn/rss/IT.xml",                  "lang": "zh"},
        {"name": "Global Times",    "url": "https://www.globaltimes.cn/rss/outbrain.xml",          "lang": "en"},
        {"name": "China Daily",     "url": "http://www.chinadaily.com.cn/rss/china_rss.xml",       "lang": "en"},
    ]
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Feedfetcher-Google; (+http://www.google.com/feedfetcher.html)",
]
_ua_idx = 0

def next_ua():
    global _ua_idx
    ua = USER_AGENTS[_ua_idx % len(USER_AGENTS)]
    _ua_idx += 1
    return ua

def fetch_rss(url, timeout=20):
    """抓取 RSS feed，失败自动重试一次"""
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": next_ua(),
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
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
            if attempt == 0:
                time.sleep(2)
                continue
            print(f"  ⚠ 抓取失败 {url}: {e}")
            return None
    return None

def _clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def _try_parse_xml(xml_text):
    """解析 XML，损坏时自动清理非法字符后重试"""
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml_text)
        try:
            return ET.fromstring(cleaned)
        except ET.ParseError:
            return None

def _is_recent(date_str, days=2):
    if not date_str:
        return True  # 放过无日期（避免空数据）

    try:
        dt = parsedate_to_datetime(date_str)
    except Exception:
        try:
            clean_str = date_str.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(clean_str)
        except Exception:
            return True  # 解析失败也放过

    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc)
    else:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    return dt >= cutoff
def parse_rss(xml_text, source_name, category):
    """解析 RSS/Atom，返回近期文章列表"""
    items = []
    if not xml_text:
        return items

    root = _try_parse_xml(xml_text)
    if root is None:
        print(f"  ⚠ XML 无法解析，跳过 {source_name}")
        return items

    ns = {
        "atom":    "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc":      "http://purl.org/dc/elements/1.1/",
    }

    entries = root.findall(".//atom:entry", ns) or root.findall(".//item")

    # 取消切片限制，遍历所有的条目
    for entry in entries:
        # 发布时间（最先获取，以便及时过滤跳过）
       # 发布时间
pub_date = ""

for tag in ("pubDate", "published", "atom:published", "updated", "dc:date"):
    ...

# ⭐ 在这里加
days_limit = 5 if category == "cctv" else 2

# 时间过滤
if not _is_recent(pub_date, days=days_limit):
    continue

        # 标题
        title = ""
        for tag in ("title", "atom:title"):
            el = entry.find(tag, ns) if ":" in tag else entry.find(tag)
            if el is not None and el.text:
                title = _clean_html(el.text)
                break

        # 链接
        link = ""
        link_el = entry.find("link")
        if link_el is not None:
            link = (link_el.get("href") or link_el.text or "").strip()
        if not link:
            al = entry.find("atom:link", ns)
            if al is not None:
                link = al.get("href", "").strip()

        # 摘要
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

    # 这里由于不再限制数量，如果新闻条数非常多，可能超出 AI 总结的 token 上限
    # 所以在提交给 AI 总结时，我们还是截取最具代表性的前 15 条标题即可，但不影响最终保存的列表
    titles_text = "\n".join([f"- {a['title']} ({a['source']})" for a in articles[:15]])

    if category_name == "cctv":
        prompt = f"""以下是今日国内外要闻标题，请用简洁的中文总结，提炼3-5个核心内容：

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
            "cctv": {"articles": [], "summary": "", "count": 0},
        }
    }

    cat_labels = {"tech": "科技", "ai": "AI", "cctv": "新闻联播"}

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

        # 取消原有 [:30] 的切片限制，保留所有近期新闻
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
    print(f"\n{'='*50}\n✨ 抓取完成！\n{'='*50}\n")

if __name__ == "__main__":
    main()
