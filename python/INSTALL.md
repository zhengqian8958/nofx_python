# NOFX Python版本安装指南

## 环统要求

- Python 3.8或更高版本
- pip包管理器

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd nofx/python
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置文件

复制示例配置文件并根据需要进行修改：

```bash
cp config.json.example config.json
```

编辑 `config.json` 文件，配置以下内容：
- 交易所API密钥
- AI模型密钥（DeepSeek、Qwen等）
- 初始余额
- 杠杆设置

### 5. 运行系统

```bash
python main.py
```

或者指定配置文件：

```bash
python main.py config.json
```

## 配置说明

### config.json字段说明

- `traders`: 交易者配置数组
  - `id`: 交易者唯一标识
  - `name`: 交易者名称
  - `ai_model`: AI模型（"qwen"、"deepseek"或"custom"）
  - `exchange`: 交易所（"binance"、"hyperliquid"或"aster"）
  - `binance_api_key`: 币安API密钥（使用币安时必需）
  - `binance_secret_key`: 币安密钥（使用币安时必需）
  - `qwen_key`: 阿里云Qwen API密钥（使用Qwen时必需）
  - `deepseek_key`: DeepSeek API密钥（使用DeepSeek时必需）
  - `initial_balance`: 初始余额
  - `scan_interval_minutes`: 扫描间隔（分钟）

- `api_server_port`: API服务器端口（默认8080）
- `leverage`: 杠杆配置
  - `btc_eth_leverage`: BTC/ETH杠杆倍数
  - `altcoin_leverage`: 山寨币杠杆倍数

## API接口

系统启动后，可以通过以下API接口获取数据：

- `GET /api/competition`: 竞赛总览
- `GET /api/traders`: Trader列表
- `GET /api/status?trader_id=xxx`: 指定trader的系统状态
- `GET /api/account?trader_id=xxx`: 指定trader的账户信息
- `GET /api/positions?trader_id=xxx`: 指定trader的持仓列表
- `GET /api/decisions?trader_id=xxx`: 指定trader的决策日志
- `GET /api/decisions/latest?trader_id=xxx`: 指定trader的最新决策
- `GET /health`: 健康检查

## 注意事项

1. **风险提示**: AI自动交易有风险，建议小额资金测试！
2. **API密钥**: 请妥善保管您的API密钥，不要泄露给他人。
3. **网络连接**: 确保系统能够访问交易所和AI服务的API。
4. **日志文件**: 系统会生成决策日志文件，用于分析和调试。

## 故障排除

### 1. 依赖安装失败

如果在安装依赖时遇到问题，请尝试：

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. API连接问题

- 检查网络连接
- 验证API密钥是否正确
- 确认防火墙设置

### 3. 运行时错误

查看日志文件获取详细错误信息，通常位于 `decision_logs` 目录中。