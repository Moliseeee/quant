# quant 架构说明

> 本文件说明当前 `quant/` 主仓库内部架构。原则：核心逻辑进 `src/quant/`，脚本只做编排；内部会审材料留在 `会审对话/`，不进入公开发布内容。

## 一、代码架构

```text
quant/
├── src/quant/                 # 核心 Python 包
│   ├── config.py              # 配置读取；.env 不入库
│   ├── data/                  # 数据源与面板构造
│   │   ├── base.py            # DataFeed 抽象
│   │   ├── tushare_feed.py    # Tushare 行情/因子原料
│   │   ├── akshare_feed.py    # AKShare 免费备份源
│   │   ├── csv_feed.py        # 本地 CSV 数据源
│   │   ├── panels.py          # 周频因子面板统一加载
│   │   ├── financial.py       # 财务面板：公告日 T+1 无前视
│   │   ├── sentiment.py       # 情绪面板：两融/龙虎榜，含陈旧值清洗
│   │   └── quality.py         # 停牌、涨跌停、异常数据检查
│   ├── backtest/              # 单标的/信号回测层
│   │   ├── engine.py          # T+1 成交、A股交易约束
│   │   ├── costs.py           # 佣金、印花税、过户费、滑点
│   │   └── metrics.py         # 年化、夏普、回撤等指标；频率自动推断
│   ├── factors/               # 因子处理与 IC 验证
│   │   ├── processing.py      # winsorize、zscore、E/P、复权远期收益
│   │   ├── ic.py              # RankIC / ICIR / t 值
│   │   └── emotion.py         # 情绪因子构造
│   ├── portfolio/             # 多标的组合层
│   │   ├── engine.py          # 权重再平衡、停牌语义、组合记账
│   │   └── scoring.py         # 多因子合成打分、TopN、行业上限
│   ├── research/              # 研究/归因工具
│   │   ├── walk_forward.py    # 样本外 walk-forward
│   │   ├── attribution.py     # 分段 IC、失效归因
│   │   └── panel_validate.py  # 通用宽面板因子验证
│   └── strategies/            # 技术指标策略示例
├── scripts/                   # CLI 入口，只做编排，不堆核心逻辑
├── tests/                     # pytest 回归测试
├── reference/                 # 参考实现与跨平台策略
│   └── joinquant/             # 聚宽在线 IDE 版策略与报告
├── data/                      # 数据缓存与输出
│   ├── cache/                 # 本地缓存，不上传
│   └── output/                # 报告输出；md 可保留，原始产物谨慎处理
├── 会审对话/                  # 内部审查、方案、临时工具、报告；不上传 GitHub
└── README.md                  # 对外说明
```

## 二、当前研究主线

1. **v1 五因子**：低换手 / 低 PB / 高股息 / E-P / 低 PS。
2. **聚宽交叉验证**：`reference/joinquant/v1_five_factor.py` 已用于 2020-2026 长周期验证。
3. **v2 因子库增强候选**：`reference/joinquant/v2_factor_library.py`，从聚宽 `jqfactor` 因子库加入现金流、质量、低波、52 周位置等维度。
4. **内部验证材料**：统一放 `会审对话/`，包括字典校验、候选裁决、Codex/Kimi 回执。

## 三、目录纪律

- 新核心逻辑：放 `src/quant/` 并写 pytest。
- 新命令行入口：放 `scripts/`；脚本不应有大量业务逻辑。
- 聚宽在线 IDE 代码：放 `reference/joinquant/`。
- 内部方案/会审/临时脚本：放 `会审对话/`，不上传 GitHub。
- 旧方案、模拟盘记录、资金风控文档：已归入 `会审对话/00_根目录旧文档/`。
- 聚宽因子海选临时工具：已归入 `会审对话/聚宽因子海选工具/`。

## 四、验证入口

```powershell
Set-Location -LiteralPath 'C:\Users\范滕\Desktop\量化\quant'
.venv\Scripts\python.exe -m pytest
python -m py_compile reference\joinquant\v2_factor_library.py
```

## 五、发布边界

公开发布前必须检查：

- 不包含 `.env`、token、密码；
- 不包含 `会审对话/`、模拟盘、学费/资金安排等内部文档；
- README、release、description 不使用自夸表述；
- 推送后用 GitHub API 校验远端 tree，无内部文档泄漏。
