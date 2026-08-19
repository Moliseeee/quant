"""批量下载 GitHub 参考源码到 reference/（走 api.github.com，代理友好）。"""
import base64
import json
from pathlib import Path

import requests

REF = Path(__file__).resolve().parent / "reference"
REF.mkdir(exist_ok=True)

# (仓库, 路径, 本地文件名)
TARGETS = [
    ("vnpy/vnpy_riskmanager", "vnpy_riskmanager/engine.py", "vnpy_riskmanager_engine.py"),
    ("vnpy/vnpy_riskmanager", "vnpy_riskmanager/rules/active_order_rule.py", "vnpy_rule_active_order.py"),
    ("vnpy/vnpy_riskmanager", "vnpy_riskmanager/rules/daily_limit_rule.py", "vnpy_rule_daily_limit.py"),
    ("vnpy/vnpy_riskmanager", "vnpy_riskmanager/rules/duplicate_order_rule.py", "vnpy_rule_duplicate.py"),
    ("vnpy/vnpy_riskmanager", "vnpy_riskmanager/rules/order_size_rule.py", "vnpy_rule_order_size.py"),
    ("vnpy/vnpy_riskmanager", "vnpy_riskmanager/rules/order_validity_rule.py", "vnpy_rule_validity.py"),
    ("microsoft/qlib", "qlib/backtest/exchange.py", "qlib_exchange.py"),
    ("microsoft/qlib", "qlib/backtest/position.py", "qlib_position.py"),
    ("mementum/backtrader", "backtrader/sizers.py", "backtrader_sizers.py"),
    ("quantopian/alphalens", "alphalens/performance.py", "alphalens_performance.py"),
]

H = {"Accept": "application/vnd.github+json", "User-Agent": "hermes-research"}

for repo, path, fname in TARGETS:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        r = requests.get(url, headers=H, timeout=30)
        if r.status_code != 200:
            print(f"[SKIP] {repo}/{path}: HTTP {r.status_code}")
            continue
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        (REF / fname).write_text(content, encoding="utf-8")
        print(f"[OK]   {fname:32s} {len(content.splitlines()):4d} 行  {data['size']} bytes")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {repo}/{path}: {e}")

print("\n完成，文件保存在:", REF)
