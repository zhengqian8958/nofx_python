import json
import time
import logging
import sys
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# 添加项目根目录到sys.path，使绝对导入可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用绝对导入替代相对导入
from market.data import MarketData, get as get_market_data, format_market_data
from mcp.client import call_with_messages

@dataclass
class PositionInfo:
    """持仓信息"""
    symbol: str = ""
    side: str = ""  # "long" or "short"
    entry_price: float = 0.0
    mark_price: float = 0.0
    quantity: float = 0.0
    leverage: int = 0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    liquidation_price: float = 0.0
    margin_used: float = 0.0
    update_time: int = 0  # 持仓更新时间戳（毫秒）


@dataclass
class AccountInfo:
    """账户信息"""
    total_equity: float = 0.0  # 账户净值
    available_balance: float = 0.0  # 可用余额
    total_pnl: float = 0.0  # 总盈亏
    total_pnl_pct: float = 0.0  # 总盈亏百分比
    margin_used: float = 0.0  # 已用保证金
    margin_used_pct: float = 0.0  # 保证金使用率
    position_count: int = 0  # 持仓数量


@dataclass
class CandidateCoin:
    """候选币种（来自币种池）"""
    symbol: str = ""
    sources: List[str] = field(default_factory=list)  # 来源: "ai500" 和/或 "oi_top"


@dataclass
class OITopData:
    """持仓量增长Top数据（用于AI决策参考）"""
    rank: int = 0  # OI Top排名
    oi_delta_percent: float = 0.0  # 持仓量变化百分比（1小时）
    oi_delta_value: float = 0.0  # 持仓量变化价值
    price_delta_percent: float = 0.0  # 价格变化百分比
    net_long: float = 0.0  # 净多仓
    net_short: float = 0.0  # 净空仓


@dataclass
class Context:
    """交易上下文（传递给AI的完整信息）"""
    current_time: str = ""
    runtime_minutes: int = 0
    call_count: int = 0
    account: AccountInfo = field(default_factory=AccountInfo)
    positions: List[PositionInfo] = field(default_factory=list)
    candidate_coins: List[CandidateCoin] = field(default_factory=list)
    market_data_map: Dict[str, MarketData] = field(default_factory=dict)  # 不序列化，但内部使用
    oi_top_data_map: Dict[str, OITopData] = field(default_factory=dict)  # OI Top数据映射
    performance: Any = None  # 历史表现分析（logger.PerformanceAnalysis）
    btc_eth_leverage: int = 0  # BTC/ETH杠杆倍数（从配置读取）
    altcoin_leverage: int = 0  # 山寨币杠杆倍数（从配置读取）
    short_interval: str = "3m"  # 短周期K线间隔（从scan_interval_minutes配置转换）
    # 交易状态字段（对齐 system_prompt 输入要求）
    last_enter_time: str = ""  # 最后开仓时间 ISO 格式
    last_stop_time: str = ""  # 最后止损时间 ISO 格式
    last_take_profit_time: str = ""  # 最后止盈时间 ISO 格式
    consecutive_losses_count: int = 0  # 连续亏损次数
    daily_loss_percent: float = 0.0  # 单日亏损百分比


@dataclass
class Decision:
    """AI的交易决策"""
    symbol: str = ""
    action: str = ""  # "open_long", "open_short", "close_long", "close_short", "hold", "wait"
    leverage: int = 0
    position_size_usd: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence: int = 0  # 信心度 (0-100)
    risk_usd: float = 0.0  # 最大美元风险
    reasoning: str = ""


@dataclass
class FullDecision:
    """AI的完整决策（包含思维链）"""
    user_prompt: str = ""  # 发送给AI的输入prompt
    cot_trace: str = ""  # 思维链分析（AI输出）
    decisions: List[Decision] = field(default_factory=list)  # 具体决策列表
    timestamp: float = 0.0


