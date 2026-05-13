#!/usr/bin/env python3
"""
A股微博热搜分析 v2.1
- 微博热搜抓取 + A股关键词筛选
- A股行情数据（大盘/涨停/跌停/板块）
- 北向资金数据
- 热搜 vs 行情关联分析
- 历史趋势对比 (--trend)
- 本地快照缓存
- 个股查询 (--stock)
- 自选股 (--watchlist)
- Markdown 导出 (--md)
- 市场情绪指标
- 板块轮动分析
- 非交易日提示
- 🆕 东方财富股吧热帖 (--guba)
- 🆕 财经新闻聚合 (--news)
- 🆕 雪球讨论 (--xueqiu)
"""

import json
import sys
import os
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import akshare as ak
    import warnings
    warnings.filterwarnings("ignore")
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, ".cache")
VERSION = "2.1.0"

# v2.1: 导入社区+新闻模块
try:
    import v2_1_patch as v21
    HAS_V21 = True
except ImportError:
    HAS_V21 = False

# ============================================================
# 工具函数
# ============================================================
def log(msg):
    print(msg, file=sys.stderr)

def format_hot(num):
    if num >= 1000000:
        return f"{num/1000000:.1f}万"
    elif num >= 10000:
        return f"{num/10000:.1f}万"
    elif num >= 1000:
        return f"{num/1000:.1f}千"
    return str(num)

def format_yi(num):
    """格式化为亿"""
    if abs(num) >= 10000:
        return f"{num/10000:.2f}万亿"
    return f"{num:.2f}亿"

def is_trading_day():
    """判断今天是否为交易日（简单判断：工作日=交易日，节假日不判断）"""
    now = datetime.now()
    # 9:00-15:30 之间视为交易时段
    if now.weekday() >= 5:  # 周六日
        return False
    return True

def get_last_trading_date():
    """获取最近一个交易日日期"""
    now = datetime.now()
    # 如果是周末，回退到周五
    offset = 0
    if now.weekday() == 5:  # 周六
        offset = 1
    elif now.weekday() == 6:  # 周日
        offset = 2
    # 如果在盘前（9:30前），用前一天
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        offset += 1
    return (now - timedelta(days=offset)).strftime("%Y-%m-%d")


# ============================================================
# 1. 微博热搜抓取
# ============================================================
def fetch_weibo_hot(retries=2):
    url = "https://weibo.com/ajax/side/hotSearch"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://weibo.com",
    }
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            hot_list = data.get("data", {}).get("realtime", [])
            return [
                {
                    "rank": item.get("rank", 0),
                    "keyword": item.get("word", ""),
                    "hot": item.get("num", 0),
                    "category": item.get("category", ""),
                    "label": item.get("label_name", ""),
                }
                for item in hot_list[:50]
            ]
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            log(f"⚠️  微博热搜获取失败: {e}")
            return []


SECTOR_KEYWORDS = [
    "AI", "人工智能", "芯片", "半导体", "算力", "光刻", "封装", "存储",
    "机器人", "具身智能", "自动驾驶", "智能驾驶", "车联网",
    "5G", "6G", "通信", "光纤", "光模块", "量子",
    "云计算", "大数据", "区块链", "元宇宙", "AR", "VR",
    "软件", "信创", "国产替代", "操作系统", "数据库",
    "新能源", "光伏", "风电", "储能", "锂电", "钠电", "氢能", "燃料电池",
    "充电桩", "特高压", "智能电网",
    "白酒", "食品", "医药", "医疗", "中药", "生物", "疫苗",
    "消费", "免税", "旅游", "酒店", "餐饮",
    "银行", "保险", "券商", "地产", "房地产", "基建", "水泥", "钢铁",
    "军工", "航空", "航天", "船舶", "汽车", "零部件",
    "有色", "稀土", "黄金", "铜", "铝", "煤炭", "石油",
    "农业", "种业", "养殖", "猪肉", "鸡肉",
    "传媒", "游戏", "影视", "短剧", "网红", "直播",
]

