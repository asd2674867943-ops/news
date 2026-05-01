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
                print(f"     ⚠ 页面时间异常，但保留: {title[:30]}")

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