def get_full_decision(ctx: Context) -> FullDecision:
    """获取AI的完整交易决策（批量分析所有币种和持仓）"""
    # 1. 为所有币种获取市场数据
    _fetch_market_data_for_context(ctx)
    
    # 2. 构建 System Prompt（固定规则）和 User Prompt（动态数据）
    system_prompt = _build_system_prompt(ctx.account.total_equity, ctx.btc_eth_leverage, ctx.altcoin_leverage)
    user_prompt = _build_user_prompt(ctx)
    
    # 3. 调用AI API（使用 system + user prompt）
    ai_response = call_with_messages(system_prompt, user_prompt)
    
    # 4. 解析AI响应
    decision = _parse_full_decision_response(ai_response, ctx.account.total_equity, ctx.btc_eth_leverage, ctx.altcoin_leverage)
    decision.timestamp = time.time()
    decision.user_prompt = user_prompt  # 保存输入prompt
    return decision


def _fetch_market_data_for_context(ctx: Context) -> None:
    """为上下文中的所有币种获取市场数据和OI数据"""
    ctx.market_data_map = {}
    ctx.oi_top_data_map = {}
    
    # 收集所有需要获取数据的币种
    symbol_set = set()
    
    # 1. 优先获取持仓币种的数据（这是必须的）
    for pos in ctx.positions:
        symbol_set.add(pos.symbol)
    
    # 2. 候选币种数量根据账户状态动态调整
    max_candidates = _calculate_max_candidates(ctx)
    for i, coin in enumerate(ctx.candidate_coins):
        if i >= max_candidates:
            break
        symbol_set.add(coin.symbol)
    
    # 并发获取市场数据
    # 持仓币种集合（用于判断是否跳过OI检查）
    position_symbols = {pos.symbol for pos in ctx.positions}
    
    for symbol in symbol_set:
        try:
            # 使用配置的短周期K线间隔获取市场数据
            data = get_market_data(symbol, ctx.short_interval)
            
            # ⚠️ 流动性过滤：持仓价值低于15M USD的币种不做（多空都不做）
            # 持仓价值 = 持仓量 × 当前价格
            # 但现有持仓必须保留（需要决策是否平仓）
            is_existing_position = symbol in position_symbols
            if (not is_existing_position and 
                data.open_interest and 
                data.current_price > 0):
                # 计算持仓价值（USD）= 持仓量 × 当前价格
                oi_value = data.open_interest.latest * data.current_price
                oi_value_in_millions = oi_value / 1_000_000  # 转换为百万美元单位
                if oi_value_in_millions < 15:
                    logging.info(f"⚠️  {symbol} 持仓价值过低({oi_value_in_millions:.2f}M USD < 15M)，跳过此币种 [持仓量:{data.open_interest.latest:.0f} × 价格:{data.current_price:.4f}]")
                    continue
            
            ctx.market_data_map[symbol] = data
        except Exception as e:
            # 单个币种失败不影响整体，只记录错误
            logging.error(f"获取 {symbol} 市场数据失败: {e}")
            continue
    
    # 加载OI Top数据（不影响主流程）
    try:
        oi_positions = []  # TODO: 实现获取OI Top数据
        for pos in oi_positions:
            # 标准化符号匹配
            symbol = pos["symbol"]
            ctx.oi_top_data_map[symbol] = OITopData(
                rank=pos["rank"],
                oi_delta_percent=pos["oi_delta_percent"],
                oi_delta_value=pos["oi_delta_value"],
                price_delta_percent=pos["price_delta_percent"],
                net_long=pos["net_long"],
                net_short=pos["net_short"],
            )
    except Exception as e:
        logging.error(f"获取OI Top数据失败: {e}")


def _calculate_max_candidates(ctx: Context) -> int:
    """根据账户状态计算需要分析的候选币种数量"""
    # 直接返回候选池的全部币种数量
    # 因为候选池已经在 auto_trader.py 中筛选过了
    # 固定分析前20个评分最高的币种（来自AI500）
    return len(ctx.candidate_coins)


