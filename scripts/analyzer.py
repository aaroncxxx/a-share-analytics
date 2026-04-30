#!/usr/bin/env python3
"""
A股微博热搜分析 v1.1
- 微博热搜抓取 + A股关键词筛选（增强版）
- A股行情数据（大盘/涨停/跌停/板块）
- 北向资金数据
- 热搜 vs 行情关联分析
- 历史趋势对比 (--trend)
- 本地快照缓存
"""

import json
import sys
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, ".cache")

# ============================================================
# 参数解析
# ============================================================
JSON_MODE = "--json" in sys.argv
BRIEF_MODE = "--brief" in sys.argv
NO_WEIBO = "--no-weibo" in sys.argv
NO_MARKET = "--no-market" in sys.argv
TREND_MODE = "--trend" in sys.argv

# ============================================================
# 1. 微博热搜抓取
# ============================================================
def fetch_weibo_hot(retries=2):
    """获取微博实时热搜（带重试）"""
    url = "https://weibo.com/ajax/side/hotSearch"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://weibo.com",
        "X-Requested-With": "XMLHttpRequest",
    }
    
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
            hot_list = data.get("data", {}).get("realtime", [])
            results = []
            for item in hot_list[:50]:
                results.append({
                    "rank": item.get("rank", 0),
                    "keyword": item.get("word", ""),
                    "hot": item.get("num", 0),
                    "category": item.get("category", ""),
                    "label": item.get("label_name", ""),
                    "icon_desc": item.get("icon_desc", ""),
                })
            return results
        except Exception as e:
            if attempt < retries:
                import time
                time.sleep(1)
                continue
            log(f"⚠️  微博热搜获取失败: {e}")
            return []


# 行业/板块关键词库（v1.1 增强）
SECTOR_KEYWORDS = [
    # 科技
    "AI", "人工智能", "芯片", "半导体", "算力", "光刻", "封装", "存储",
    "机器人", "具身智能", "自动驾驶", "智能驾驶", "车联网",
    "5G", "6G", "通信", "光纤", "光模块", "量子",
    "云计算", "大数据", "区块链", "元宇宙", "AR", "VR",
    "软件", "信创", "国产替代", "操作系统", "数据库",
    # 新能源
    "新能源", "光伏", "风电", "储能", "锂电", "钠电", "氢能", "燃料电池",
    "充电桩", "特高压", "智能电网",
    # 消费
    "白酒", "食品", "医药", "医疗", "中药", "生物", "疫苗",
    "消费", "免税", "旅游", "酒店", "餐饮",
    # 金融地产
    "银行", "保险", "券商", "地产", "房地产", "基建", "水泥", "钢铁",
    # 制造
    "军工", "航空", "航天", "船舶", "汽车", "零部件",
    "有色", "稀土", "黄金", "铜", "铝", "煤炭", "石油",
    # 农业
    "农业", "种业", "养殖", "猪肉", "鸡肉",
    # 其他热点
    "传媒", "游戏", "影视", "短剧", "网红", "直播",
]

def filter_stock_keywords(hot_list):
    """筛选A股相关关键词（v1.1 增强版）"""
    # 精确匹配关键词
    exact_keywords = [
        "A股", "大A", "股市", "股票", "涨停", "跌停", "牛市", "熊市",
        "基金", "证券", "券商", "上证", "深证", "创业板", "科创板",
        "涨停板", "跌停板", "打板", "龙头", "妖股",
        "利好", "利空", "暴跌", "暴涨", "反弹", "回调",
        "北向资金", "主力", "游资", "散户",
        "融资融券", "两融", "期权", "期货",
        "大盘", "行情", "板块", "概念", "题材",
    ]
    
    stock_related = []
    seen_keywords = set()
    
    for item in hot_list:
        keyword = item["keyword"]
        if keyword in seen_keywords:
            continue
        seen_keywords.add(keyword)
        
        # 精确匹配
        matched = False
        for kw in exact_keywords:
            if kw in keyword:
                item["match_reason"] = f"包含「{kw}」"
                stock_related.append(item)
                matched = True
                break
        
        # 板块关键词匹配
        if not matched:
            for sector in SECTOR_KEYWORDS:
                if sector in keyword and len(keyword) <= 20:
                    item["match_reason"] = f"板块「{sector}」"
                    stock_related.append(item)
                    matched = True
                    break
        
        # 模糊匹配（兜底）
        if not matched:
            fuzzy_chars = ["股", "涨", "跌", "板"]
            for ch in fuzzy_chars:
                if ch in keyword and len(keyword) <= 10:
                    item["match_reason"] = "模糊匹配"
                    stock_related.append(item)
                    break
    
    return stock_related


