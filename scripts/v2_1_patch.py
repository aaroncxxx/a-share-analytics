#!/usr/bin/env python3
"""
A股分析 v2.1 新增模块
- 东方财富股吧热帖
- 财经新闻聚合（东方财富 + 第一财经/证券时报 RSS）
- 雪球讨论（可选，需 token）
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import urllib.error
import html
import time

# ============================================================
# 1. 东方财富股吧热帖
# ============================================================

def _guba_fetch_hot_topics(code, count=10):
    """
    东方财富股吧热帖 - 通过 HTML 解析
    code: 股票代码 (如 688256)
    """
    url = f"https://guba.eastmoney.com/list,{code},f_1.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://guba.eastmoney.com/",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html_text = resp.read().decode("utf-8", errors="replace")

        posts = []
        # 匹配 <tr class="listitem"> 块
        rows = re.findall(r'<tr class="listitem">(.*?)</tr>', html_text, re.DOTALL)
        for row in rows[:count]:
            # 阅读数
            reads_m = re.search(r'<div class="read">([\d.万千]+)</div>', row)
            reads = reads_m.group(1) if reads_m else "0"
            # 评论数
            reply_m = re.search(r'<div class="reply">(\d+)</div>', row)
            comments = reply_m.group(1) if reply_m else "0"
            # 标题 + 链接
            title_m = re.search(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', row)
            if title_m:
                href = title_m.group(1)
                title = re.sub(r'<[^>]+>', '', title_m.group(2)).strip()
                title = html.unescape(title)
            else:
                continue
            # 作者
            author_m = re.search(r'class="author"><a[^>]*>(.*?)</a>', row)
            author = author_m.group(1) if author_m else ""
            # 时间
            time_m = re.search(r'class="update">(.*?)</div>', row)
            post_time = time_m.group(1) if time_m else ""

            full_url = href if href.startswith("http") else f"https://guba.eastmoney.com{href}"
            posts.append({
                "title": title,
                "url": full_url,
                "reads": reads,
                "comments": comments,
                "author": author,
                "time": post_time,
                "source": "东方财富股吧",
            })
        return posts
    except Exception as e:
        return []


def fetch_guba_for_stock(code, name="", count=10):
    """获取单只股票的股吧热帖"""
    posts = _guba_fetch_hot_topics(code, count=count)
    for p in posts:
        p["stock_code"] = code
        p["stock_name"] = name
    return posts


# ============================================================
# 2. 财经新闻聚合
# ============================================================

def fetch_eastmoney_news(count=15):
    """
    东方财富要闻 - 免费公开接口
    """
    ts = int(time.time())
    url = (
        f"https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
        f"?client=web&biz=web_home_channel&column=350&order=1"
        f"&needInteractData=0&page_index=1&page_size={count}&req_trace={ts}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.eastmoney.com/",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        news_list = data.get("data", {}).get("list", [])
        results = []
        for item in news_list[:count]:
            results.append({
                "title": item.get("title", ""),
                "summary": item.get("summary", "")[:200],
                "url": item.get("url", ""),
                "time": item.get("showTime", ""),
                "source": item.get("mediaName", "东方财富"),
                "category": "要闻",
            })
        return results
    except Exception as e:
        return []


def fetch_rss_feed(url, source_name="", count=10):
    """
    通用 RSS 源抓取
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")

        root = ET.fromstring(xml_text)
        results = []

        # RSS 2.0
        for item in root.findall(".//item")[:count]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            desc = re.sub(r'<[^>]+>', '', desc)[:200]
            if title:
                results.append({
                    "title": html.unescape(title),
                    "summary": html.unescape(desc),
                    "url": link,
                    "time": pub_date,
                    "source": source_name,
                    "category": "新闻",
                })

        # Atom fallback
        if not results:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns)[:count]:
                title = entry.findtext("atom:title", "", ns).strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                summary = entry.findtext("atom:summary", "", ns).strip()
                updated = entry.findtext("atom:updated", "", ns).strip()
                summary = re.sub(r'<[^>]+>', '', summary)[:200]
                if title:
                    results.append({
                        "title": html.unescape(title),
                        "summary": html.unescape(summary),
                        "url": link,
                        "time": updated,
                        "source": source_name,
                        "category": "新闻",
                    })
        return results
    except Exception as e:
        return []