def _build_system_prompt(account_equity: float, btc_eth_leverage: int = 50, altcoin_leverage: int = 20) -> str:
    """构建 System Prompt（从外部文件读取并添加动态内容）"""
    # 定义外部提示词文件路径
    prompt_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompt", "system_prompt.txt")
    
    try:
        # 读取外部提示词文件内容
        with open(prompt_file_path, 'r', encoding='utf-8') as file:
            base_prompt = file.read()
        
        # 添加硬约束（风险控制）- 动态生成
        hard_constraints = f"""
# 硬约束（风险控制）

1. 风险回报比: 必须 ≥ 1:3（冒1%风险，赚3%+收益）
2. 最多持仓: 3个币种（质量>数量）
3. 单币仓位: 山寨{account_equity*0.8:.0f}-{account_equity*1.5:.0f} U({altcoin_leverage}x杠杆) | BTC/ETH {account_equity*5:.0f}-{account_equity*10:.0f} U({btc_eth_leverage}x杠杆)
4. 保证金: 总使用率 ≤ 90%
"""
        
        # 添加输出格式 - 动态生成
        output_format = f"""
# 输出格式

第一步: 思维链（纯文本）
简洁分析你的思考过程

第二步: JSON决策数组

```json
[
  {{"symbol": "BTCUSDT", "action": "open_short", "leverage": {btc_eth_leverage}, "position_size_usd": {account_equity*5:.0f}, "stop_loss": 97000, "take_profit": 91000, "confidence": 85, "risk_usd": 300, "reasoning": "下跌趋势+MACD死叉"}},
  {{"symbol": "ETHUSDT", "action": "close_long", "reasoning": "止盈离场"}}
]
```

字段说明:
- `action`: open_long | open_short | close_long | close_short | hold | wait
- `confidence`: 0-100（开仓建议≥75）
- 开仓时必填: leverage, position_size_usd, stop_loss, take_profit, confidence, risk_usd, reasoning
"""
        
        # 合并基础提示词和动态生成的内容
        full_prompt = base_prompt + hard_constraints + output_format
        
        return full_prompt
    except FileNotFoundError:
        # 如果外部文件不存在，使用默认的硬编码提示词
        logging.warning(f"外部提示词文件 {prompt_file_path} 未找到，使用默认提示词")
        prompt = f"""你是专业的加密货币交易AI，在币安合约市场进行自主交易。

# 🎯 核心目标

**最大化夏普比率（Sharpe Ratio）**

夏普比率 = 平均收益 / 收益波动率

**这意味着**：
- ✅ 高质量交易（高胜率、大盈亏比）→ 提升夏普
- ✅ 稳定收益、控制回撤 → 提升夏普
- ✅ 耐心持仓、让利润奔跑 → 提升夏普
- ❌ 频繁交易、小盈小亏 → 增加波动，严重降低夏普
- ❌ 过度交易、手续费损耗 → 直接亏损
- ❌ 过早平仓、频繁进出 → 错失大行情

**关键认知**: 系统每3分钟扫描一次，但不意味着每次都要交易！
大多数时候应该是 `wait` 或 `hold`，只在极佳机会时才开仓。

# 硬约束（风险控制）

1. 风险回报比: 必须 ≥ 1:3（冒1%风险，赚3%+收益）
2. 最多持仓: 3个币种（质量>数量）
3. 单币仓位: 山寨{account_equity*0.8:.0f}-{account_equity*1.5:.0f} U({altcoin_leverage}x杠杆) | BTC/ETH {account_equity*5:.0f}-{account_equity*10:.0f} U({btc_eth_leverage}x杠杆)
4. 保证金: 总使用率 ≤ 90%

# 📉 做多做空平衡

**重要**: 下跌趋势做空的利润 = 上涨趋势做多的利润

- 上涨趋势 → 做多
- 下跌趋势 → 做空
- 震荡市场 → 观望

**不要有做多偏见！做空是你的核心工具之一**

# ⏱️ 交易频率认知

**量化标准**:
- 优秀交易员：每天2-4笔 = 每小时0.1-0.2笔
- 过度交易：每小时>2笔 = 严重问题
- 最佳节奏：开仓后持有至少30-60分钟

**自查**:
如果你发现自己每个周期都在交易 → 说明标准太低
如果你发现持仓<30分钟就平仓 → 说明太急躁

# 🎯 开仓标准（严格）

只在**强信号**时开仓，不确定就观望。

**你拥有的完整数据**：
- 📊 **原始序列**：3分钟价格序列(MidPrices数组) + 4小时K线序列
- 📈 **技术序列**：EMA20序列、MACD序列、RSI7序列、RSI14序列
- 💰 **资金序列**：成交量序列、持仓量(OI)序列、资金费率
- 🎯 **筛选标记**：AI500评分 / OI_Top排名（如果有标注）

**分析方法**（完全由你自主决定）：
- 自由运用序列数据，你可以做但不限于趋势分析、形态识别、支撑阻力、技术阻力位、斐波那契、波动带计算
- 多维度交叉验证（价格+量+OI+指标+序列形态）
- 用你认为最有效的方法发现高确定性机会
- 综合信心度 ≥ 75 才开仓

**避免低质量信号**：
- 单一维度（只看一个指标）
- 相互矛盾（涨但量萎缩）
- 横盘震荡
- 刚平仓不久（<15分钟）

# 🧬 夏普比率自我进化

每次你会收到**夏普比率**作为绩效反馈（周期级别）：

**夏普比率 < -0.5** (持续亏损):
  → 🛑 停止交易，连续观望至少6个周期（18分钟）
  → 🔍 深度反思：
     • 交易频率过高？（每小时>2次就是过度）
     • 持仓时间过短？（<30分钟就是过早平仓）
     • 信号强度不足？（信心度<75）
     • 是否在做空？（单边做多是错误的）

**夏普比率 -0.5 ~ 0** (轻微亏损):
  → ⚠️ 严格控制：只做信心度>80的交易
  → 减少交易频率：每小时最多1笔新开仓
  → 耐心持仓：至少持有30分钟以上

**夏普比率 0 ~ 0.7** (正收益):
  → ✅ 维持当前策略

**夏普比率 > 0.7** (优异表现):
  → 🚀 可适度扩大仓位

**关键**: 夏普比率是唯一指标，它会自然惩罚频繁交易和过度进出。

# 📋 决策流程

1. **分析夏普比率**: 当前策略是否有效？需要调整吗？
2. **评估持仓**: 趋势是否改变？是否该止盈/止损？
3. **寻找新机会**: 有强信号吗？多空机会？
4. **输出决策**: 思维链分析 + JSON

# 输出格式

第一步: 思维链（纯文本）
简洁分析你的思考过程

第二步: JSON决策数组

```json
[
  {{"symbol": "BTCUSDT", "action": "open_short", "leverage": {btc_eth_leverage}, "position_size_usd": {account_equity*5:.0f}, "stop_loss": 97000, "take_profit": 91000, "confidence": 85, "risk_usd": 300, "reasoning": "下跌趋势+MACD死叉"}},
  {{"symbol": "ETHUSDT", "action": "close_long", "reasoning": "止盈离场"}}
]
```

字段说明:
- `action`: open_long | open_short | close_long | close_short | hold | wait
- `confidence`: 0-100（开仓建议≥75）
- 开仓时必填: leverage, position_size_usd, stop_loss, take_profit, confidence, risk_usd, reasoning

---
**记住**: 
- 目标是夏普比率，不是交易频率
- 做空 = 做多，都是赚钱工具
- 宁可错过，不做低质量交易
- 风险回报比1:3是底线
"""
        return prompt
    except Exception as e:
        # 如果读取文件时出现其他错误，记录日志并使用默认提示词
        logging.error(f"读取外部提示词文件时出错: {e}，使用默认提示词")
        return "你是专业的加密货币交易AI，在合约市场进行自主交易。"