# ============================================================
# 2. A股行情数据 (AKShare)
# ============================================================
def fetch_market_overview():
    """获取大盘指数"""
    try:
        import akshare as ak
        import warnings
        warnings.filterwarnings("ignore")
        
        indices = [
            ("sh000001", "上证指数"),
            ("sz399001", "深证成指"),
            ("sz399006", "创业板指"),
        ]
        
        results = []
        for symbol, name in indices:
            try:
                df = ak.stock_zh_index_daily(symbol=symbol)
                if df is not None and len(df) >= 2:
                    last = df.iloc[-1]
                    prev = df.iloc[-2]
                    close = float(last["close"])
                    prev_close = float(prev["close"])
                    change_pct = (close - prev_close) / prev_close * 100
                    results.append({
                        "name": name,
                        "close": round(close, 2),
                        "change_pct": round(change_pct, 2),
                    })
            except Exception:
                continue
        
        return results
    except Exception as e:
        log(f"⚠️  大盘数据获取失败: {e}")
        return []


def fetch_market_trend(days=5):
    """获取大盘近N天趋势"""
    try:
        import akshare as ak
        import warnings
        warnings.filterwarnings("ignore")
        
        indices = [
            ("sh000001", "上证指数"),
            ("sz399001", "深证成指"),
            ("sz399006", "创业板指"),
        ]
        
        results = {}
        for symbol, name in indices:
            try:
                df = ak.stock_zh_index_daily(symbol=symbol)
                if df is not None and len(df) >= days:
                    recent = df.tail(days)
                    trend = []
                    for _, row in recent.iterrows():
                        trend.append({
                            "date": str(row.get("date", "")),
                            "close": round(float(row["close"]), 2),
                        })
                    # 计算趋势方向
                    if len(trend) >= 2:
                        start = trend[0]["close"]
                        end = trend[-1]["close"]
                        total_pct = (end - start) / start * 100
                        results[name] = {
                            "trend": trend,
                            "total_change_pct": round(total_pct, 2),
                            "direction": "📈" if total_pct > 0 else "📉" if total_pct < 0 else "➡️",
                        }
            except Exception:
                continue
        
        return results
    except Exception as e:
        log(f"⚠️  趋势数据获取失败: {e}")
        return {}


def fetch_zt_dt():
    """获取涨停/跌停数据"""
    today = datetime.now().strftime("%Y%m%d")
    result = {"涨停": [], "跌停": []}
    
    try:
        import akshare as ak
        import warnings
        warnings.filterwarnings("ignore")
        
        # 涨停板
        try:
            zt_df = ak.stock_zt_pool_em(date=today)
            if zt_df is not None and not zt_df.empty:
                for _, row in zt_df.head(15).iterrows():
                    result["涨停"].append({
                        "code": str(row.get("代码", "")),
                        "name": str(row.get("名称", "")),
                        "change_pct": float(row.get("涨跌幅", 0)),
                        "reason": str(row.get("涨停原因", "")),
                        "turnover": str(row.get("换手率", "")),
                    })
        except Exception:
            pass
        
        # 跌停板
        try:
            dt_df = ak.stock_zt_pool_dtgc_em(date=today)
            if dt_df is not None and not dt_df.empty:
                for _, row in dt_df.head(15).iterrows():
                    result["跌停"].append({
                        "code": str(row.get("代码", "")),
                        "name": str(row.get("名称", "")),
                        "change_pct": float(row.get("涨跌幅", 0)),
                    })
        except Exception:
            pass
        
    except Exception as e:
        log(f"⚠️  涨停/跌停数据获取失败: {e}")
    
    return result


