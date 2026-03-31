#!/usr/bin/env python3
"""
新闻聚合抓取脚本
抓取科技/AI新闻 + 新闻联播，使用 DeepSeek API 总结
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

# RSS 源配置
RSS_SOURCES = {
    "tech": [
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "lang": "en"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "lang": "en"},
        {"name": "Wired", "url": "https://www.wired.com/feed/rss", "lang": "en"},
        {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/", "lang": "en"},
        {"name": "36氪", "url": "https://36kr.com/feed", "lang": "zh"},
        {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml", "lang": "zh"},
    ],
    "ai": [
        {"name": "AI新闻", "url": "https://www.jiqizhixin.com/rss", "lang": "zh"},
        {"name": "量子位", "url": "https://www.qbitai.com/feed", "lang": "zh"},
        {"name": "AI Weekly", "url": "https://aiweekly.co/issues.rss", "lang": "en"},
    ],
    "cctv": [
        {"name": "新华网", "url": "http://www.xinhuanet.com/politics/rss/news.xml", "lang": "zh"},
        {"name": "央视网", "url": "https://news.cctv.com/rss/china.xml", "lang": "zh"},
        {"name": "人民网", "url": "http://www.people.com.cn/rss/politics.xml", "lang": "zh"},
    ]
}

def fetch_rss(url, timeout=15):
    """抓取 RSS feed"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsAggregator/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠ 抓取失败 {url}: {e}")
        return None

def parse_rss(xml_text, source_name, category):
    """解析 RSS XML，返回文章列表"""
    items = []
    if not xml_text:
        return items
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        # 处理 Atom 格式
        entries = root.findall(".//atom:entry", ns)
        if not entries:
            entries = root.findall(".//item")
        
        for entry in entries[:8]:  # 每源最多8条
            # 标题
            title_el = entry.find("title") or entry.find("atom:title", ns)
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            
            # 链接
            link_el = entry.find("link") or entry.find("atom:link", ns)
            link = ""
            if link_el is not None:
                link = link_el.get("href", "") or (link_el.text or "")
            
            # 描述/摘要
            desc_el = (entry.find("description") or entry.find("summary") or
                      entry.find("atom:summary", ns) or entry.find("content:encoded"))
            desc = ""
            if desc_el is not None and desc_el.text:
                # 去除 HTML 标签
                desc = re.sub(r"<[^>]+>", "", desc_el.text).strip()
                desc = desc[:500]
            
            # 日期
            date_el = (entry.find("pubDate") or entry.find("published") or
                      entry.find("atom:published", ns) or entry.find("updated"))
            pub_date = date_el.text.strip() if date_el is not None and date_el.text else ""
            
            if title and len(title) > 5:
                items.append({
                    "id": hashlib.md5(f"{title}{link}".encode()).hexdigest()[:12],
                    "title": title,
                    "link": link.strip(),
                    "description": desc,
                    "source": source_name,
                    "category": category,
                    "pub_date": pub_date
                })
    except Exception as e:
        print(f"  ⚠ 解析错误 {source_name}: {e}")
    return items

def call_deepseek(prompt, max_tokens=1500):
    """调用 DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        return "（未配置 DeepSeek API Key，跳过 AI 总结）"
    
    import json as json_mod
    
    payload = json_mod.dumps({
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json_mod.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠ DeepSeek API 错误: {e}")
        return "（AI 总结暂时不可用）"

def summarize_news(articles, category_name):
    """用 DeepSeek 总结新闻"""
    if not articles:
        return "今日暂无相关新闻。"
    
    titles_text = "\n".join([f"- {a['title']} ({a['source']})" for a in articles[:15]])
    
    if category_name == "cctv":
        prompt = f"""以下是今日新闻联播相关报道标题，请用简洁的中文总结今日要闻，提炼3-5个核心内容，每条100字以内：

{titles_text}

请用以下格式输出：
📺 今日新闻联播要点

1. [要点一]
2. [要点二]
3. [要点三]
（如有更多重要内容继续列出）

最后用一句话总结今日政治/民生重点。"""
    else:
        prompt = f"""以下是今日{category_name}领域新闻标题，请用中文总结今日科技动态，提炼最重要的3-5个趋势或事件：

{titles_text}

请用以下格式输出：
🔬 今日{category_name}动态摘要

1. [重点事件/趋势]
2. [重点事件/趋势]
3. [重点事件/趋势]
（如有更多重要内容继续列出）

最后用一句话总结今日{category_name}领域最值得关注的发展。"""
    
    print(f"  → 调用 DeepSeek 总结 {category_name}...")
    return call_deepseek(prompt)

def clean_old_data():
    """清理15天前的数据文件"""
    if not os.path.exists(DATA_DIR):
        return
    cutoff = datetime.date.today() - datetime.timedelta(days=MAX_DAYS)
    for fname in os.listdir(DATA_DIR):
        if fname.startswith("news_") and fname.endswith(".json"):
            date_str = fname[5:15]  # news_YYYY-MM-DD.json
            try:
                file_date = datetime.date.fromisoformat(date_str)
                if file_date < cutoff:
                    os.remove(os.path.join(DATA_DIR, fname))
                    print(f"  🗑 清理旧数据: {fname}")
            except Exception:
                pass

def get_date_list():
    """获取现有数据文件的日期列表"""
    dates = []
    if not os.path.exists(DATA_DIR):
        return dates
    for fname in sorted(os.listdir(DATA_DIR), reverse=True):
        if fname.startswith("news_") and fname.endswith(".json"):
            date_str = fname[5:15]
            try:
                datetime.date.fromisoformat(date_str)
                dates.append(date_str)
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
            "tech": {"articles": [], "summary": ""},
            "ai": {"articles": [], "summary": ""},
            "cctv": {"articles": [], "summary": ""}
        }
    }
    
    # 抓取各类新闻
    for cat, sources in RSS_SOURCES.items():
        cat_labels = {"tech": "科技", "ai": "AI", "cctv": "新闻联播"}
        print(f"\n📡 抓取 {cat_labels[cat]} 新闻...")
        all_articles = []
        
        for src in sources:
            print(f"  → {src['name']}: {src['url'][:60]}...")
            xml = fetch_rss(src["url"])
            arts = parse_rss(xml, src["name"], cat)
            print(f"     获取 {len(arts)} 条")
            all_articles.extend(arts)
            time.sleep(0.5)
        
        # 去重（按 id）
        seen = set()
        unique = []
        for a in all_articles:
            if a["id"] not in seen:
                seen.add(a["id"])
                unique.append(a)
        
        result["categories"][cat]["articles"] = unique[:30]
        
        # AI 总结
        print(f"  📝 总结 {cat_labels[cat]} 新闻（共{len(unique)}条）...")
        result["categories"][cat]["summary"] = summarize_news(unique, cat_labels[cat])
        result["categories"][cat]["count"] = len(unique)
    
    # 保存今日数据
    out_path = os.path.join(DATA_DIR, f"news_{today}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 今日数据已保存: {out_path}")
    
    # 清理旧数据
    clean_old_data()
    
    # 更新索引文件
    dates = get_date_list()
    index = {
        "latest": today,
        "dates": dates,
        "updated_at": datetime.datetime.now().isoformat()
    }
    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"📋 索引更新完成，共 {len(dates)} 天数据")
    print(f"\n{'='*50}\n✨ 抓取完成！\n{'='*50}\n")

if __name__ == "__main__":
    main()