def fetch_yicai_news(count=10):
    """第一财经 RSS"""
    return fetch_rss_feed("https://www.yicai.com/rss/", "第一财经", count)


def fetch_stcn_news(count=10):
    """证券时报 RSS"""
    return fetch_rss_feed("https://www.stcn.com/rss/", "证券时报", count)


def fetch_all_news(count=15):
    """聚合所有新闻源"""
    all_news = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(fetch_eastmoney_news, count)
        f2 = executor.submit(fetch_yicai_news, count)
        f3 = executor.submit(fetch_stcn_news, count)
        for f in [f1, f2, f3]:
            try:
                result = f.result(timeout=10)
                all_news.extend(result)
            except Exception:
                pass

    # 去重（标题前20字符）
    seen = set()
    unique = []
    for item in all_news:
        key = item["title"][:20]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:count * 2]


# ============================================================
# 3. 雪球讨论（可选，需 token）
# ============================================================

def fetch_xueqiu_discuss(symbol="SH688256", count=10, token=""):
    """雪球个股讨论（需浏览器 xq_a_token）"""
    if not token:
        return []
    url = f"https://stock.xueqiu.com/v5/stock/comment/list.json?symbol={symbol}&count={count}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Cookie": f"xq_a_token={token}",
        "Referer": "https://xueqiu.com/",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data", {}).get("items", [])
        results = []
        for item in items[:count]:
            reply = item.get("reply", {})
            results.append({
                "title": reply.get("title", ""),
                "text": re.sub(r'<[^>]+>', '', reply.get("text", ""))[:200],
                "user": reply.get("user", {}).get("screen_name", ""),
                "like_count": reply.get("like_count", 0),
                "reply_count": reply.get("reply_count", 0),
                "source": "雪球",
                "symbol": symbol,
            })
        return results
    except Exception:
        return []


# ============================================================
# 4. 综合社区+新闻数据
# ============================================================

def fetch_community_data(stock_codes=None, count_per_stock=5):
    """
    综合社区舆情数据
    stock_codes: [(code, name), ...]
    """
    results = {"guba": [], "news": []}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        if stock_codes:
            for code, name in stock_codes[:5]:
                futures[f"guba_{code}"] = executor.submit(
                    fetch_guba_for_stock, code, name, count_per_stock
                )
        futures["news"] = executor.submit(fetch_all_news, 20)
        for key, future in futures.items():
            try:
                result = future.result(timeout=15)
                if key.startswith("guba_"):
                    results["guba"].extend(result)
                else:
                    results["news"] = result
            except Exception:
                pass
    return results


# ============================================================
# 5. 文本渲染
# ============================================================

def render_guba_text(posts, title="东方财富股吧热帖"):
    if not posts:
        return ""
    lines = [f"\n🗣️  【{title}】", "-" * 40]
    for p in posts[:10]:
        lines.append(f"  📌 {p['title']}")
        meta = []
        if p.get("reads") and p["reads"] != "0":
            meta.append(f"👀{p['reads']}阅读")
        if p.get("comments") and p["comments"] != "0":
            meta.append(f"💬{p['comments']}评论")
        if p.get("time"):
            meta.append(p["time"])
        if meta:
            lines.append(f"     {' | '.join(meta)}")
    return "\n".join(lines)


def render_news_text(news, title="财经新闻"):
    if not news:
        return ""
    lines = [f"\n📰 【{title}】", "-" * 40]
    for n in news[:10]:
        source = n.get("source", "")
        time_str = n.get("time", "")
        lines.append(f"  📄 {n['title']}")
        meta = [x for x in [source, time_str] if x]
        if meta:
            lines.append(f"     {' | '.join(meta)}")
    return "\n".join(lines)


def render_community_text(data):
    """渲染综合社区数据（文本格式）"""
    lines = []
    guba = data.get("guba", [])
    if guba:
        by_stock = {}
        for p in guba:
            code = p.get("stock_code", "other")
            if code not in by_stock:
                by_stock[code] = {"name": p.get("stock_name", code), "posts": []}
            by_stock[code]["posts"].append(p)
        for code, info in by_stock.items():
            text = render_guba_text(info["posts"], f"股吧热帖 · {info['name']}({code})")
            lines.extend(text.split("\n"))
    news = data.get("news", [])
    if news:
        text = render_news_text(news)
        lines.extend(text.split("\n"))
    return "\n".join(lines)
