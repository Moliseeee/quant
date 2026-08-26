# Walk-Forward 重跑确认（17 截面补齐后）

> 2026-08-26 | Codex 审查遗留待办①：17 个早期截面补 adj_factor 后，历史复权收益研究需重跑确认
> 配置：五因子 Top8 + 双周调仓 + 行业≤3（模拟盘/实盘口径），run_factor_portfolio.py --start/--end 按年切段

## 结果对比

| 分段 | 修复前（2026-08 记录） | 修复后（本次重跑） | 差异 | 说明 |
|---|---|---|---|---|
| 2023 | +14.09% / 夏普1.87 | **+14.09% / 1.90** | 0.00pt | 逐位一致，2023 段无缺列截面影响 |
| 2024 | +10.67% / 1.02 | **+14.05% / 1.20** | **+3.38pt** | 2024 上半年 5 个缺 adj_factor 截面（20240315/22/29、20240430、20240517）补齐后复权收益准确，**之前被低估** |
| 2025-26 | -0.61% / -0.05 | **-0.71% / -0.06** | -0.10pt | 噪声内；**门仍未过** |

## 结论

1. **Codex 待办①完成**：17 截面补齐的历史影响已量化——2024 段修正 +3.38pt（方向：之前低估 alpha），2023/2025-26 基本不变。全区间 Top8 双周行业3 五因子 +35.02%（Codex 已复现）
2. **walk-forward 门仍未过**：2025-26 段 -0.71%（负），**加仓红线不变**——模拟盘继续纸面记录，盈利 ≠ 加仓依据
3. 2023/2024 的 alpha 证据比修复前更扎实（2024 修正后 +14.05%/夏普1.20）

## 复跑命令

```bash
.venv\Scripts\python.exe scripts\run_factor_portfolio.py --start 2023-01-01 --end 2023-12-31 --top-n 8 --max-per-industry 3 --rebalance biweekly
.venv\Scripts\python.exe scripts\run_factor_portfolio.py --start 2024-01-01 --end 2024-12-31 --top-n 8 --max-per-industry 3 --rebalance biweekly
.venv\Scripts\python.exe scripts\run_factor_portfolio.py --start 2025-01-01 --end 2026-08-20 --top-n 8 --max-per-industry 3 --rebalance biweekly
```