EXACT_KEYWORDS = [
    "A股", "大A", "股市", "股票", "涨停", "跌停", "牛市", "熊市",
    "基金", "证券", "券商", "上证", "深证", "创业板", "科创板",
    "涨停板", "跌停板", "打板", "龙头", "妖股",
    "利好", "利空", "暴跌", "暴涨", "反弹", "回调",
    "北向资金", "主力", "游资", "散户",
    "融资融券", "两融", "期权", "期货",
    "大盘", "行情", "板块", "概念", "题材",
]

def filter_stock_keywords(hot_list, watchlist=None):
    stock_related = []
    seen = set()
    for item in hot_list:
        kw = item["keyword"]
        if kw in seen:
            continue
        seen.add(kw)
        matched = False
        for ek in EXACT_KEYWORDS:
            if ek in kw:
                item["match_reason"] = f"包含「{ek}」"
                stock_related.append(item)
                matched = True
                break
        if not matched:
            for sector in SECTOR_KEYWORDS:
                if sector in kw and len(kw) <= 20:
                    item["match_reason"] = f"板块「{sector}」"
                    stock_related.append(item)
                    matched = True
                    break
        # v2.0: 收窄模糊匹配，只匹配 <=6 字符
        if not matched:
            if any(ch in kw for ch in ["股", "涨", "跌"]) and len(kw) <= 6:
                item["match_reason"] = "模糊匹配"
                stock_related.append(item)
    if watchlist:
        stock_related = [i for i in stock_related if any(w in i["keyword"] for w in watchlist)]
    return stock_related