def fetch_hot_sectors():
    """获取热门板块"""
    try:
        import akshare as ak
        import warnings
        warnings.filterwarnings("ignore")
        
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            sectors = []
            for _, row in df.head(15).iterrows():
                sectors.append({
                    "name": str(row.get("板块名称", "")),
                    "change_pct": float(row.get("涨跌幅", 0)),
                    "leader": str(row.get("领涨股票", "")),
                    "leader_change": float(row.get("领涨股票-涨跌幅", 0)) if "领涨股票-涨跌幅" in row else 0,
                    "up_count": int(row.get("上涨家数", 0)) if "上涨家数" in row else 0,
                    "down_count": int(row.get("下跌家数", 0)) if "下跌家数" in row else 0,
                })
            return sectors
        return []
    except Exception as e:
        log(f"⚠️  板块数据获取失败: {e}")
        return []


def fetch_top_stocks():
    """获取涨幅/跌幅前10"""
    try:
        import akshare as ak
        import warnings
        warnings.filterwarnings("ignore")
        
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            # 涨幅前10
            top_up = df.nlargest(10, "涨跌幅")[["代码", "名称", "涨跌幅", "最新价", "成交额"]].to_dict("records")
            # 跌幅前10
            top_down = df.nsmallest(10, "涨跌幅")[["代码", "名称", "涨跌幅", "最新价", "成交额"]].to_dict("records")
            # 成交额前10
            top_volume = df.nlargest(10, "成交额")[["代码", "名称", "涨跌幅", "最新价", "成交额"]].to_dict("records")
            
            return {
                "涨幅榜": [{"code": str(r["代码"]), "name": str(r["名称"]), "change_pct": float(r["涨跌幅"]), "price": float(r["最新价"]) if r["最新价"] else 0, "volume": float(r["成交额"]) if r["成交额"] else 0} for r in top_up],
                "跌幅榜": [{"code": str(r["代码"]), "name": str(r["名称"]), "change_pct": float(r["涨跌幅"]), "price": float(r["最新价"]) if r["最新价"] else 0, "volume": float(r["成交额"]) if r["成交额"] else 0} for r in top_down],
                "成交榜": [{"code": str(r["代码"]), "name": str(r["名称"]), "change_pct": float(r["涨跌幅"]), "price": float(r["最新价"]) if r["最新价"] else 0, "volume": float(r["成交额"]) if r["成交额"] else 0} for r in top_volume],
            }
        return {}
    except Exception as e:
        log(f"⚠️  个股排行获取失败: {e}")
        return {}


# ============================================================
# 2.5 北向资金数据 (v1.1 新增)
# ============================================================
def fetch_northbound_flow():
    """获取北向资金（沪股通+深股通）"""
    try:
        import akshare as ak
        import warnings
        warnings.filterwarnings("ignore")
        
        result = {"沪股通": {}, "深股通": {}, "合计": {}}
        
        try:
            # 北向资金实时流入
            df = ak.stock_hsgt_north_net_flow_in_em()
            if df is not None and not df.empty:
                last_row = df.iloc[-1]
                result["date"] = str(last_row.get("date", ""))
                result["north_net"] = round(float(last_row.get("value", 0)), 2)
        except Exception:
            pass
        
        try:
            # 沪股通+深股通 汇总
            df2 = ak.stock_hsgt_fund_flow_summary_em()
            if df2 is not None and not df2.empty:
                last = df2.iloc[-1]
                result["沪股通"] = {
                    "buy": round(float(last.get("沪股通-买入", 0)), 2),
                    "sell": round(float(last.get("沪股通-卖出", 0)), 2),
                    "net": round(float(last.get("沪股通-净买入", 0)), 2),
                }
                result["深股通"] = {
                    "buy": round(float(last.get("深股通-买入", 0)), 2),
                    "sell": round(float(last.get("深股通-卖出", 0)), 2),
                    "net": round(float(last.get("深股通-净买入", 0)), 2),
                }
                result["合计"] = {
                    "net": round(result["沪股通"]["net"] + result["深股通"]["net"], 2),
                }
        except Exception:
            pass
        
        return result
    except Exception as e:
        log(f"⚠️  北向资金获取失败: {e}")
        return {}


