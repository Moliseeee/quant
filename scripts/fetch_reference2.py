"""补拉 qlib exchange/position + backtrader sizer（带重试）。"""
import base64
import time
from pathlib import Path

import requests

REF = Path(__file__).resolve().parent / "reference"
REF.mkdir(exist_ok=True)

TARGETS = [
    ("microsoft/qlib", "qlib/backtest/exchange.py", "qlib_exchange.py"),
    ("microsoft/qlib", "qlib/backtest/position.py", "qlib_position.py"),
    ("mementum/backtrader", "backtrader/sizer.py", "backtrader_sizers.py"),
]

H = {"Accept": "application/vnd.github+json", "User-Agent": "hermes-research"}

for repo, path, fname in TARGETS:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    for attempt in range(4):
        try:
            r = requests.get(url, headers=H, timeout=40)
            if r.status_code == 200:
                data = r.json()
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                (REF / fname).write_text(content, encoding="utf-8")
                print(f"[OK]   {fname:30s} {len(content.splitlines()):5d} 行  {data['size']} bytes")
                break
            print(f"[{attempt}] {repo}/{path}: HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            print(f"[{attempt}] {repo}/{path}: {type(e).__name__}")
        time.sleep(3 * (attempt + 1))
    else:
        print(f"[FAIL] {repo}/{path} 重试 4 次仍失败")
