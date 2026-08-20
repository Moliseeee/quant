# UIA 备选方案：向 Kimi Work 输入框发送消息（cua-driver 会话故障时使用）
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$pid_target = 33464
$msg = @"
同步进展：模拟盘已正式启动。
① 数据已增量更新到 2026-08-20（186 个截面，新增 08-07/08-14/08-20 三期）。
② 首批持仓已生成（08-21 周五建仓）：当前为低换手市（市场换手率 3.143 < rolling 阈值 3.862），条件化未触发，主组合=影子组合——山东路桥/浙能电力/广州发展/物产中大/华域汽车/中国铁建/中国中铁/新华文轩，Top8 等权、行业≤3。
③ 新增周度选股工具 scripts/paper_select.py（每周五：更新数据→选股→记录），记录表 quant/模拟盘记录表.md，本周指导 quant/本周指导_模拟盘第1周.md，请审阅。
④ 实盘旧模型组合已清仓（restart，之前不算数），胜率复盘翻篇。
你的 iFinD 通道可顺手验证这 8 只的行情数据（浦发那批接口够用）。
"@

# 找 Kimi 主窗口
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pid_target)
$kimi = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if (-not $kimi) { Write-Host "FAIL: Kimi 窗口未找到"; exit 1 }

# 找输入框（Edit）
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit)
$edit = $kimi.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCond)
if (-not $edit) { Write-Host "FAIL: 输入框未找到"; exit 1 }
Write-Host "找到输入框: $($edit.Current.Name)"

# 聚焦输入框
$edit.SetFocus()
Start-Sleep -Milliseconds 500

# 剪贴板粘贴（绕过输入法）
Set-Clipboard -Value $msg
Start-Sleep -Milliseconds 300
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 800
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Milliseconds 500
Write-Host "OK: 消息已粘贴并发送"