# ============================================================
# 3. 关联分析
# ============================================================
def analyze_correlation(stock_hot, zt_dt, sectors):
    """分析热搜与行情的关联"""
    analysis = {
        "hot_stock_mentions": [],
        "hot_and_zt": [],
        "hot_sectors": [],
        "insights": [],
    }
    
    # 提取热搜中的个股名
    stock_names = []
    for item in stock_hot:
        keyword = item["keyword"]
        clean = keyword.replace("#", "")
        if 2 <= len(clean) <= 8:
            stock_names.append(clean)
    
    analysis["hot_stock_mentions"] = stock_names[:10]
    
    # 与涨停板交叉
    zt_names = [item["name"] for item in zt_dt.get("涨停", [])]
    mentioned_and_zt = [name for name in stock_names if name in zt_names]
    
    if mentioned_and_zt:
        analysis["hot_and_zt"] = mentioned_and_zt
        analysis["insights"].append(
            f"🔥 同时出现在微博热搜和涨停板: {', '.join(mentioned_and_zt)}"
        )
    
    # 热搜板块
    sector_keywords = []
    for item in stock_hot:
        kw = item["keyword"]
        if any(w in kw for w in ["板块", "概念", "题材"]):
            sector_keywords.append(kw)
    
    if sector_keywords:
        analysis["hot_sectors"] = sector_keywords
        analysis["insights"].append(
            f"📊 热搜板块关键词: {', '.join(sector_keywords[:5])}"
        )
    
    # 涨停原因分析
    if zt_dt.get("涨停"):
        reasons = {}
        for item in zt_dt["涨停"]:
            reason = item.get("reason", "").strip()
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        if reasons:
            top_reasons = sorted(reasons.items(), key=lambda x: -x[1])[:3]
            for reason, count in top_reasons:
                analysis["insights"].append(f"📈 涨停原因「{reason}」: {count} 只")
    
    return analysis