# ============================================================
# 2. A股行情数据
# ============================================================
def fetch_market_overview():
    if not HAS_AKSHARE:
        return []
    results = []
    for symbol, name in [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is not None and len(df) >= 2:
                close = float(df.iloc[-1]["close"])
                prev = float(df.iloc[-2]["close"])
                pct = (close - prev) / prev * 100
                results.append({"name": name, "close": round(close, 2), "change_pct": round(pct, 2)})
        except Exception:
            continue
    return results


def fetch_market_trend(days=5):
    if not HAS_AKSHARE:
        return {}
    results = {}
    for symbol, name in [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is not None and len(df) >= days:
                recent = df.tail(days)
                trend = [{"date": str(r.get("date", "")), "close": round(float(r["close"]), 2)} for _, r in recent.iterrows()]
                if len(trend) >= 2:
                    total = (trend[-1]["close"] - trend[0]["close"]) / trend[0]["close"] * 100
                    results[name] = {
                        "trend": trend,
                        "total_change_pct": round(total, 2),
                        "direction": "📈" if total > 0 else "📉" if total < 0 else "➡️",
                    }
        except Exception:
            continue
    return results


def fetch_zt_dt():
    if not HAS_AKSHARE:
        return {"涨停": [], "跌停": []}
    today = datetime.now().strftime("%Y%m%d")
    result = {"涨停": [], "跌停": []}
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
    return result


def fetch_hot_sectors():
    if not HAS_AKSHARE:
        return []
    try:
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            sectors = []
            for _, row in df.head(15).iterrows():
                try:
                    lc = float(row["领涨股票-涨跌幅"]) if "领涨股票-涨跌幅" in row.index else 0
                except (ValueError, TypeError):
                    lc = 0
                try:
                    uc = int(row["上涨家数"]) if "上涨家数" in row.index else 0
                except (ValueError, TypeError):
                    uc = 0
                try:
                    dc = int(row["下跌家数"]) if "下跌家数" in row.index else 0
                except (ValueError, TypeError):
                    dc = 0
                sectors.append({
                    "name": str(row.get("板块名称", "")),
                    "change_pct": float(row.get("涨跌幅", 0)),
                    "leader": str(row.get("领涨股票", "")),
                    "leader_change": lc,
                    "up_count": uc,
                    "down_count": dc,
                })
            return sectors
    except Exception as e:
        log(f"⚠️  板块数据获取失败: {e}")
    return []


def fetch_top_stocks():
    if not HAS_AKSHARE:
        return {}
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            cols = ["代码", "名称", "涨跌幅", "最新价", "成交额"]
            def to_list(sub):
                return [{"code": str(r["代码"]), "name": str(r["名称"]),
                         "change_pct": float(r["涨跌幅"]),
                         "price": float(r["最新价"]) if r["最新价"] else 0,
                         "volume": float(r["成交额"]) if r["成交额"] else 0} for _, r in sub.iterrows()]
            return {
                "涨幅榜": to_list(df.nlargest(10, "涨跌幅")),
                "跌幅榜": to_list(df.nsmallest(10, "涨跌幅")),
                "成交榜": to_list(df.nlargest(10, "成交额")),
            }
    except Exception as e:
        log(f"⚠️  个股排行获取失败: {e}")
    return {}


def fetch_single_stock(code):
    """查询单只股票详情"""
    if not HAS_AKSHARE:
        return None
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            row = df[df["代码"] == code]
            if row.empty:
                return None
            r = row.iloc[0]
            return {
                "code": str(r.get("代码", "")),
                "name": str(r.get("名称", "")),
                "price": float(r.get("最新价", 0)),
                "change_pct": float(r.get("涨跌幅", 0)),
                "change_amt": float(r.get("涨跌额", 0)),
                "volume": float(r.get("成交量", 0)),
                "turnover": float(r.get("成交额", 0)),
                "high": float(r.get("最高", 0)),
                "low": float(r.get("最低", 0)),
                "open": float(r.get("今开", 0)),
                "prev_close": float(r.get("昨收", 0)),
                "pe": r.get("市盈率-动态", ""),
                "total_mv": r.get("总市值", ""),
                "circ_mv": r.get("流通市值", ""),
            }
    except Exception as e:
        log(f"⚠️  个股查询失败: {e}")
    return None


def fetch_market_stats():
    """获取市场情绪统计（涨跌家数、涨停/跌停数）"""
    if not HAS_AKSHARE:
        return {}
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            total = len(df)
            up = len(df[df["涨跌幅"] > 0])
            down = len(df[df["涨跌幅"] < 0])
            flat = total - up - down
            return {
                "total": total, "up": up, "down": down, "flat": flat,
                "up_ratio": round(up / total * 100, 1) if total else 0,
            }
    except Exception:
        pass
    return {}


# ============================================================
# 2.5 北向资金
# ============================================================
def fetch_northbound_flow():
    if not HAS_AKSHARE:
        return {}
    result = {"沪股通": {}, "深股通": {}, "合计": {}}
    try:
        df = ak.stock_hsgt_north_net_flow_in_em()
        if df is not None and not df.empty:
            last_row = df.iloc[-1]
            result["date"] = str(last_row.get("date", ""))
            result["north_net"] = round(float(last_row.get("value", 0)), 2)
    except Exception:
        pass
    try:
        df2 = ak.stock_hsgt_fund_flow_summary_em()
        if df2 is not None and not df2.empty:
            last = df2.iloc[-1]
            # v2.0: 逐列容错
            for prefix, key in [("沪股通", "沪股通"), ("深股通", "深股通")]:
                try:
                    result[key] = {
                        "buy": round(float(last.get(f"{prefix}-买入", 0)), 2),
                        "sell": round(float(last.get(f"{prefix}-卖出", 0)), 2),
                        "net": round(float(last.get(f"{prefix}-净买入", 0)), 2),
                    }
                except (ValueError, TypeError):
                    result[key] = {"buy": 0, "sell": 0, "net": 0}
            hn = result["沪股通"].get("net", 0)
            sn = result["深股通"].get("net", 0)
            result["合计"]["net"] = round(hn + sn, 2)
    except Exception:
        pass
    return result


# ============================================================
# 3. 关联分析
# ============================================================
def analyze_correlation(stock_hot, zt_dt, sectors):
    analysis = {"hot_stock_mentions": [], "hot_and_zt": [], "hot_sectors": [], "insights": []}
    stock_names = [i["keyword"].replace("#", "") for i in stock_hot if 2 <= len(i["keyword"].replace("#", "")) <= 8]
    analysis["hot_stock_mentions"] = stock_names[:10]
    zt_names = [i["name"] for i in zt_dt.get("涨停", [])]
    overlap = [n for n in stock_names if n in zt_names]
    if overlap:
        analysis["hot_and_zt"] = overlap
        analysis["insights"].append(f"🔥 同时出现在微博热搜和涨停板: {', '.join(overlap)}")
    sector_kw = [i["keyword"] for i in stock_hot if any(w in i["keyword"] for w in ["板块", "概念", "题材"])]
    if sector_kw:
        analysis["hot_sectors"] = sector_kw
        analysis["insights"].append(f"📊 热搜板块关键词: {', '.join(sector_kw[:5])}")
    if zt_dt.get("涨停"):
        reasons = {}
        for item in zt_dt["涨停"]:
            r = item.get("reason", "").strip()
            if r:
                reasons[r] = reasons.get(r, 0) + 1
        for r, c in sorted(reasons.items(), key=lambda x: -x[1])[:3]:
            analysis["insights"].append(f"📈 涨停原因「{r}」: {c} 只")
    return analysis


# ============================================================
# 3.5 板块轮动分析 (v2.0)
# ============================================================
def analyze_sector_rotation():
    """对比近3天板块数据，发现轮动趋势"""
    snapshots = load_recent_snapshots(3)
    if len(snapshots) < 2:
        return None
    try:
        today_sectors = {s["name"]: s["change_pct"] for s in snapshots[-1].get("sectors", [])}
        prev_sectors = {s["name"]: s["change_pct"] for s in snapshots[-2].get("sectors", [])}
        today_set = set(today_sectors.keys())
        prev_set = set(prev_sectors.keys())
        new_in = today_set - prev_set
        gone = prev_set - today_set
        both = today_set & prev_set
        hot_rotation = []
        for name in both:
            diff = today_sectors[name] - prev_sectors.get(name, 0)
            if abs(diff) > 1:
                hot_rotation.append({"name": name, "today": today_sectors[name], "change": round(diff, 2)})
        hot_rotation.sort(key=lambda x: -x["change"])
        return {
            "new": list(new_in)[:5],
            "gone": list(gone)[:5],
            "hot": hot_rotation[:5],
        }
    except Exception:
        return None


# ============================================================
# 4. 快照缓存
# ============================================================
def save_snapshot(data):
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
def render_text(data, args):
    lines = []
    lines.append("📊 A股微博热搜分析报告 v2.1")
    lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if not is_trading_day():
        lines.append(f"🏖️  今日非交易日，数据为最近交易日 ({get_last_trading_date()})")
    lines.append("=" * 50)

    # 市场情绪
    stats = data.get("stats", {})
    if stats:
        total = stats.get("total", 0)
        up = stats.get("up", 0)
        down = stats.get("down", 0)
        flat = stats.get("flat", 0)
        emoji = "🟢" if up > down else "🔴" if down > up else "⚪"
        lines.append(f"\n{emoji} 【市场情绪】")
        lines.append("-" * 40)
        lines.append(f"  上涨 {up} 家 / 下跌 {down} 家 / 平盘 {flat} 家（共 {total} 家）")
        lines.append(f"  涨跌比 {up}:{down}  上涨占比 {stats.get('up_ratio', 0)}%")
        zt_count = len(data.get("zt_dt", {}).get("涨停", []))
        dt_count = len(data.get("zt_dt", {}).get("跌停", []))
        if zt_count or dt_count:
            lines.append(f"  涨停 {zt_count} 家 / 跌停 {dt_count} 家")

    # 大盘
    if data.get("market"):
        lines.append(f"\n📈 【大盘概览】")
        lines.append("-" * 40)
        for idx in data["market"]:
            emoji = "🟢" if idx["change_pct"] > 0 else "🔴" if idx["change_pct"] < 0 else "⚪"
            lines.append(f"  {emoji} {idx['name']}: {idx['close']} ({idx['change_pct']:+.2f}%)")

    # 北向资金
    nb = data.get("northbound", {})
    if nb.get("合计", {}).get("net"):
        net = nb["合计"]["net"]
        emoji = "🟢" if net > 0 else "🔴"
        lines.append(f"\n🌊 【北向资金】")
        lines.append("-" * 40)
        lines.append(f"  {emoji} 净流入: {format_yi(net)}")
        if nb.get("沪股通", {}).get("net"):
            lines.append(f"  沪股通净买入: {format_yi(nb['沪股通']['net'])}")
        if nb.get("深股通", {}).get("net"):
            lines.append(f"  深股通净买入: {format_yi(nb['深股通']['net'])}")

    # 趋势
    if data.get("trend"):
        lines.append(f"\n📉 【近5日趋势】")
        lines.append("-" * 40)
        for name, info in data["trend"].items():
            lines.append(f"  {info['direction']} {name}: {info['total_change_pct']:+.2f}% (5日)")
            if info.get("trend"):
                prices = " → ".join(str(t["close"]) for t in info["trend"])
                lines.append(f"    {prices}")

    # 板块轮动
    rotation = data.get("rotation")
    if rotation:
        lines.append(f"\n🔄 【板块轮动】")
        lines.append("-" * 40)
        if rotation.get("new"):
            lines.append(f"  🆕 新入热门: {', '.join(rotation['new'])}")
        if rotation.get("gone"):
            lines.append(f"  📤 退出热门: {', '.join(rotation['gone'])}")
        if rotation.get("hot"):
            for h in rotation["hot"]:
                arrow = "🔺" if h["change"] > 0 else "🔻"
                lines.append(f"  {arrow} {h['name']}: 今日 {h['today']:+.2f}% (变化 {h['change']:+.2f}%)")

    # 热搜
    if data.get("stock_hot"):
        lines.append(f"\n🔥 【微博A股热搜】")
        lines.append("-" * 40)
        for item in data["stock_hot"][:10]:
            hot_str = format_hot(item["hot"])
            reason = item.get("match_reason", "")
            lines.append(f"  #{item['keyword']}#  🔥{hot_str}  ({reason})")

    # 涨停
    zt_dt = data.get("zt_dt", {})
    if zt_dt.get("涨停"):
        lines.append(f"\n🟢 【涨停板 TOP10】")
        lines.append("-" * 40)
        for item in zt_dt["涨停"][:10]:
            lines.append(f"  {item['name']}({item['code']}) {item['change_pct']:+.1f}%  {item.get('reason', '')}")

    if zt_dt.get("跌停"):
        lines.append(f"\n🔴 【跌停板 TOP5】")
        lines.append("-" * 40)
        for item in zt_dt["跌停"][:5]:
            lines.append(f"  {item['name']}({item['code']}) {item['change_pct']:+.1f}%")

    # 板块
    if data.get("sectors"):
        lines.append(f"\n📊 【热门板块 TOP10】")
        lines.append("-" * 40)
        for s in data["sectors"][:10]:
            emoji = "🟢" if s["change_pct"] > 0 else "🔴"
            lines.append(f"  {emoji} {s['name']}: {s['change_pct']:+.2f}%  领涨: {s.get('leader', '')}")

    # 关联分析
    corr = data.get("correlation", {})
    if corr.get("insights"):
        lines.append(f"\n🔗 【热搜 vs 行情 关联分析】")
        lines.append("-" * 40)
        for insight in corr["insights"]:
            lines.append(f"  {insight}")

    # v2.1: 社区+新闻
    community = data.get("community", {})
    if community.get("guba"):
        lines.extend(v21.render_guba_text(community["guba"]).split("\n"))
    if community.get("news"):
        lines.extend(v21.render_news_text(community["news"]).split("\n"))

    # 历史对比
    snapshots = load_recent_snapshots(5)
    if len(snapshots) > 1:
        lines.append(f"\n📅 【历史数据对比】")
        lines.append("-" * 40)
        for snap in reversed(snapshots):
            zt_c = len(snap.get("zt_dt", {}).get("涨停", []))
            dt_c = len(snap.get("zt_dt", {}).get("跌停", []))
            sec_c = len(snap.get("sectors", []))
            nb_net = snap.get("northbound", {}).get("合计", {}).get("net", 0)
            nb_str = format_yi(nb_net) if nb_net else "N/A"
            lines.append(f"  📌 {snap['date']}: 涨停{zt_c}家 / 跌停{dt_c}家 / 板块{sec_c}个  北向: {nb_str}")

    lines.append("")
    return "\n".join(lines)


def render_community_section(data, args):
    """渲染社区+新闻部分"""
    if not HAS_V21:
        return ""
    community = data.get("community", {})
    lines = []
    if community.get("guba"):
        lines.append(v21.render_guba_text(community["guba"]))
    if community.get("news"):
        lines.append(v21.render_news_text(community["news"]))
    return "\n".join(lines)


def render_markdown(data, args):
    """Markdown 格式输出"""
    lines = []
    lines.append("# 📊 A股微博热搜分析报告 v2.1")
    lines.append(f"> ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if not is_trading_day():
        lines.append(f"> 🏖️  今日非交易日，数据为最近交易日 ({get_last_trading_date()})")
    lines.append("")

    stats = data.get("stats", {})
    if stats:
        total = stats.get("total", 0)
        up = stats.get("up", 0)
        down = stats.get("down", 0)
        lines.append(f"## 市场情绪")
        lines.append(f"| 上涨 | 下跌 | 平盘 | 涨跌比 |")
        lines.append(f"|------|------|------|--------|")
        lines.append(f"| {up} | {down} | {stats.get('flat', 0)} | {up}:{down} |")
        lines.append("")

    if data.get("market"):
        lines.append("## 大盘概览")
        lines.append("| 指数 | 收盘 | 涨跌幅 |")
        lines.append("|------|------|--------|")
        for idx in data["market"]:
            emoji = "🟢" if idx["change_pct"] > 0 else "🔴" if idx["change_pct"] < 0 else "⚪"
            lines.append(f"| {emoji} {idx['name']} | {idx['close']} | {idx['change_pct']:+.2f}% |")
        lines.append("")

    if data.get("stock_hot"):
        lines.append("## 🔥 微博A股热搜")
        for item in data["stock_hot"][:10]:
            lines.append(f"- **#{item['keyword']}#** 🔥{format_hot(item['hot'])} ({item.get('match_reason', '')})")
        lines.append("")

    if zt_dt := data.get("zt_dt", {}):
        if zt_dt.get("涨停"):
            lines.append("## 🟢 涨停板 TOP10")
            for item in zt_dt["涨停"][:10]:
                lines.append(f"- {item['name']}({item['code']}) {item['change_pct']:+.1f}% {item.get('reason', '')}")
            lines.append("")

    corr = data.get("correlation", {})
    if corr.get("insights"):
        lines.append("## 🔗 关联分析")
        for insight in corr["insights"]:
            lines.append(f"- {insight}")
        lines.append("")

    # v2.1: 社区+新闻 (Markdown)
    community = data.get("community", {})
    if community.get("guba"):
        lines.append("## 🗣️ 东方财富股吧热帖")
        for p in community["guba"][:10]:
            lines.append(f"- {p['title']}")
            meta = []
            if p.get("reads") and p["reads"] != "0":
                meta.append(f"👀{p['reads']}")
            if p.get("comments") and p["comments"] != "0":
                meta.append(f"💬{p['comments']}")
            if meta:
                lines.append(f"  {' | '.join(meta)}")
        lines.append("")
    if community.get("news"):
        lines.append("## 📰 财经新闻")
        for n in community["news"][:10]:
            lines.append(f"- {n['title']} [{n.get('source', '')}]({n.get('url', '')})")
        lines.append("")

    lines.append(f"\n---\n*Generated by A股分析 v{VERSION}*")
    return "\n".join(lines)


# ============================================================
# 6. 主函数
# ============================================================
def collect_data(args):
    """并行收集所有数据"""
    data = {}
    watchlist = args.watchlist.split(",") if args.watchlist else None

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}
        if not args.no_weibo:
            futures["weibo"] = executor.submit(fetch_weibo_hot)
        if not args.no_market:
            futures["market"] = executor.submit(fetch_market_overview)
            futures["trend"] = executor.submit(fetch_market_trend)
            futures["zt_dt"] = executor.submit(fetch_zt_dt)
            futures["sectors"] = executor.submit(fetch_hot_sectors)
            futures["northbound"] = executor.submit(fetch_northbound_flow)
            futures["stats"] = executor.submit(fetch_market_stats)

        for name, future in futures.items():
            try:
                data[name] = future.result(timeout=30)
            except Exception as e:
                log(f"⚠️  {name} 数据获取超时: {e}")
                data[name] = {} if name != "weibo" else []

    # 处理热搜
    if data.get("weibo"):
        data["stock_hot"] = filter_stock_keywords(data["weibo"], watchlist)
    else:
        data["stock_hot"] = []

    # 关联分析
    if data.get("stock_hot") and data.get("zt_dt"):
        data["correlation"] = analyze_correlation(data["stock_hot"], data["zt_dt"], data.get("sectors", []))
    else:
        data["correlation"] = {}

    # v2.1: 社区+新闻数据
    if HAS_V21 and (args.guba or args.news or args.all):
        stock_codes_for_guba = []
        if data.get("zt_dt", {}).get("涨停"):
            stock_codes_for_guba = [(i["code"], i["name"]) for i in data["zt_dt"]["涨停"][:3]]
        elif watchlist:
            stock_codes_for_guba = [(w, w) for w in watchlist[:3]]
        try:
            data["community"] = v21.fetch_community_data(stock_codes_for_guba)
        except Exception as e:
            log(f"⚠️  社区数据获取失败: {e}")
            data["community"] = {"guba": [], "news": []}

    # 板块轮动
    if not args.no_market:
        data["rotation"] = analyze_sector_rotation()

    # 保存快照
    if not args.no_market:
        save_snapshot(data)

    return data


def main():
    parser = argparse.ArgumentParser(description="A股微博热搜分析 v2.0", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--brief", action="store_true", help="精简模式：仅热搜 + 涨停")
    parser.add_argument("--trend", action="store_true", help="趋势模式：含大盘5日走势")
    parser.add_argument("--md", action="store_true", help="Markdown 格式输出")
    parser.add_argument("--no-weibo", action="store_true", help="跳过微博数据")
    parser.add_argument("--no-market", action="store_true", help="跳过行情数据")
    parser.add_argument("--stock", type=str, help="查询单只股票（代码）")
    parser.add_argument("--watchlist", type=str, help="自选股（逗号分隔）")
    parser.add_argument("--guba", action="store_true", help="显示东方财富股吧热帖")
    parser.add_argument("--news", action="store_true", help="显示财经新闻")
    parser.add_argument("--xueqiu", action="store_true", help="显示雪球讨论（需配置 token）")
    parser.add_argument("--all", action="store_true", help="显示全部数据（股吧+新闻）")
    parser.add_argument("--version", action="version", version=f"A股分析 v{VERSION}")
    args = parser.parse_args()

    # 单股查询
    if args.stock:
        info = fetch_single_stock(args.stock)
        if info:
            if args.json:
                print(json.dumps(info, ensure_ascii=False, indent=2))
            else:
                emoji = "🟢" if info["change_pct"] > 0 else "🔴" if info["change_pct"] < 0 else "⚪"
                print(f"\n{emoji} {info['name']} ({info['code']})")
                print(f"  最新价: {info['price']}  涨跌: {info['change_pct']:+.2f}% ({info['change_amt']:+.2f})")
                print(f"  今开: {info['open']}  最高: {info['high']}  最低: {info['low']}  昨收: {info['prev_close']}")
                print(f"  成交量: {info['volume']:.0f}  成交额: {info['turnover']:.0f}")
                if info.get("pe"):
                    print(f"  市盈率: {info['pe']}")
        else:
            print(f"❌ 未找到股票 {args.stock}")
        return

    data = collect_data(args)

    if args.json:
        # JSON 模式：去掉不可序列化的部分
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    elif args.md:
        print(render_markdown(data, args))
    elif args.brief:
        # 精简模式：热搜+涨停+社区
        brief_data = {
            "stock_hot": data.get("stock_hot", []),
            "zt_dt": data.get("zt_dt", {}),
            "community": data.get("community", {}),
        }
        print(render_text(brief_data, args))
    else:
        print(render_text(data, args))


if __name__ == "__main__":
    main()
