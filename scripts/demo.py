#!/usr/bin/env python3
"""
A股微博热搜分析 Demo
- 微博热搜抓取
- A股行情数据
- 热门讨论股票分析
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

# ============================================================
# 1. 微博热搜抓取
# ============================================================
def fetch_weibo_hot():
    """获取微博实时热搜"""
    url = "https://weibo.com/ajax/side/hotSearch"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://weibo.com"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            
        hot_list = data.get("data", {}).get("realtime", [])
        results = []
        for item in hot_list[:50]:  # 取前50
            results.append({
                "rank": item.get("rank", 0),
                "keyword": item.get("word", ""),
                "hot": item.get("num", 0),
                "category": item.get("category", ""),
                "label": item.get("label_name", ""),
            })
        return results
    except Exception as e:
        print(f"⚠️  微博热搜获取失败: {e}", file=sys.stderr)
        return []


def filter_stock_keywords(hot_list):
    """筛选A股相关关键词"""
    stock_keywords = [
        "A股", "大A", "股市", "股票", "涨停", "跌停", "牛市", "熊市",
        "基金", "证券", "券商", "上证", "深证", "创业板", "科创板",
        "涨停板", "跌停板", "打板", "龙头", "妖股", "板块",
        "利好", "利空", "暴跌", "暴涨", "反弹", "回调",
        "北向资金", "主力", "游资", "散户",
    ]
    
    # 额外：提取可能的个股名称（2-4个汉字）
    stock_related = []
    for item in hot_list:
        keyword = item["keyword"]
        # 精确匹配
        for kw in stock_keywords:
            if kw in keyword:
                item["match_reason"] = f"包含「{kw}」"
                stock_related.append(item)
                break
        else:
            # 模糊匹配：包含"股"/"涨"/"跌"/"板"
            if any(w in keyword for w in ["股", "涨", "跌", "板", "牛市", "熊市", "基金"]):
                item["match_reason"] = "模糊匹配"
                stock_related.append(item)
    
    return stock_related


# ============================================================
# 2. A股行情数据 (AKShare)
# ============================================================
def fetch_market_overview():
    """获取大盘指数"""
    try:
        import akshare as ak
        
        # 上证指数
        sh = ak.stock_zh_index_daily(symbol="sh000001")
        sz = ak.stock_zh_index_daily(symbol="sz399001")
        cy = ak.stock_zh_index_daily(symbol="sz399006")
        
        def get_latest(df, name):
            last = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(last["close"])
            prev_close = float(prev["close"])
            change_pct = (close - prev_close) / prev_close * 100
            return {
                "name": name,
                "close": round(close, 2),
                "change_pct": round(change_pct, 2),
            }
        
        return [
            get_latest(sh, "上证指数"),
            get_latest(sz, "深证成指"),
            get_latest(cy, "创业板指"),
        ]
    except Exception as e:
        print(f"⚠️  大盘数据获取失败: {e}", file=sys.stderr)
        return []


def fetch_zt_dt():
    """获取涨停/跌停数据"""
    try:
        import akshare as ak
        
        # 涨停板
        zt_df = ak.stock_zt_pool_em(date=datetime.now().strftime("%Y%m%d"))
        zt_list = []
        if zt_df is not None and not zt_df.empty:
            for _, row in zt_df.head(10).iterrows():
                zt_list.append({
                    "code": str(row.get("代码", "")),
                    "name": str(row.get("名称", "")),
                    "change_pct": float(row.get("涨跌幅", 0)),
                    "reason": str(row.get("涨停原因", "")),
                })
        
        # 跌停板
        dt_df = ak.stock_zt_pool_dtgc_em(date=datetime.now().strftime("%Y%m%d"))
        dt_list = []
        if dt_df is not None and not dt_df.empty:
            for _, row in dt_df.head(10).iterrows():
                dt_list.append({
                    "code": str(row.get("代码", "")),
                    "name": str(row.get("名称", "")),
                    "change_pct": float(row.get("涨跌幅", 0)),
                })
        
        return {"涨停": zt_list, "跌停": dt_list}
    except Exception as e:
        print(f"⚠️  涨停/跌停数据获取失败: {e}", file=sys.stderr)
        return {"涨停": [], "跌停": []}


def fetch_hot_sectors():
    """获取热门板块"""
    try:
        import akshare as ak
        
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            sectors = []
            for _, row in df.head(10).iterrows():
                sectors.append({
                    "name": str(row.get("板块名称", "")),
                    "change_pct": float(row.get("涨跌幅", 0)),
                    "leader": str(row.get("领涨股票", "")),
                })
            return sectors
        return []
    except Exception as e:
        print(f"⚠️  板块数据获取失败: {e}", file=sys.stderr)
        return []


# ============================================================
# 3. 关联分析
# ============================================================
def analyze_correlation(hot_list, zt_dt, sectors):
    """分析热搜与行情的关联"""
    analysis = {
        "hot_stock_mentions": [],
        "potential_analysis": [],
    }
    
    # 提取热搜中提到的股票名称
    stock_names_in_hot = []
    for item in hot_list:
        keyword = item["keyword"]
        # 简单提取：如果关键词包含具体股票名（2-4字中文）
        if 2 <= len(keyword) <= 6 and not any(w in keyword for w in ["A股", "大A", "股市"]):
            stock_names_in_hot.append(keyword)
    
    analysis["hot_stock_mentions"] = stock_names_in_hot[:10]
    
    # 与涨停板交叉分析
    zt_names = [item["name"] for item in zt_dt.get("涨停", [])]
    mentioned_and_zt = [name for name in stock_names_in_hot if name in zt_names]
    
    if mentioned_and_zt:
        analysis["potential_analysis"].append(
            f"🔥 以下股票同时出现在微博热搜和涨停板: {', '.join(mentioned_and_zt)}"
        )
    
    # 板块分析
    hot_sector_keywords = [item["keyword"] for item in hot_list if "板块" in item["keyword"]]
    if hot_sector_keywords:
        analysis["potential_analysis"].append(
            f"📊 热搜板块关键词: {', '.join(hot_sector_keywords)}"
        )
    
    return analysis


# ============================================================
# 4. 报告生成
# ============================================================
def generate_report(hot_list, stock_hot, market, zt_dt, sectors, correlation):
    """生成分析报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = []
    lines.append(f"📊 A股微博热搜分析报告")
    lines.append(f"⏰ {now}")
    lines.append("=" * 50)
    
    # 大盘概览
    lines.append("")
    lines.append("📈 【大盘概览】")
    lines.append("-" * 40)
    if market:
        for m in market:
            arrow = "🔴" if m["change_pct"] < 0 else "🟢"
            lines.append(f"  {arrow} {m['name']}: {m['close']} ({m['change_pct']:+.2f}%)")
    else:
        lines.append("  数据获取中...")
    
    # 微博A股热搜
    lines.append("")
    lines.append("🔥 【微博A股热搜】")
    lines.append("-" * 40)
    if stock_hot:
        for item in stock_hot[:15]:
            hot_num = item["hot"]
            if hot_num >= 1000000:
                hot_str = f"{hot_num/10000:.0f}万"
            elif hot_num >= 10000:
                hot_str = f"{hot_num/10000:.1f}万"
            else:
                hot_str = str(hot_num)
            lines.append(f"  #{item['keyword']}#  🔥{hot_str}  ({item['match_reason']})")
    else:
        lines.append("  暂无A股相关热搜")
    
    # 涨停板
    lines.append("")
    lines.append("🟢 【涨停板 TOP10】")
    lines.append("-" * 40)
    if zt_dt.get("涨停"):
        for item in zt_dt["涨停"]:
            lines.append(f"  {item['name']}({item['code']}) +{item['change_pct']:.1f}%  {item.get('reason', '')}")
    else:
        lines.append("  数据获取中...")
    
    # 跌停板
    lines.append("")
    lines.append("🔴 【跌停板 TOP10】")
    lines.append("-" * 40)
    if zt_dt.get("跌停"):
        for item in zt_dt["跌停"]:
            lines.append(f"  {item['name']}({item['code']}) {item['change_pct']:.1f}%")
    else:
        lines.append("  无跌停或数据获取中...")
    
    # 热门板块
    lines.append("")
    lines.append("📊 【热门板块 TOP10】")
    lines.append("-" * 40)
    if sectors:
        for item in sectors:
            arrow = "🔴" if item["change_pct"] < 0 else "🟢"
            lines.append(f"  {arrow} {item['name']}: {item['change_pct']:+.2f}%  领涨: {item['leader']}")
    else:
        lines.append("  数据获取中...")
    
    # 关联分析
    lines.append("")
    lines.append("🔗 【热搜 vs 行情 关联分析】")
    lines.append("-" * 40)
    if correlation["hot_stock_mentions"]:
        lines.append(f"  💬 热搜提及个股: {', '.join(correlation['hot_stock_mentions'][:5])}")
    if correlation["potential_analysis"]:
        for note in correlation["potential_analysis"]:
            lines.append(f"  {note}")
    if not correlation["potential_analysis"] and not correlation["hot_stock_mentions"]:
        lines.append("  暂无明显关联")
    
    lines.append("")
    lines.append("=" * 50)
    lines.append("📌 数据来源: 微博热搜 + AKShare (东方财富)")
    lines.append("⚠️ 仅供参考，不构成投资建议")
    
    return "\n".join(lines)


