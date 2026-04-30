---
name: CNY RMB A股 China A shares Stock
version: 1.0.0
description: >
  CNY RMB A股热搜分析 - China A Shares Stock Skill
  微博热搜 + A股行情 + 关联分析，一站式掌握市场热点。
  关键词：A股, 大A, A-shares, China A, Onshore, 涨停, 跌停, 热搜
applyTo: "**"
---

# CNY RMB A股热搜分析
# China A Shares Stock Skill

微博热搜 + A股行情 + 关联分析，一站式掌握市场热点。

> **关于作者** — 米粉，A股老韭菜，美股老韭菜，期货老韭菜，币圈老韭菜，被割多了，现在只看不玩，用MIMO做个Skill大家娱乐围观A股行情，好用记得回来点星星。⭐
>
> Mi Fan 🍚 | Rekt veteran: A-shares, US stocks, futures, crypto 📉 | Now just watching 👀 | Built with MIMO for fun | Star if you like it ⭐
>
> **功能清单：**
> - ✅ 微博实时热搜抓取 + A股关键词筛选
> - ✅ 大盘指数（上证/深证/创业板）
> - ✅ 涨停板 / 跌停板 TOP 列表
> - ✅ 热门板块排行
> - ✅ 热搜 vs 行情关联分析
> - ✅ `--json` 结构化输出
> - ✅ `--brief` 精简模式（仅热搜 + 涨停）

## When to Use

| Situation | Use this skill? |
|---|---|
| 用户说"A股分析" / "股市热搜" / "今天行情" | ✅ Yes |
| 用户问"今天有什么热门股票" | ✅ Yes |
| 用户想看微博上大家在讨论什么股票 | ✅ Yes |
| 盘后复盘 / 盘中监控 | ✅ Yes |

## Usage

```bash
python3 "{baseDir}/scripts/analyzer.py" [options]
```

### Options

| Flag | Description |
|------|-------------|
| `--json` | JSON 格式输出 |
| `--brief` | 精简模式：仅热搜 + 涨停 |
| `--no-weibo` | 跳过微博数据（只看行情） |
| `--no-market` | 跳过行情数据（只看热搜） |

### Examples

```bash
# 完整分析
python3 "{baseDir}/scripts/analyzer.py"

# 精简模式
python3 "{baseDir}/scripts/analyzer.py" --brief

# JSON 输出
python3 "{baseDir}/scripts/analyzer.py" --json

# 只看行情
python3 "{baseDir}/scripts/analyzer.py" --no-weibo

# 只看热搜
python3 "{baseDir}/scripts/analyzer.py" --no-market
```

## 输出格式

```
📊 A股微博热搜分析报告
⏰ 2026-05-01 09:30
==================================================

📈 【大盘概览】
----------------------------------------
  🟢 上证指数: 3288.41 (+0.52%)
  🟢 深证成指: 10245.67 (+0.38%)
  🔴 创业板指: 2045.12 (-0.15%)

🔥 【微博A股热搜】
----------------------------------------
  #寒武纪涨停#  🔥17.5万  (包含「涨停」)
  #A股牛市来了#  🔥12.3万  (包含「A股」「牛市」)
  #北向资金抄底#  🔥8.7万  (包含「北向资金」)

🟢 【涨停板 TOP10】
----------------------------------------
  寒武纪(688256) +20.0%  AI芯片
  中科曙光(603019) +10.0%  算力
  ...

🔴 【跌停板 TOP10】
----------------------------------------
  ...

📊 【热门板块 TOP10】
----------------------------------------
  🟢 AI芯片: +5.23%  领涨: 寒武纪
  🟢 算力: +3.45%  领涨: 中科曙光
  ...

🔗 【关联分析】
----------------------------------------
  💬 热搜提及个股: 寒武纪, 中科曙光
  🔥 以下股票同时出现在微博热搜和涨停板: 寒武纪
  📊 热搜板块关键词: AI芯片, 算力
```

## 数据源

| 源 | 说明 | 需要 API Key |
|----|------|-------------|
| 微博热搜 | 公开 API | ❌ 不需要 |
| AKShare (东方财富) | A股行情 | ❌ 不需要 |

## 依赖

- Python 3.8+
- akshare (`pip3 install akshare`)

## 版本历史

### v1.0.0 (2026-05-01)

- 🚀 首发：微博热搜抓取 + A股行情 + 关联分析
- 📈 大盘指数：上证/深证/创业板
- 🟢 涨停板/跌停板 TOP 列表
- 📊 热门板块排行
- 🔗 热搜 vs 行情关联分析
- 📱 支持 `--json` / `--brief` / `--no-weibo` / `--no-market`
