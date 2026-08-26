"""quant — A股量化研究框架。

模块结构:
- config:     pydantic 配置，敏感信息走环境变量
- data:       数据源抽象（Tushare/CSV）+ 数据质量控制
- backtest:   向量化回测引擎 + A股交易约束 + 绩效指标套件
- strategies: 策略信号生成（标准接口）
- factors:    因子处理（winsorize/中性化/IC-IR 分析）
"""

__version__ = "0.1.0"
