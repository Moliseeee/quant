"""脚本 smoke 测试：验证所有 CLI 脚本可导入（模块级代码 + import 链有效）。

脚本不在 pytest testpaths 内，通过 importlib 显式加载，捕获语法/依赖错误。
不执行 main()（模块 __name__ != "__main__"）。
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = [
    "run_factor_portfolio.py",
    "factor_attribution.py",
    "validate_factors.py",
    "fetch_factor_data.py",
    "fetch_stock_basic.py",
    "check_survivorship.py",
    "run_backtest.py",
    "candidate_factors.py",
    "market_turnover_analysis.py",
    "run_regime_portfolio.py",
]


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_importable(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / name
    assert path.exists(), f"脚本不存在: {name}"
    spec = importlib.util.spec_from_file_location(name.replace(".py", "_mod"), path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    # 模块级代码（import quant.*、常量定义）会执行；main() 因 __name__ 非 __main__ 不触发
    spec.loader.exec_module(mod)
    assert mod is not None