# ============================================================
# Main
# ============================================================
def main():
    json_mode = "--json" in sys.argv
    
    print("🔍 正在抓取数据...\n", file=sys.stderr)
    
    # 1. 微博热搜
    print("  📱 微博热搜...", file=sys.stderr)
    hot_list = fetch_weibo_hot()
    stock_hot = filter_stock_keywords(hot_list)
    
    # 2. 大盘指数
    print("  📈 大盘指数...", file=sys.stderr)
    market = fetch_market_overview()
    
    # 3. 涨停/跌停
    print("  🟢 涨停/跌停...", file=sys.stderr)
    zt_dt = fetch_zt_dt()
    
    # 4. 热门板块
    print("  📊 热门板块...", file=sys.stderr)
    sectors = fetch_hot_sectors()
    
    # 5. 关联分析
    print("  🔗 关联分析...", file=sys.stderr)
    correlation = analyze_correlation(stock_hot, zt_dt, sectors)
    
    # 6. 输出
    if json_mode:
        result = {
            "timestamp": datetime.now().isoformat(),
            "weibo_hot_total": len(hot_list),
            "stock_hot": stock_hot,
            "market": market,
            "zt_dt": zt_dt,
            "sectors": sectors,
            "correlation": correlation,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = generate_report(hot_list, stock_hot, market, zt_dt, sectors, correlation)
        print(report)


if __name__ == "__main__":
    main()