def _build_user_prompt(ctx: Context) -> str:
    """构建 User Prompt（动态数据）"""
    prompt_lines = []
    
    # 系统状态
    prompt_lines.append(f"**时间**: {ctx.current_time} | **周期**: #{ctx.call_count} | **运行**: {ctx.runtime_minutes}分钟\n")
    
    # BTC 市场
    if "BTCUSDT" in ctx.market_data_map:
        btc_data = ctx.market_data_map["BTCUSDT"]
        # 计算BTC中期/长期涨跌幅（基于动态周期 medium/long）
        medium_change_pct = None
        long_change_pct = None
        try:
            if btc_data.timeframe_medium and btc_data.timeframe_medium.mid_prices:
                mp = btc_data.timeframe_medium.mid_prices
                if mp[0] > 0:
                    medium_change_pct = (mp[-1] - mp[0]) / mp[0] * 100
            if btc_data.timeframe_long and btc_data.timeframe_long.mid_prices:
                lp = btc_data.timeframe_long.mid_prices
                if lp[0] > 0:
                    long_change_pct = (lp[-1] - lp[0]) / lp[0] * 100
        except Exception:
            pass
        medium_str = f"{medium_change_pct:+.2f}%" if medium_change_pct is not None else "N/A"
        long_str = f"{long_change_pct:+.2f}%" if long_change_pct is not None else "N/A"
        prompt_lines.append(f"**BTC**: {btc_data.current_price:.2f} ({btc_data.medium_interval}: {medium_str}, {btc_data.long_interval}: {long_str}) | MACD: {btc_data.current_macd:.4f} | RSI: {btc_data.current_rsi7:.2f}\n")
        
        # 单独提取 BTC 多周期指标（对齐 system_prompt 输入要求）
        prompt_lines.append("\n**BTC 多周期指标**（用于山寨币交易的 BTC 状态确认）:\n\n")
        
        # BTC MACD (short/medium/long)
        btc_macd_short = btc_data.timeframe_short.macd_values if btc_data.timeframe_short else []
        btc_macd_medium = btc_data.timeframe_medium.macd_values if btc_data.timeframe_medium else []
        btc_macd_long = btc_data.timeframe_long.macd_values if btc_data.timeframe_long else []
        if btc_macd_short:
            prompt_lines.append(f"btc_macd_short ({btc_data.short_interval}): [{', '.join([f'{v:.4f}' for v in btc_macd_short])}]\n")
        if btc_macd_medium:
            prompt_lines.append(f"btc_macd_medium ({btc_data.medium_interval}): [{', '.join([f'{v:.4f}' for v in btc_macd_medium])}]\n")
        if btc_macd_long:
            prompt_lines.append(f"btc_macd_long ({btc_data.long_interval}): [{', '.join([f'{v:.4f}' for v in btc_macd_long])}]\n")
        
        # BTC 价格序列（用于计算波动率）
        btc_prices = btc_data.timeframe_short.mid_prices if btc_data.timeframe_short else []
        if btc_prices:
            prompt_lines.append(f"btc_price (short): [{', '.join([f'{p:.2f}' for p in btc_prices])}]\n")
        
        # BTC 日波动率（基于 long 周期价格序列）
        try:
            if btc_data.timeframe_long and btc_data.timeframe_long.mid_prices:
                lp = btc_data.timeframe_long.mid_prices
                if len(lp) >= 2:
                    price_changes = [(lp[i] - lp[i-1]) / lp[i-1] * 100 for i in range(1, len(lp)) if lp[i-1] > 0]
                    if price_changes:
                        btc_volatility = sum(abs(c) for c in price_changes) / len(price_changes)
                        prompt_lines.append(f"btc_daily_volatility_percent: {btc_volatility:.2f}%\n")
        except Exception:
            pass
        
        prompt_lines.append("\n")
    
    # 账户
    prompt_lines.append(f"**账户**: 净值{ctx.account.total_equity:.2f} | 余额{ctx.account.available_balance:.2f} ({ctx.account.available_balance/ctx.account.total_equity*100:.1f}%) | 盈亏{ctx.account.total_pnl:+.2f}% | 保证金{ctx.account.margin_used_pct:.1f}% | 持仓{ctx.account.position_count}个\n")
    
    # 交易状态约束（对齐 system_prompt 输入要求与决策流程检查）
    prompt_lines.append("\n**交易状态约束**（决策流程第 1-2 步检查）:\n\n")
    
    # 当前持仓状态（简化版，用于冷却期与连续亏损判定）
    if ctx.positions:
        for pos in ctx.positions:
            side_str = "long" if pos.side.lower() == "long" else "short"
            prompt_lines.append(f"current_position_{pos.symbol}: {{side: {side_str}, entry_price: {pos.entry_price:.4f}, size_coins: {pos.quantity:.4f}}}\n")
    else:
        prompt_lines.append("current_position: {side: null, entry_price: null, size_coins: null}\n")
    
    # 冷却期时间戳（ISO 格式）
    prompt_lines.append(f"last_enter_time: {ctx.last_enter_time if ctx.last_enter_time else 'null'}\n")
    prompt_lines.append(f"last_stop_time: {ctx.last_stop_time if ctx.last_stop_time else 'null'}\n")
    prompt_lines.append(f"last_take_profit_time: {ctx.last_take_profit_time if ctx.last_take_profit_time else 'null'}\n")
    
    # 连续亏损计数
    prompt_lines.append(f"consecutive_losses_count: {ctx.consecutive_losses_count}\n")
    
    # 单日亏损百分比（基于 ctx 传入或当前账户盈亏计算）
    daily_loss = ctx.daily_loss_percent if ctx.daily_loss_percent > 0 else abs(min(0, ctx.account.total_pnl_pct))
    prompt_lines.append(f"daily_loss_percent: {daily_loss:.2f}%\n")
    
    # 冷却状态计算（基于时间戳）
    cooldown_status = "ok"
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        # 检查开仓冷却（≥9分钟）
        if ctx.last_enter_time:
            last_enter = datetime.fromisoformat(ctx.last_enter_time.replace('Z', '+00:00'))
            enter_minutes = (now - last_enter).total_seconds() / 60
            if enter_minutes < 9:
                cooldown_status = "cooling"
        # 检查止损冷却（≥6分钟）
        if ctx.last_stop_time:
            last_stop = datetime.fromisoformat(ctx.last_stop_time.replace('Z', '+00:00'))
            stop_minutes = (now - last_stop).total_seconds() / 60
            if stop_minutes < 6:
                cooldown_status = "cooling"
        # 检查止盈冷却（≥3分钟）
        if ctx.last_take_profit_time:
            last_tp = datetime.fromisoformat(ctx.last_take_profit_time.replace('Z', '+00:00'))
            tp_minutes = (now - last_tp).total_seconds() / 60
            if tp_minutes < 3:
                cooldown_status = "cooling"
    except Exception:
        pass
    prompt_lines.append(f"cooldown_status: {cooldown_status}\n")
    
    prompt_lines.append("\n")
    
    # 持仓（完整市场数据）
    if ctx.positions:
        prompt_lines.append("## 当前持仓")
        for i, pos in enumerate(ctx.positions):
            # 计算持仓时长
            holding_duration = ""
            if pos.update_time > 0:
                duration_ms = int(time.time() * 1000) - pos.update_time
                duration_min = duration_ms // (1000 * 60)  # 转换为分钟
                if duration_min < 60:
                    holding_duration = f" | 持仓时长{duration_min}分钟"
                else:
                    duration_hour = duration_min // 60
                    duration_min_remainder = duration_min % 60
                    holding_duration = f" | 持仓时长{duration_hour}小时{duration_min_remainder}分钟"
            
            prompt_lines.append(f"{i+1}. {pos.symbol} {pos.side.upper()} | 入场价{pos.entry_price:.4f} 当前价{pos.mark_price:.4f} | 盈亏{pos.unrealized_pnl_pct:+.2f}% | 杠杆{pos.leverage}x | 保证金{pos.margin_used:.0f} | 强平价{pos.liquidation_price:.4f}{holding_duration}\n")
            
            # 使用format_market_data输出完整市场数据
            if pos.symbol in ctx.market_data_map:
                prompt_lines.append(format_market_data(ctx.market_data_map[pos.symbol]))
                prompt_lines.append("\n")
    else:
        prompt_lines.append("**当前持仓**: 无\n")
    
    # 候选币种（完整市场数据）
    prompt_lines.append(f"## 候选币种 ({len(ctx.market_data_map)})\n\n")
    displayed_count = 0
    for coin in ctx.candidate_coins:
        if coin.symbol not in ctx.market_data_map:
            continue
        displayed_count += 1
        
        source_tags = ""
        if len(coin.sources) > 1:
            source_tags = " (AI500+OI_Top双重信号)"
        elif len(coin.sources) == 1 and coin.sources[0] == "oi_top":
            source_tags = " (OI_Top持仓增长)"
        
        # 使用format_market_data输出完整市场数据
        prompt_lines.append(f"### {displayed_count}. {coin.symbol}{source_tags}\n\n")
        prompt_lines.append(format_market_data(ctx.market_data_map[coin.symbol]))
        prompt_lines.append("\n")
    
    prompt_lines.append("\n")
    
    # 夏普比率（直接传值，不要复杂格式化）
    if ctx.performance:
        # 直接从interface{}中提取SharpeRatio
        try:
            perf_data = json.loads(json.dumps(ctx.performance))
            if "sharpe_ratio" in perf_data:
                prompt_lines.append(f"## 📊 夏普比率: {perf_data['sharpe_ratio']:.2f}\n\n")
        except Exception:
            pass
    
    prompt_lines.append("---\n\n")
    prompt_lines.append("现在请分析并输出决策（思维链 + JSON）\n")
    
    return "".join(prompt_lines)


