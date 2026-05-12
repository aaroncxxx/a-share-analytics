# 📊 A股微博热搜分析 v2.0

微博热搜 + A股行情 + 关联分析，一站式掌握市场热点。

> **关于作者** — 米粉，A股老韭菜，美股老韭菜，期货老韭菜，币圈老韭菜，被割多了，现在只看不玩，用MIMO做个Skill大家娱乐围观A股行情，好用记得回来点星星。⭐

## ✨ 特性

- 🔥 微博实时热搜抓取 + A股关键词筛选
- 📈 大盘指数（上证/深证/创业板）
- 🟢 涨停板 / 跌停板 TOP 列表
- 📊 热门板块排行
- 🔗 热搜 vs 行情关联分析
- 🌊 北向资金实时数据（沪股通/深股通）
- 📉 大盘5日趋势 + 迷你趋势图
- 🔄 板块轮动分析（对比近3天热门板块变化）
- 📱 Markdown 导出（方便分享到群/文档）

## 🚀 快速使用

```bash
# 完整分析
python3 scripts/analyzer.py

# 精简模式
python3 scripts/analyzer.py --brief

# 趋势模式
python3 scripts/analyzer.py --trend

# Markdown 导出
python3 scripts/analyzer.py --md

# 查询个股
python3 scripts/analyzer.py --stock 688256

# 自选股
python3 scripts/analyzer.py --watchlist "寒武纪,中芯国际"

# JSON 输出
python3 scripts/analyzer.py --json
```

## 📋 支持的场景

| 场景 | 命令示例 |
|------|---------|
| 今天行情怎么样 | `python3 scripts/analyzer.py` |
| 有什么热门股票 | `python3 scripts/analyzer.py --brief` |
| 北向资金流入多少 | `python3 scripts/analyzer.py`（看北向资金部分） |
| 大盘最近走势 | `python3 scripts/analyzer.py --trend` |
| 寒武纪怎么样 | `python3 scripts/analyzer.py --stock 688256` |
| 只看我关注的股票 | `python3 scripts/analyzer.py --watchlist "寒武纪,茅台"` |
| 分享报告到群 | `python3 scripts/analyzer.py --md` |

## 🆕 v2.0 更新

- **个股查询** — `--stock <代码>` 查单只股票
- **自选股** — `--watchlist` 过滤只看关注的
- **Markdown 导出** — `--md` 方便分享
- **市场情绪** — 涨跌比、涨跌家数
- **板块轮动** — 对比近3天热门板块变化
- **非交易日提示** — 周末/盘前自动提示
- **并行抓取** — ThreadPoolExecutor，速度更快
- **argparse** — 支持 `--help`

## 📦 依赖

- Python 3.8+
- `pip3 install akshare`

## 📁 文件结构

```
a-share-weibo-analytics/
├── SKILL.md              # OpenClaw Skill 定义
├── README.md             # 本文件
└── scripts/
    ├── analyzer.py       # 主脚本（v2.0）
    └── .cache/           # 本地快照缓存
```

## 📚 数据源

| 源 | 说明 | 需要 API Key |
|----|------|-------------|
| 微博热搜 | 公开 API | ❌ 不需要 |
| AKShare (东方财富) | A股行情 + 北向资金 | ❌ 不需要 |

## 🔧 自定义

- 修改 `analyzer.py` 中的 `SECTOR_KEYWORDS` 添加板块关键词
- 修改 `EXACT_KEYWORDS` 调整匹配规则

## 📝 版本历史

### v2.0.0 (2026-05-12)
- 🆕 个股查询、自选股、Markdown导出、市场情绪、板块轮动、非交易日提示
- 🔧 并行抓取、argparse、北向资金容错

### v1.1.0 (2026-05-01)
- 🌊 北向资金、5日趋势、关键词增强、快照缓存

### v1.0.0 (2026-05-01)
- 🚀 首发
