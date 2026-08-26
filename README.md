# quant — A股量化研究框架（v1）

机构级 A股量化研究/回测框架：无前视偏差引擎、完整 A股 约束、16+ 绩效指标、因子 IC/IR 验证、walk-forward 样本外验证。

**v1 核心策略**：五因子选股组合（低换手 / 低PB / 高股息 / E/P / 低PS），Top8 双周调仓 + 行业≤3 约束（回测 2023-2026 全区间 +35.02%，夏普 0.98；walk-forward 2023 +14.09% / 2024 +14.05% / 2025-26 -0.71%——**近期段未过样本外门，实盘/加仓需谨慎**）。

> ⚠️ **免责声明**：本项目为量化研究学习框架，不构成任何投资建议。回测收益不代表未来表现，因子存在失效风险（2025-26 样本外已为负）。实盘决策风险自负。

## 特性

| 类别 | 内容 |
|---|---|
| 无前视 | 信号 T 日收盘产生 → **T+1 成交**（开盘价执行）；财报/情绪数据按公告日 T+1 对齐 |
| A股约束 | 涨跌停（涨停买不进/跌停卖不出）、停牌、100 股整手、T+1 |
| 成本模型 | 佣金(万2.5, 最低5元) + 印花税(卖出0.05%) + 过户费(0.001%) + 滑点 |
| 指标套件 | 16+ 项：夏普/索提诺/卡玛/最大回撤/最长回撤/胜率/盈亏比/换手/alpha/beta/IR |
| 因子验证 | RankIC / ICIR / t 值 / 行业+市值中性化 / 十分组单调性 / 相关矩阵（防重复下注） |
| 过拟合防护 | walk-forward 样本外分段验证；模拟盘双组合并行（主/影子） |
| 工程化 | pytest 123 用例、`.env` 配置（密钥不入库）、日志化、脚本-库分层 |

## 架构

```
src/quant/
├── data/          # 数据源（tushare/akshare/csv）+ 面板 + 质量检查
│   ├── financial.py   # 财务面板（akshare 业绩报表，公告日 T+1 无前视）
│   └── sentiment.py   # 情绪面板（两融/龙虎榜，T+1 无前视，含陈旧值清洗）
├── backtest/      # 回测引擎（T+1+约束迭代）、成本、16+ 指标
├── strategies/    # 技术策略（sma/macd/boll/rsi/breakout）
├── factors/       # 因子处理（winsorize/zscore/E-P口径/复权收益）+ IC 检验
│   └── emotion.py     # 情绪因子构造（融资余额变化率/龙虎榜上榜，反向指标）
├── portfolio/     # 多标的组合引擎（周频再平衡、权重合成、行业约束）
└── research/      # walk-forward、归因、通用因子面板验证
scripts/           # CLI 编排（核心逻辑全部在 src/ 库内）
tests/             # pytest 123 用例（含无前视/停牌/风控死锁回归）
```

## 快速开始

```bash
# 环境（需要 Python 3.11+）
uv venv .venv && uv pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
cp .env.example .env   # 填写 TUSHARE_TOKEN（可选，akshare 免 token 可跑）

# 测试
.venv\Scripts\python.exe -m pytest

# 单标的回测（MACD 示例）
.venv\Scripts\python.exe scripts\run_backtest.py --symbol 600744.SH --strategy macd

# 因子选股组合回测（v1 五因子）
.venv\Scripts\python.exe scripts\run_factor_portfolio.py --top-n 8 --max-per-industry 3 --rebalance biweekly

# 因子面板验证（财务/情绪因子 IC，正式复跑链路）
.venv\Scripts\python.exe scripts\validate_factor_panels.py --kind financial --horizons 1 4 13
.venv\Scripts\python.exe scripts\validate_factor_panels.py --kind sentiment --horizons 1 4
```

## 数据源（免费优先）

| 数据源 | 费用 | 用途 |
|---|---|---|
| tushare | 2000+ 积分 | 主力：daily_basic（PE/PB/PS/市值/换手/股息率）+ adj_factor 复权因子 |
| akshare | 免费免 token | 财务面板（业绩报表）、情绪面板（两融/龙虎榜）、备份行情 |
| csv | 本地 | 存量数据 |

## 因子验证结论（2023-2026 周频截面）

| 因子 | 中性化 ICIR | 状态 |
|---|---|---|
| 低换手 | 0.887 | ✅ v1 核心（0.40） |
| 低PB | 0.523 | ✅ v1（0.20） |
| 高股息 | 0.527 | ✅ v1（0.15） |
| E/P | 0.485 | ✅ v1（0.10） |
| 低PS | 0.371 | ✅ v1（0.10） |
| 净利增速 | 0.323（4周） | ⏳ v2 候选（组合层未验证） |
| 质量/成长/动量 | <0.2 或负 | ❌ 截面无效（动量 A股 为负 alpha） |
| 情绪（融资/龙虎榜反向） | 截面显著但组合层拖累 | ❌ 不进组合（IC 正≠组合有效） |

## 已知边界（诚实声明）

- **Top8 集中效应**：v1 的 +35% 是 Top8 深度小组合（含集中持有成分）；Top20 分散后 ≈0.15%（alpha 不可规模化）
- **walk-forward 门未过**：2025-26 样本外 -0.71%，策略近期失效——模拟盘盈利 ≠ 加仓依据
- 数据仅 2023-2026（约 3.6 年），历史短、参数有拟合风险

## License

MIT
