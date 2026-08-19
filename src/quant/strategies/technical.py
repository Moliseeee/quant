"""技术指标策略（迁移自 Kimi 原版，修复副作用与边沿问题）。

全部实现只读 df：中间计算用局部变量，不往 df 上写列。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class SMAStrategy(Strategy):
    """双均线：短期均线 > 长期均线 → 持仓，否则空仓。"""

    name = "sma"

    def __init__(self, fast: int = 5, slow: int = 20):
        self.params = {"fast": fast, "slow": slow}
        self.fast, self.slow = fast, slow

    def generate_signal(self, df: pd.DataFrame) -> pd.Series:
        fast_ma = df["close"].rolling(self.fast).mean()
        slow_ma = df["close"].rolling(self.slow).mean()
        sig = (fast_ma > slow_ma).astype(float)
        return sig.fillna(0.0)


class MACDStrategy(Strategy):
    """MACD：DIF > DEA → 持仓。"""

    name = "macd"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.params = {"fast": fast, "slow": slow, "signal": signal}
        self.fast, self.slow, self.signal = fast, slow, signal

    def generate_signal(self, df: pd.DataFrame) -> pd.Series:
        ema_fast = df["close"].ewm(span=self.fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=self.signal, adjust=False).mean()
        sig = (dif > dea).astype(float)
        return sig.fillna(0.0)


class BollingerStrategy(Strategy):
    """布林带均值回归：跌破下轨持仓，突破上轨空仓，中间维持原状态。"""

    name = "boll"

    def __init__(self, window: int = 20, num_std: float = 2.0):
        self.params = {"window": window, "num_std": num_std}
        self.window, self.num_std = window, num_std

    def generate_signal(self, df: pd.DataFrame) -> pd.Series:
        mid = df["close"].rolling(self.window).mean()
        std = df["close"].rolling(self.window).std()
        upper = mid + self.num_std * std
        lower = mid - self.num_std * std
        sig = pd.Series(0.0, index=df.index)
        sig[df["close"] < lower] = 1.0
        sig[df["close"] > upper] = 0.0
        return sig.ffill().fillna(0.0)


class RSIStrategy(Strategy):
    """RSI 超买超卖：RSI < buy_th 持仓，> sell_th 空仓，中间维持。"""

    name = "rsi"

    def __init__(self, window: int = 14, buy_th: float = 30, sell_th: float = 70):
        self.params = {"window": window, "buy_th": buy_th, "sell_th": sell_th}
        self.window, self.buy_th, self.sell_th = window, buy_th, sell_th

    def generate_signal(self, df: pd.DataFrame) -> pd.Series:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(self.window).mean()
        avg_loss = loss.rolling(self.window).mean()
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100 - 100 / (1 + rs)
        sig = pd.Series(0.0, index=df.index)
        sig[rsi < self.buy_th] = 1.0
        sig[rsi > self.sell_th] = 0.0
        return sig.ffill().fillna(0.0)


class DonchianStrategy(Strategy):
    """唐奇安通道突破：收盘突破 N 日高点持仓，跌破 N 日低点空仓。"""

    name = "breakout"

    def __init__(self, window: int = 20):
        self.params = {"window": window}
        self.window = window

    def generate_signal(self, df: pd.DataFrame) -> pd.Series:
        high_n = df["high"].rolling(self.window).max().shift(1)
        low_n = df["low"].rolling(self.window).min().shift(1)
        sig = pd.Series(0.0, index=df.index)
        sig[df["close"] > high_n] = 1.0
        sig[df["close"] < low_n] = 0.0
        return sig.ffill().fillna(0.0)


STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "sma": SMAStrategy,
    "macd": MACDStrategy,
    "boll": BollingerStrategy,
    "rsi": RSIStrategy,
    "breakout": DonchianStrategy,
}


def get_strategy(name: str, **params) -> Strategy:
    """按名称实例化策略。"""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"未知策略 {name}，可选: {list(STRATEGY_REGISTRY)}")
    return STRATEGY_REGISTRY[name](**params)
