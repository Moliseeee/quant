# quant — A股量化研究框架（机构级重构版）

> 由 `桌面/量化/` 下的 Kimi 脚本重构而来。旧脚本保持原样未动，本目录是机构级工程化版本。

## 与原版相比，修复了什么

| 问题 | 原版（Kimi） | 本版 |
|---|---|---|
| 前视偏差 | 当日收盘价算信号又当日成交 | **T+1 成交**（信号 T 日产生，T+1 开盘价执行） |
| 涨跌停 | 无 | 涨停买不进/跌停卖不出，次日继续尝试 |
| 停牌 | 无 | 停牌日无法交易 |
| 交易成本 | 仅佣金+滑点 | 佣金(最低5元)+印花税+过户费+滑点 |
| 整手约束 | 无 | 买入 100 股整手 |
| 胜率配对 | 按索引硬配（会错位） | 买卖配对计算真实盈亏 |
| 绩效指标 | 4 个 | **16+ 个**：夏普/索提诺/卡玛/盈亏比/换手/最长回撤/alpha/beta/IR… |
| 因子 | 无验证、方向矛盾 | **IC/IR/分层检验 + 行业市值中性化 + winsorize** |
| 过拟合防护 | 无 | **walk-forward 样本外验证** |
| 敏感信息 | iFinD 密码明文 | 全部走 `.env`（`.gitignore` 排除） |
| 工程化 | 无测试无依赖管理 | pytest 27 用例 + pyproject/requirements |

## 快速开始

```bash
cd quant
uv venv .venv && uv pip install -e ".[dev]"     # 或 pip install -e ".[dev]"
cp .env.example .env                             # 填入 TUSHARE_TOKEN
.venv\Scripts\python.exe scripts\run_backtest.py --symbol 600744.SH --strategy macd
.venv\Scripts\python.exe scripts\run_backtest.py --symbol 600744.SH --all   # 全策略对比
.venv\Scripts\python.exe -m pytest               # 跑测试
```

### 风控参数（实盘生存第一道防线）

```bash
# 止损 8% + 单票仓位 80% + 累计回撤熔断 15%
.venv\Scripts\python.exe scripts\run_backtest.py --symbol 600744.SH --strategy macd \
    --stop-loss 0.08 --max-position 0.8 --drawdown 0.15
```

| 参数 | 说明 |
|---|---|
| `--stop-loss` | 固定止损：收盘破成本×N% 次日离场，离场后需新买入信号才进场 |
| `--trailing-stop` | 移动止盈：收盘破持仓峰值×N% 锁利离场 |
| `--max-position` | 单笔买入资金上限（0-1），防满仓单票 |
| `--daily-loss` | 当日亏损熔断：单日亏 N% 次日禁止开新仓 |
| `--drawdown` | 累计回撤熔断：亏 N% 清仓并永久停手 |

实测（600744.SH + MACD, 2023~2026）：
- 无风控：总收益 -26%，**最大回撤 53%**
- 有风控：总收益 -20%，**最大回撤 20%**（止损/熔断把灾难性回撤压成可控回撤）

## 模块结构

```
src/quant/
├── config.py          # pydantic 配置，敏感信息走环境变量
├── data/              # DataFeed 抽象（Tushare/CSV）+ 本地缓存 + 数据质检
├── backtest/
│   ├── engine.py      # 向量化引擎：T+1 成交、涨跌停/停牌/整手约束、风控钩子
│   ├── costs.py       # A股成本模型（佣金/印花税/过户费/滑点）
│   └── metrics.py     # 16+ 绩效指标
├── strategies/        # 策略接口 + 5 个技术策略（sma/macd/boll/rsi/breakout）
├── factors/           # winsorize/中性化/标准化 + RankIC/ICIR/分层检验
└── research/          # walk-forward 样本外验证（防过拟合）
```

## 使用策略（建议工作流）

1. **因子研究先行**：用 `factors/` 的 IC/IR 检验候选因子有没有预测力
   （经验阈值：`|mean IC| > 0.02` 且 `ICIR > 0.3` 且 `t > 2`）
2. **回测**：引擎跑出完整指标，注意真实成本下收益会显著低于"乐观回测"
3. **walk-forward**：训练段选参 → 样本外验证。**样本外业绩才是真实业绩**
4. 全部验证通过，再考虑发布/实盘

## 已知限制（Roadmap）

- 0/1 全仓模型；组合级（多标的、权重分配、再平衡）引擎待扩展
- 涨跌停用"开盘价即涨停/跌停"近似，未处理盘中打开
- 未建模 T+1 交易制度下的"当日买入当日不可卖"（0/1 模型天然满足）
- 创业板/科创板 20% 涨跌幅需按标的设置 `limit_pct`