def _parse_full_decision_response(ai_response: str, account_equity: float, btc_eth_leverage: int, altcoin_leverage: int) -> FullDecision:
    """解析AI的完整决策响应"""
    # 1. 提取思维链
    cot_trace = _extract_cot_trace(ai_response)
    
    # 2. 提取JSON决策列表
    try:
        decisions = _extract_decisions(ai_response)
    except Exception as e:
        decision = FullDecision(cot_trace=cot_trace, decisions=[])
        raise Exception(f"提取决策失败: {e}\n\n=== AI思维链分析 ===\n{cot_trace}")
    
    # 3. 验证决策
    try:
        _validate_decisions(decisions, account_equity, btc_eth_leverage, altcoin_leverage)
    except Exception as e:
        decision = FullDecision(cot_trace=cot_trace, decisions=decisions)
        raise Exception(f"决策验证失败: {e}\n\n=== AI思维链分析 ===\n{cot_trace}")
    
    return FullDecision(cot_trace=cot_trace, decisions=decisions)


def _extract_cot_trace(response: str) -> str:
    """提取思维链分析"""
    # 查找JSON数组的开始位置
    json_start = response.find("[")
    
    if json_start > 0:
        # 思维链是JSON数组之前的内容
        return response[:json_start].strip()
    
    # 如果找不到JSON，整个响应都是思维链
    return response.strip()