# ============================================================
# 4. 本地快照缓存 (v1.1 新增)
# ============================================================
def save_snapshot(data):
    """保存当日快照"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot = {
        "date": today,
        "market": data.get("market", []),
        "zt_dt": data.get("zt_dt", {}),
        "sectors": data.get("sectors", []),
        "northbound": data.get("northbound", {}),
    }
    path = os.path.join(CACHE_DIR, f"{today}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_recent_snapshots(days=5):
    """加载最近N天快照"""
    snapshots = []
    today = datetime.now()
    for i in range(days):
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        path = os.path.join(CACHE_DIR, f"{date}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    snapshots.append(json.load(f))
            except Exception:
                pass
    return sorted(snapshots, key=lambda x: x["date"])


# ============================================================
# 5. 报告生成
# ============================================================
def format_hot(num):
    """格式化热度数字"""
    if num >= 1000000:
        return f"{num/10000:.0f}万"
    elif num >= 10000:
        return f"{num/10000:.1f}万"
    return str(num)


def format_amount(val):
    """格式化金额（亿/万）"""
    if abs(val) >= 10000:
        return f"{val/10000:.2f}万亿"
    elif abs(val) >= 1:
        return f"{val:.2f}亿"
    else:
        return f"{val*10000:.0f}万"


def log(msg):
    """日志输出"""
    if not JSON_MODE:
        print(msg, file=sys.stderr)


def generate_report(data):
    """生成完整报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = []
    lines.append(f"📊 A股微博热搜分析报告 v1.1")
    lines.append(f"⏰ {now}")
    lines.append("=" * 50)
    
    # 大盘
    market = data.get("market", [])
    lines.append("")
    lines.append("📈 【大盘概览】")
    lines.append("-" * 40)
    if market:
        for m in market:
            arrow = "🔴" if m["change_pct"] < 0 else "🟢"
            lines.append(f"  {arrow} {m['name']}: {m['close']} ({m['change_pct']:+.2f}%)")
    else:
        lines.append("  数据获取中...")
    
    # 北向资金（v1.1 新增）
    nb = data.get("northbound", {})
    if nb.get("north_net") is not None:
        nb_arrow = "🟢 净流入" if nb["north_net"] > 0 else "🔴 净流出"
        lines.append("")
        lines.append("🌊 【北向资金】")
        lines.append("-" * 40)
        lines.append(f"  {nb_arrow}: {format_amount(abs(nb['north_net']))}")
        if nb.get("沪股通") and nb["沪股通"].get("net") is not None:
            lines.append(f"  沪股通净买入: {format_amount(abs(nb['沪股通']['net']))}")
        if nb.get("深股通") and nb["深股通"].get("net") is not None:
            lines.append(f"  深股通净买入: {format_amount(abs(nb['深股通']['net']))}")
    
    # 大盘趋势（v1.1 新增）
    trend = data.get("trend", {})
    if trend:
        lines.append("")
        lines.append("📉 【近5日趋势】")
        lines.append("-" * 40)
        for name, info in trend.items():
            lines.append(f"  {info['direction']} {name}: {info['total_change_pct']:+.2f}% (5日)")
            # 迷你趋势图
            pts = info.get("trend", [])
            if pts:
                closes = [p["close"] for p in pts]
                min_c, max_c = min(closes), max(closes)
                if max_c > min_c:
                    bar_width = 20
                    bars = ""
                    for c in closes:
                        h = int((c - min_c) / (max_c - min_c) * bar_width)
                        bars += "▓" * h + "░" * (bar_width - h) + " "
                    lines.append(f"    {bars}")
                    lines.append(f"    {' → '.join(str(p['close']) for p in pts)}")
    
    # 微博热搜
    stock_hot = data.get("stock_hot", [])
    lines.append("")
    lines.append(f"🔥 【微博A股热搜】 ({len(stock_hot)} 条)")
    lines.append("-" * 40)
    if stock_hot:
        for item in stock_hot[:15]:
            lines.append(f"  #{item['keyword']}#  🔥{format_hot(item['hot'])}  ({item['match_reason']})")
    else:
        lines.append("  暂无A股相关热搜")
    
    if BRIEF_MODE:
        lines.append("")
        lines.append("🟢 【涨停板】")
        lines.append("-" * 40)
        zt = data.get("zt_dt", {}).get("涨停", [])
        for item in zt[:10]:
            lines.append(f"  {item['name']}({item['code']}) +{item['change_pct']:.1f}%  {item.get('reason', '')}")
        
        lines.append("")
        lines.append("=" * 50)
        lines.append("📌 数据来源: 微博热搜 + AKShare")
        return "\n".join(lines)
    
    # 涨停
    zt = data.get("zt_dt", {}).get("涨停", [])
    lines.append("")
    lines.append(f"🟢 【涨停板 TOP{min(15, len(zt))}】")
    lines.append("-" * 40)
    if zt:
        for item in zt[:15]:
            lines.append(f"  {item['name']}({item['code']}) +{item['change_pct']:.1f}%  {item.get('reason', '')}")
    else:
        lines.append("  无涨停或数据获取中...")
    
    # 跌停
    dt = data.get("zt_dt", {}).get("跌停", [])
    lines.append("")
    lines.append(f"🔴 【跌停板 TOP{min(15, len(dt))}】")
    lines.append("-" * 40)
    if dt:
        for item in dt[:15]:
            lines.append(f"  {item['name']}({item['code']}) {item['change_pct']:.1f}%")
    else:
        lines.append("  无跌停或数据获取中...")
    
    # 热门板块
    sectors = data.get("sectors", [])
    lines.append("")
    lines.append(f"📊 【热门板块 TOP{min(10, len(sectors))}】")
    lines.append("-" * 40)
    if sectors:
        for item in sectors[:10]:
            arrow = "🔴" if item["change_pct"] < 0 else "🟢"
            lines.append(f"  {arrow} {item['name']}: {item['change_pct']:+.2f}%  领涨: {item['leader']}")
    else:
        lines.append("  数据获取中...")
    
    # 个股排行
    stocks = data.get("stocks", {})
    if stocks.get("涨幅榜"):
        lines.append("")
        lines.append("📈 【今日涨幅榜 TOP5】")
        lines.append("-" * 40)
        for item in stocks["涨幅榜"][:5]:
            lines.append(f"  🟢 {item['name']}({item['code']}) +{item['change_pct']:.1f}%  ¥{item['price']}")
    
    if stocks.get("成交榜"):
        lines.append("")
        lines.append("💰 【今日成交额 TOP5】")
        lines.append("-" * 40)
        for item in stocks["成交榜"][:5]:
            vol_str = f"{item['volume']/100000000:.1f}亿" if item['volume'] >= 100000000 else f"{item['volume']/10000:.0f}万"
            lines.append(f"  💰 {item['name']}({item['code']}) {vol_str}  {item['change_pct']:+.1f}%")
    
    # 关联分析
    corr = data.get("correlation", {})
    lines.append("")
    lines.append("🔗 【热搜 vs 行情 关联分析】")
    lines.append("-" * 40)
    
    if corr.get("hot_stock_mentions"):
        lines.append(f"  💬 热搜提及个股: {', '.join(corr['hot_stock_mentions'][:5])}")
    
    if corr.get("hot_and_zt"):
        lines.append(f"  🔥 热搜+涨停双重热度: {', '.join(corr['hot_and_zt'])}")
    
    if corr.get("hot_sectors"):
        lines.append(f"  📊 热搜板块: {', '.join(corr['hot_sectors'][:3])}")
    
    if corr.get("insights"):
        for note in corr["insights"]:
            lines.append(f"  {note}")
    
    if not corr.get("insights") and not corr.get("hot_stock_mentions"):
        lines.append("  暂无明显关联")
    
    # 历史快照对比（v1.1 新增）
    snapshots = data.get("snapshots", [])
    if snapshots and len(snapshots) >= 2:
        lines.append("")
        lines.append("📅 【历史数据对比】")
        lines.append("-" * 40)
        for snap in snapshots[-5:]:
            date = snap["date"]
            snap_zt = len(snap.get("zt_dt", {}).get("涨停", []))
            snap_dt = len(snap.get("zt_dt", {}).get("跌停", []))
            snap_sectors = len(snap.get("sectors", []))
            snap_nb = snap.get("northbound", {})
            nb_val = snap_nb.get("north_net", "N/A")
            nb_str = f"  北向: {format_amount(abs(nb_val))}" if isinstance(nb_val, (int, float)) else ""
            lines.append(f"  📌 {date}: 涨停{snap_zt}家 / 跌停{snap_dt}家 / 板块{snap_sectors}个{nb_str}")
    
    lines.append("")
    lines.append("=" * 50)
    lines.append("📌 数据来源: 微博热搜 + AKShare (东方财富)")
    lines.append("🆕 v1.1 新增: 北向资金 / 大盘趋势 / 关键词增强 / 历史快照")
    lines.append("⚠️ 仅供参考，不构成投资建议")
    
    return "\n".join(lines)


