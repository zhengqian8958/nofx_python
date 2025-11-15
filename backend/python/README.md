# NOFX Python版本

这是一个将NOFX交易系统从Go语言转换为Python的项目。该系统是一个基于AI的加密货币期货自动交易系统，支持Binance交易所。

## 项目结构

```
python/
├── config/              # 配置模块
│   ├── __init__.py
│   └── config.py        # 配置加载和验证
├── market/              # 市场数据获取和分析
│   ├── __init__.py
│   └── data.py          # 市场数据获取和指标计算
├── trader/              # 交易执行模块
│   ├── __init__.py
│   ├── interface.py     # 交易器接口
│   ├── binance_futures.py # 币安期货交易实现
│   └── auto_trader.py   # 自动交易器
├── mcp/                 # AI通信客户端
│   ├── __init__.py
│   └── client.py        # AI模型通信客户端
├── decision/            # AI决策引擎
│   ├── __init__.py
│   └── engine.py        # AI决策引擎
├── pool/                # 币种池管理
│   ├── __init__.py
│   └── coin_pool.py     # 币种池管理
├── manager/             # 交易器管理器
│   ├── __init__.py
│   └── trader_manager.py # 交易器管理器
├── api/                 # HTTP API服务
│   ├── __init__.py
│   └── server.py        # HTTP API服务
├── logger/              # 决策日志记录
│   ├── __init__.py
│   └── decision_logger.py # 决策日志记录器
├── main.py              # 程序入口
├── requirements.txt     # 依赖库列表
├── config.json.example  # 配置文件示例
├── INSTALL.md           # 安装指南
└── README.md            # 项目说明
```

## 功能特性

- 多AI竞赛模式：Qwen与DeepSeek AI实时对战
- AI自我学习机制：基于最近20个周期的历史表现优化决策
- 智能市场分析：结合3分钟与4小时K线、持仓量、AI500币池等多维度数据
- 专业风险控制：单币仓位限制、强制1:2风险回报比、防重复开仓
- Web监控界面：提供收益率曲线、实时性能对比等可视化功能

## 技术栈

- Python 3.8+
- Flask：Web框架
- python-binance：币安API客户端
- pandas & pandas-ta：数据处理和技指标计算
- requests：HTTP客户端

## 安装和运行

请参考 [INSTALL.md](INSTALL.md) 文件获取详细的安装和运行指南。

## 配置说明

请参考 [config.json.example](config.json.example) 文件获取配置示例。

## 许可证

本项目仅供学习和研究使用，请在合法合规的前提下使用。