def _extract_decisions(response: str) -> List[Decision]:
    """提取JSON决策列表"""
    # 直接查找JSON数组 - 找第一个完整的JSON数组
    array_start = response.find("[")
    if array_start == -1:
        raise Exception("无法找到JSON数组起始")
    
    # 从 [ 开始，匹配括号找到对应的 ]
    array_end = _find_matching_bracket(response, array_start)
    if array_end == -1:
        raise Exception("无法找到JSON数组结束")
    
    json_content = response[array_start:array_end+1].strip()
    
    # 🔧 修复常见的JSON格式错误：缺少引号的字段值
    # 匹配: "reasoning": 内容"}  或  "reasoning": 内容}  (没有引号)
    # 修复为: "reasoning": "内容"}
    # 使用简单的字符串扫描而不是正则表达式
    json_content = _fix_missing_quotes(json_content)
    
    # 解析JSON
    try:
        decisions_data = json.loads(json_content)
    except json.JSONDecodeError as e:
        raise Exception(f"JSON解析失败: {e}\nJSON内容: {json_content}")
    
    decisions = []
    for item in decisions_data:
        decision = Decision(
            symbol=item.get("symbol", ""),
            action=item.get("action", ""),
            leverage=item.get("leverage", 0),
            position_size_usd=item.get("position_size_usd", 0.0),
            stop_loss=item.get("stop_loss", 0.0),
            take_profit=item.get("take_profit", 0.0),
            confidence=item.get("confidence", 0),
            risk_usd=item.get("risk_usd", 0.0),
            reasoning=item.get("reasoning", ""),
        )
        decisions.append(decision)
    
    return decisions


