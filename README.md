# quant — A股量化研究框架

> 并非机构级 A股量化研究/回测框架：无前视偏差引擎、完整 A股 约束、16+ 绩效指标、因子 IC/IR 验证、walk-forward 样本外验证。
> 从零构建的个人量化研究项目，代码与结论全部公开，欢迎交流指正。

**v1 核心策略**：五因子选股组合（低换手 0.40 / 低PB 0.20 / 高股息 0.15 / E-P 0.10 / 低PS 0.10），Top8 双周调仓 + 行业≤3 约束。

| 验证渠道 | 区间 | 收益 | 年化 | 最大回撤 | 夏普 |
|---|---|---|---|---|---|
| 本地回测 | 2023-01 ~ 2026-08 | +35.02% | +8.71% | -9.0% | 0.98 |
| **聚宽平台复现** | **2020-01 ~ 2026-08** | **+35.33%** | **+4.66%** | **-26.81%** | 0.278 |

聚宽版覆盖 6.6 年完整周期（本地数据仅 2023 起），两实现交叉验证一致。⚠️ 2025-26 样本外两实现均走弱（本地 -0.71% / 聚宽 2026 -10.30%）——**加仓红线维持不变**。详见 [`reference/joinquant/backtest_report.md`](reference/joinquant/backtest_report.md)。

> ⚠️ **免责声明**：本项目为量化研究学习框架，不构成任何投资建议。回测收益不代表未来表现，因子存在失效风险。实盘决策风险自负。

---

## 特性

| 类别 | 内容 |
|---|---|
| **无前视** | 信号 T 日收盘产生 → T+1 成交；财报/情绪数据按公告日 T+1 对齐（`merge_asof` 防未来函数） |
| **A股约束** | 涨跌停（涨停买不进/跌停卖不出）、停牌、100 股整手、T+1 |
| **成本模型** | 佣金(万2.5, 最低5元) + 印花税(卖出0.05%) + 过户费(0.001%) + 滑点 |
| **绩效套件** | 16+ 项：夏普/索提诺/卡玛/最大回撤/胜率/盈亏比/换手/alpha/beta/IR |
| **因子验证** | RankIC / ICIR / t 值 / 行业+市值中性化 / 分年 / 相关矩阵（防重复下注） |
| **过拟合防护** | walk-forward 样本外分段验证；模拟盘双组合并行 |
| **工程化** | pytest 123 用例、`.env` 密钥管理、脚本-库分层、GitHub Actions 就绪 |

## 快速开始

```bash
# 环境（Python 3.11+）
uv venv .venv && uv pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
cp .env.example .env        # 可选：填 TUSHARE_TOKEN（akshare 免 token 可跑）

# 跑测试
.venv\Scripts\python.exe -m pytest

# 单标的回测（MACD 示例）
.venv\Scripts\python.exe scripts\run_backtest.py --symbol 600744.SH --strategy macd

# v1 五因子组合回测（Top8 + 双周 + 行业≤3）
.venv\Scripts\python.exe scripts\run_factor_portfolio.py --top-n 8 --max-per-industry 3 --rebalance biweekly

# 因子面板验证（正式复跑链路）
.venv\Scripts\python.exe scripts\validate_factor_panels.py --kind financial --horizons 1 4 13
.venv\Scripts\python.exe scripts\validate_factor_panels.py --kind sentiment --horizons 1 4
```

## 项目结构

```
quant/
├── src/quant/               # 核心库（逻辑全部在库内，脚本只做编排）
│   ├── data/                # 数据源（tushare/akshare/csv）+ 面板 + 质量检查
│   │   ├── financial.py     #   财务面板（公告日 T+1 无前视）
│   │   └── sentiment.py     #   情绪面板（两融/龙虎榜，含陈旧值清洗）
│   ├── backtest/            # 回测引擎（T+1+约束迭代）、成本、指标
│   ├── factors/             # 因子处理（winsorize/zscore/中性化）+ IC 检验
│   ├── portfolio/           # 组合引擎（周频再平衡、权重合成、行业约束）
│   └── research/            # walk-forward、归因、通用因子面板验证
├── scripts/                 # CLI 入口（fetch/backtest/validate/paper_select）
├── tests/                   # pytest 123 用例（无前视/停牌/风控死锁回归）
├── reference/               # 参考实现
│   ├── joinquant/           #   ★ 聚宽在线平台复现（v1 五因子 + 回测报告）
│   ├── qlib_*.py            #   Qlib 参考
│   ├── vnpy_*.py            #   vn.py 参考
│   └── backtrader_sizers.py #   Backtrader 参考
├── data/                    # 数据缓存（gitignore）与输出
├── ARCHITECTURE.md          # 仓库内部架构与目录纪律
├── pyproject.toml           # 依赖与打包（editable install）
├── .env.example             # 密钥模板（.env 不入库）
└── LICENSE                  # MIT
```

## 数据源（免费优先）

| 数据源 | 费用 | 用途 |
|---|---|---|
| tushare | 2000+ 积分 | 主力：daily_basic（PE/PB/PS/市值/换手/股息率）+ adj_factor 复权 |
| akshare | 免费免 token | 财务面板（业绩报表）、情绪面板（两融/龙虎榜）、备份行情 |
| 聚宽（在线回测） | 免费 | 长周期交叉验证（2020 起全量数据，不占 JQData 额度） |

## 因子验证结论（2023-2026 周频截面，中性化 ICIR）

| 因子 | ICIR | 状态 |
|---|---|---|
| 低换手 | 0.887 | ✅ v1 核心（0.40） |
| 高股息 | 0.527 | ✅ v1（0.15） |
| 低PB | 0.523 | ✅ v1（0.20） |
| E/P | 0.485 | ✅ v1（0.10） |
| 低PS | 0.371 | ✅ v1（0.10） |
| 净利增速 | 0.323（4周） | ⏳ 截面过门槛，组合层拖累（v2 候选已关闭） |
| 情绪（融资/龙虎榜反向） | 截面显著 | ❌ 组合层拖累（IC 正≠组合有效） |
| 质量/成长/动量 | <0.2 或负 | ❌ 截面无效（A股 动量为负 alpha） |

## 已知边界（诚实声明）

1. **Top8 集中效应**：+35% 是 Top8 深度小组合（含集中持有成分）；Top20 分散后 ≈0.15%，alpha 不可规模化
2. **风格依赖强**：聚宽 6.6 年周期显示 2024 红利大年 +40% 撑起总收益，2020/2026 风格逆风年亏 10-19%
3. **walk-forward 门未过**：2025-26 样本外为负——模拟盘盈利 ≠ 加仓依据
4. **数据短**：本地仅 2023-2026（3.6 年），参数有拟合风险（聚宽版补足长周期验证）

## License

[MIT](LICENSE)