# ============================================================
# Main
# ============================================================
def main():
    log("🔍 正在抓取数据... (v1.1)\n")
    
    data = {}
    
    # 1. 微博热搜
    if not NO_WEIBO:
        log("  📱 微博热搜...")
        hot_list = fetch_weibo_hot()
        data["weibo_hot_total"] = len(hot_list)
        data["stock_hot"] = filter_stock_keywords(hot_list)
    else:
        data["stock_hot"] = []
    
    # 2. 大盘指数
    if not NO_MARKET:
        log("  📈 大盘指数...")
        data["market"] = fetch_market_overview()
    else:
        data["market"] = []
    
    # 3. 涨停/跌停
    if not NO_MARKET:
        log("  🟢 涨停/跌停...")
        data["zt_dt"] = fetch_zt_dt()
    else:
        data["zt_dt"] = {"涨停": [], "跌停": []}
    
    # 4. 热门板块
    if not NO_MARKET and not BRIEF_MODE:
        log("  📊 热门板块...")
        data["sectors"] = fetch_hot_sectors()
    else:
        data["sectors"] = []
    
    # 5. 个股排行
    if not NO_MARKET and not BRIEF_MODE:
        log("  📈 个股排行...")
        data["stocks"] = fetch_top_stocks()
    else:
        data["stocks"] = {}
    
    # 6. 北向资金 (v1.1 新增)
    if not NO_MARKET:
        log("  🌊 北向资金...")
        data["northbound"] = fetch_northbound_flow()
    else:
        data["northbound"] = {}
    
    # 7. 大盘趋势 (v1.1 新增)
    if not NO_MARKET and TREND_MODE:
        log("  📉 大盘趋势...")
        data["trend"] = fetch_market_trend(days=5)
    else:
        data["trend"] = {}
    
    # 8. 关联分析
    log("  🔗 关联分析...")
    data["correlation"] = analyze_correlation(data["stock_hot"], data["zt_dt"], data["sectors"])
    
    # 9. 保存快照
    save_snapshot(data)
    
    # 10. 加载历史快照
    if not BRIEF_MODE:
        data["snapshots"] = load_recent_snapshots(days=5)
    
    # 11. 输出
    if JSON_MODE:
        data["timestamp"] = datetime.now().isoformat()
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(generate_report(data))


if __name__ == "__main__":
    main()