def _fix_missing_quotes(json_str: str) -> str:
    """替换中文引号为英文引号（避免输入法自动转换）"""
    json_str = json_str.replace("\u201c", "\"")  # "
    json_str = json_str.replace("\u201d", "\"")  # "
    json_str = json_str.replace("\u2018", "'")   # '
    json_str = json_str.replace("\u2019", "'")   # '
    return json_str


def _validate_decisions(decisions: List[Decision], account_equity: float, btc_eth_leverage: int, altcoin_leverage: int) -> None:
    """验证所有决策（需要账户信息和杠杆配置）"""
    for i, decision in enumerate(decisions):
        _validate_decision(decision, account_equity, btc_eth_leverage, altcoin_leverage)


def _find_matching_bracket(s: str, start: int) -> int:
    """查找匹配的右括号"""
    if start >= len(s) or s[start] != '[':
        return -1
    
    depth = 0
    for i in range(start, len(s)):
        if s[i] == '[':
            depth += 1
        elif s[i] == ']':
            depth -= 1
            if depth == 0:
                return i
    
    return -1


def _validate_decision(d: Decision, account_equity: float, btc_eth_leverage: int, altcoin_leverage: int) -> None:
    """验证单个决策的有效性"""
    # 验证action
    valid_actions = {"open_long", "open_short", "close_long", "close_short", "hold", "wait"}
    
    if d.action not in valid_actions:
        raise Exception(f"无效的action: {d.action}")
    
    # 开仓操作必须提供完整参数
    if d.action in ["open_long", "open_short"]:
        # 根据币种使用配置的杠杆上限
        max_leverage = altcoin_leverage  # 山寨币使用配置的杠杆
        max_position_value = account_equity * 1.5  # 山寨币最多1.5倍账户净值
        if d.symbol in ["BTCUSDT", "ETHUSDT"]:
            max_leverage = btc_eth_leverage  # BTC和ETH使用配置的杠杆
            max_position_value = account_equity * 10  # BTC/ETH最多10倍账户净值
        
        if d.leverage <= 0 or d.leverage > max_leverage:
            raise Exception(f"杠杆必须在1-{max_leverage}之间（{d.symbol}，当前配置上限{max_leverage}倍）: {d.leverage}")
        if d.position_size_usd <= 0:
            raise Exception(f"仓位大小必须大于0: {d.position_size_usd:.2f}")
        # 验证仓位价值上限（加1%容差以避免浮点数精度问题）
        tolerance = max_position_value * 0.01  # 1%容差
        if d.position_size_usd > max_position_value + tolerance:
            if d.symbol in ["BTCUSDT", "ETHUSDT"]:
                raise Exception(f"BTC/ETH单币种仓位价值不能超过{max_position_value:.0f} USDT（10倍账户净值），实际: {d.position_size_usd:.0f}")
            else:
                raise Exception(f"山寨币单币种仓位价值不能超过{max_position_value:.0f} USDT（1.5倍账户净值），实际: {d.position_size_usd:.0f}")
        if d.stop_loss <= 0 or d.take_profit <= 0:
            raise Exception("止损和止盈必须大于0")
        
        # 验证止损止盈的合理性
        if d.action == "open_long":
            if d.stop_loss >= d.take_profit:
                raise Exception("做多时止损价必须小于止盈价")
        else:
            if d.stop_loss <= d.take_profit:
                raise Exception("做空时止损价必须大于止盈价")
        
        # 验证风险回报比（必须≥1:3）
        # 计算入场价（假设当前市价）
        entry_price = 0.0
        if d.action == "open_long":
            # 做多：入场价在止损和止盈之间
            entry_price = d.stop_loss + (d.take_profit - d.stop_loss) * 0.2  # 假设在20%位置入场
        else:
            # 做空：入场价在止损和止盈之间
            entry_price = d.stop_loss - (d.stop_loss - d.take_profit) * 0.2  # 假设在20%位置入场
        
        risk_percent = 0.0
        reward_percent = 0.0
        risk_reward_ratio = 0.0
        if d.action == "open_long":
            risk_percent = (entry_price - d.stop_loss) / entry_price * 100
            reward_percent = (d.take_profit - entry_price) / entry_price * 100
            if risk_percent > 0:
                risk_reward_ratio = reward_percent / risk_percent
        else:
            risk_percent = (d.stop_loss - entry_price) / entry_price * 100
            reward_percent = (entry_price - d.take_profit) / entry_price * 100
            if risk_percent > 0:
                risk_reward_ratio = reward_percent / risk_percent
        
        # 硬约束：风险回报比必须≥3.0
        if risk_reward_ratio < 3.0:
            raise Exception(f"风险回报比过低({risk_reward_ratio:.2f}:1)，必须≥3.0:1 [风险:{risk_percent:.2f}% 收益:{reward_percent:.2f}%] [止损:{d.stop_loss:.2f} 止盈:{d.take_profit:.2f}]")