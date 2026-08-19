"""配置管理：pydantic 模型 + .env 环境变量加载。

敏感信息（Tushare token、iFinD 账号密码）一律从环境变量读取，
禁止硬编码进源码 —— 防止上传 GitHub 时泄露。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# 项目根目录（quant/）：config.py -> src/quant/config.py -> parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 加载 .env（不存在则静默跳过）
load_dotenv(PROJECT_ROOT / ".env")

CACHE_DIR = PROJECT_ROOT / "data" / "cache"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


class DataConfig(BaseModel):
    """数据源配置。"""

    provider: Literal["tushare", "akshare", "csv"] = "akshare"
    tushare_token: str = Field(default_factory=lambda: _env("TUSHARE_TOKEN"))
    csv_path: Path | None = None
    # 本地缓存：下载过的数据存 parquet，重复运行不重复拉取
    use_cache: bool = True
    cache_dir: Path = CACHE_DIR


class CostConfig(BaseModel):
    """A股交易成本模型（机构级必需）。

    买入成本 = 佣金(万2.5, 最低5元) + 过户费(0.001%)
    卖出成本 = 佣金(万2.5, 最低5元) + 印花税(0.05%, 2023-08 起减半) + 过户费(0.001%)
    """

    commission_rate: float = 0.00025          # 佣金率（万2.5）
    commission_min: float = 5.0               # 单笔最低佣金（元）
    stamp_tax: float = 0.0005                 # 印花税（卖出收取，单边）
    transfer_fee: float = 0.00001             # 过户费（双边，0.001%）
    slippage: float = 0.02                    # 每股滑点（元）


class BacktestConfig(BaseModel):
    """回测引擎配置。"""

    initial_capital: float = 20_000.0
    # 成交时点: "next_open" 用次日开盘价成交（保守、无前视偏差）
    #           "next_close" 用次日收盘价成交（常见简化）
    execution: Literal["next_open", "next_close"] = "next_open"
    # 基准代码（用于 alpha/beta/IR 计算），如 "000300.SH"
    benchmark_code: str | None = None
    lot_size: int = 100                        # A股一手 = 100股
    # 涨停价买入会被拒、跌停价卖出会被拒（模拟真实可成交性）
    respect_price_limit: bool = True
    limit_pct: float = 0.10                    # 主板 ±10%；创业板/科创板需按标的调整
    min_cash_reserve: float = 0.0             # 预留现金比例（0-1）


class RiskConfig(BaseModel):
    """风控配置 —— 实盘生存的第一道防线（回测与实盘共用同一套）。

    全部为可选，None/0 表示关闭对应规则。默认全关，保证与旧行为兼容；
    实盘建议至少开启 stop_loss_pct + max_position_pct。
    """

    # 1. 固定止损：收盘价 ≤ 持仓成本 × (1 - pct) → 次日卖出
    stop_loss_pct: float | None = None
    # 2. 移动止盈：收盘价 ≤ 持仓期最高价 × (1 - pct) → 次日卖出
    trailing_stop_pct: float | None = None
    # 3. 单笔仓位上限：买入资金 ≤ 当前可用资金 × pct（0-1，防满仓单票）
    max_position_pct: float = 1.0
    # 4. 当日亏损熔断：当日净值较前收跌幅 ≥ pct → 当日停止开新仓
    daily_loss_limit: float | None = None
    # 5a. 分级回撤熔断（推荐语义，Kimi 审查建议）：
    #      [(回撤阈值, 剩余仓位比例), ...]，按阈值升序。
    #      例 [(0.10, 0.5), (0.15, 0.0)] = 回撤 10% 仓位减半，回撤 15% 清仓停手（等人工复核）。
    #      回撤从历史峰值计算，创新高后自动恢复满仓。
    #      0/1 模型简化：降仓只影响后续新买入预算，不强制减半现有持仓。
    drawdown_stages: list[tuple[float, float]] = []
    # 5b. 简单回撤熔断（旧语义）：累计回撤 ≥ pct → 清仓并永久停手
    drawdown_limit: float | None = None


class Config(BaseModel):
    """全局配置。"""

    data: DataConfig = Field(default_factory=DataConfig)
    costs: CostConfig = Field(default_factory=CostConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    @field_validator("backtest")
    @classmethod
    def _check_capital(cls, v: BacktestConfig) -> BacktestConfig:
        if v.initial_capital <= 0:
            raise ValueError("initial_capital 必须为正数")
        return v

    @classmethod
    def load(cls, env_file: str | os.PathLike | None = None) -> "Config":
        """从 .env 加载配置。"""
        if env_file is not None:
            load_dotenv(env_file, override=True)
        return cls()
