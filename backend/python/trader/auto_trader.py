import json
import time
import logging
import sys
import os
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

# 添加项目根目录到sys.path，使绝对导入可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 使用绝对导入替代相对导入
from decision.engine import (
    Context, AccountInfo, PositionInfo, CandidateCoin, 
    get_full_decision, FullDecision, Decision
)
from market.data import get as get_market_data
# 导入DecisionLogger和DecisionRecord
from logger.decision_logger import DecisionLogger, DecisionRecord
from trader.interface import Trader
from trader.binance_futures import FuturesTrader
# 添加HyperliquidTrader导入
from trader.hyperliquid_trader import HyperliquidTrader
# 添加AsterTrader导入
from trader.aster_trader import DummyAsterTrader
# 添加AsterTrader导入
from trader.aster_trader import DummyAsterTrader

if TYPE_CHECKING:
    from logger.decision_logger import DecisionLogger, DecisionRecord


@dataclass
class AutoTraderConfig:
    """自动交易配置（简化版 - AI全权决策）"""
    # Trader标识
    id: str = ""  # Trader唯一标识（用于日志目录等）
    name: str = ""  # Trader显示名称
    ai_model: str = ""  # AI模型: "qwen" 或 "deepseek"
    
    # 交易平台选择
    exchange: str = ""  # "binance", "hyperliquid" 或 "aster"
    
    # 币安API配置
    binance_api_key: Optional[str] = None
    binance_secret_key: Optional[str] = None
    
    # Hyperliquid配置
    hyperliquid_private_key: Optional[str] = None
    hyperliquid_testnet: bool = False
    
    # Aster配置
    aster_user: Optional[str] = None  # Aster主钱包地址
    aster_signer: Optional[str] = None  # Aster API钱包地址
    aster_private_key: Optional[str] = None  # Aster API钱包私钥
    
    coin_pool_api_url: str = ""
    
    # AI配置
    use_qwen: bool = False
    deepseek_key: Optional[str] = None
    qwen_key: Optional[str] = None
    
    # 自定义AI API配置
    custom_api_url: Optional[str] = None
    custom_api_key: Optional[str] = None
    custom_model_name: Optional[str] = None
    
    # 扫描配置
    scan_interval_minutes: int = 3  # 扫描间隔（建议3分钟）
    
    # 账户配置
    initial_balance: float = 0.0  # 初始金额（用于计算盈亏，需手动设置）
    
    # 杠杆配置
    btc_eth_leverage: int = 5  # BTC和ETH的杠杆倍数
    altcoin_leverage: int = 5  # 山寨币的杠杆倍数
    
    # 风险控制（仅作为提示，AI可自主决定）
    max_daily_loss: float = 0.0  # 最大日亏损百分比（提示）
    max_drawdown: float = 0.0  # 最大回撤百分比（提示）
    stop_trading_time: int = 0  # 触发风控后暂停时长（秒）


class AutoTrader:
    """自动交易器"""
    
    def __init__(self, config: AutoTraderConfig):
        self.id = config.id  # Trader唯一标识
        self.name = config.name  # Trader显示名称
        self.ai_model = config.ai_model  # AI模型名称
        self.exchange = config.exchange  # 交易平台名称
        self.config = config
        self.trader: Optional[Trader] = None  # 使用Trader接口（支持多平台）
        self.decision_logger: Optional[DecisionLogger] = None  # 决策日志记录器
        self.initial_balance = config.initial_balance
        self.daily_pnl = 0.0
        self.last_reset_time = time.time()
        self.stop_until = 0.0
        self.is_running = False
        self.start_time = time.time()  # 系统启动时间
        self.call_count = 0  # AI调用次数
        self.position_first_seen_time: Dict[str, int] = {}  # 持仓首次出现时间 (symbol_side -> timestamp毫秒)
        
        # 交易状态追踪（对齐 system_prompt 输入要求）
        self.last_enter_time: str = ""  # 最后开仓时间 ISO 格式
        self.last_stop_time: str = ""  # 最后止损时间 ISO 格式
        self.last_take_profit_time: str = ""  # 最后止盈时间 ISO 格式
        self.consecutive_losses_count: int = 0  # 连续亏损次数
        
        # 添加调试信息
        print(f"DEBUG: Initializing AutoTrader {config.name}")
        print(f"DEBUG: AI Model: {config.ai_model}")
        print(f"DEBUG: DeepSeek Key: {config.deepseek_key[:10] if config.deepseek_key else None}")
        print(f"DEBUG: Qwen Key: {config.qwen_key[:10] if config.qwen_key else None}")
        print(f"DEBUG: Custom API URL: {config.custom_api_url}")
        print(f"DEBUG: Custom API Key: {config.custom_api_key[:10] if config.custom_api_key else None}")
        print(f"DEBUG: Custom Model Name: {config.custom_model_name}")
        
        # 初始化AI
        if config.ai_model == "custom" and config.custom_api_url and config.custom_api_key and config.custom_model_name:
            # 使用自定义API
            from mcp.client import set_custom_api
            set_custom_api(config.custom_api_url, config.custom_api_key, config.custom_model_name)
            logging.info(f"🤖 [{config.name}] 使用自定义AI API: {config.custom_api_url} (模型: {config.custom_model_name})")
        elif (config.use_qwen or config.ai_model == "qwen") and config.qwen_key:
            # 使用Qwen
            from mcp.client import set_qwen_api_key
            set_qwen_api_key(config.qwen_key, "")
            logging.info(f"🤖 [{config.name}] 使用阿里云Qwen AI")
        elif config.deepseek_key:
            # 默认使用DeepSeek
            from mcp.client import set_deepseek_api_key
            set_deepseek_api_key(config.deepseek_key)
            logging.info(f"🤖 [{config.name}] 使用DeepSeek AI")
        else:
            print("DEBUG: No AI key configured!")
            raise Exception("未配置AI密钥，请检查配置文件")
        
        # 初始化币种池API
        if config.coin_pool_api_url:
            from pool.coin_pool import set_coin_pool_api
            set_coin_pool_api(config.coin_pool_api_url)
        
        # 设置默认交易平台
        if not config.exchange:
            config.exchange = "binance"
        
        # 根据配置创建对应的交易器
        if config.exchange == "binance" and config.binance_api_key and config.binance_secret_key:
            logging.info(f"🏦 [{config.name}] 使用币安合约交易")
            self.trader = FuturesTrader(config.binance_api_key, config.binance_secret_key)
        elif config.exchange == "hyperliquid" and config.hyperliquid_private_key:
            logging.info(f"🏦 [{config.name}] 使用Hyperliquid交易")
            self.trader = HyperliquidTrader(config.hyperliquid_private_key, config.hyperliquid_testnet)
        elif config.exchange == "aster":
            logging.info(f"🏦 [{config.name}] 使用Aster交易")
            # 使用Dummy Aster Trader避免报错
            self.trader = DummyAsterTrader(config.aster_user, config.aster_signer, config.aster_private_key)
        else:
            raise Exception(f"不支持的交易平台: {config.exchange}")
        
        # 验证初始金额配置
        if config.initial_balance <= 0:
            raise Exception("初始金额必须大于0，请在配置中设置InitialBalance")
        
        # 初始化决策日志记录器（使用trader ID创建独立目录）
        log_dir = f"decision_logs/{config.id}"
        self.decision_logger = DecisionLogger(log_dir)
    
    def run(self) -> None:
        """运行自动交易主循环"""
        self.is_running = True
        logging.info("🚀 AI驱动自动交易系统启动")
        logging.info(f"💰 初始余额: {self.initial_balance:.2f} USDT")
        logging.info(f"⚙️  扫描间隔: {self.config.scan_interval_minutes}分钟")
        logging.info("🤖 AI将全权决定杠杆、仓位大小、止损止盈等参数")
        
        # 首次立即执行
        try:
            self._run_cycle()
        except Exception as e:
            logging.error(f"❌ 执行失败: {e}")
        
        # 定时执行
        while self.is_running:
            time.sleep(self.config.scan_interval_minutes * 60)
            try:
                self._run_cycle()
            except Exception as e:
                logging.error(f"❌ 执行失败: {e}")
    
    def stop(self) -> None:
        """停止自动交易"""
        self.is_running = False
        logging.info("⏹ 自动交易系统停止")
    
    def _run_cycle(self) -> None:
        """运行一个交易周期（使用AI全权决策）"""
        self.call_count += 1
        
        logging.info("=" * 70)
        logging.info(f"⏰ {time.strftime('%Y-%m-%d %H:%M:%S')} - AI决策周期 #{self.call_count}")
        logging.info("=" * 70)
        
        # 创建决策记录
        record = DecisionRecord()
        record.success = True
        
        # 1. 检查是否需要停止交易
        if time.time() < self.stop_until:
            remaining = self.stop_until - time.time()
            logging.info(f"⏸ 风险控制：暂停交易中，剩余 {remaining/60:.0f} 分钟")
            record.success = False
            record.error_message = f"风险控制暂停中，剩余 {remaining/60:.0f} 分钟"
            if self.decision_logger:
                self.decision_logger.log_decision(record)
            return
        
        # 2. 重置日盈亏（每天重置）
        if time.time() - self.last_reset_time > 24 * 3600:
            self.daily_pnl = 0
            self.last_reset_time = time.time()
            logging.info("📅 日盈亏已重置")
        
        # 3. 收集交易上下文
        try:
            ctx = self._build_trading_context()
        except Exception as e:
            record.success = False
            record.error_message = f"构建交易上下文失败: {e}"
            if self.decision_logger:
                self.decision_logger.log_decision(record)
            raise Exception(f"构建交易上下文失败: {e}")
        
        # 保存账户状态快照
        record.account_state = {
            "total_balance": ctx.account.total_equity,
            "available_balance": ctx.account.available_balance,
            "total_unrealized_profit": ctx.account.total_pnl,
            "position_count": ctx.account.position_count,
            "margin_used_pct": ctx.account.margin_used_pct,
        }
        
        # 保存持仓快照
        for pos in ctx.positions:
            record.positions.append({
                "symbol": pos.symbol,
                "side": pos.side,
                "position_amt": pos.quantity,
                "entry_price": pos.entry_price,
                "mark_price": pos.mark_price,
                "unrealized_profit": pos.unrealized_pnl,
                "leverage": float(pos.leverage),
                "liquidation_price": pos.liquidation_price,
            })
        
        # 保存候选币种列表
        for coin in ctx.candidate_coins:
            record.candidate_coins.append(coin.symbol)
        
        # 保存交易状态字段
        record.last_enter_time = self.last_enter_time
        record.last_stop_time = self.last_stop_time
        record.last_take_profit_time = self.last_take_profit_time
        record.consecutive_losses_count = self.consecutive_losses_count
        record.daily_loss_percent = abs(min(0, ctx.account.total_pnl_pct))
        
        logging.info(f"📊 账户净值: {ctx.account.total_equity:.2f} USDT | 可用: {ctx.account.available_balance:.2f} USDT | 持仓: {ctx.account.position_count}")
        
        # 4. 调用AI获取完整决策
        logging.info("🤖 正在请求AI分析并决策...")
        decision: Optional[FullDecision] = None
        try:
            decision = get_full_decision(ctx)
        except Exception as e:
            # 即使有错误，也保存思维链、决策和输入prompt（用于debug）
            if decision:
                record.input_prompt = decision.user_prompt
                record.cot_trace = decision.cot_trace
                if decision.decisions:
                    decision_data = []
                    for d in decision.decisions:
                        decision_data.append(d.__dict__)
                    decision_json = json.dumps(decision_data, ensure_ascii=False, indent=2)
                    record.decision_json = decision_json
            
            record.success = False
            record.error_message = f"获取AI决策失败: {e}"
            
            # 打印AI思维链（即使有错误）
            if decision and decision.cot_trace:
                logging.info("-" * 70)
                logging.info("💭 AI思维链分析（错误情况）:")
                logging.info("-" * 70)
                logging.info(decision.cot_trace)
                logging.info("-" * 70)
            
            if self.decision_logger:
                self.decision_logger.log_decision(record)
            raise Exception(f"获取AI决策失败: {e}")
        
        # 保存决策信息
        record.input_prompt = decision.user_prompt
        record.cot_trace = decision.cot_trace
        if decision.decisions:
            decision_data = []
            for d in decision.decisions:
                decision_data.append(d.__dict__)
            decision_json = json.dumps(decision_data, ensure_ascii=False, indent=2)
            record.decision_json = decision_json
        
        # 5. 打印AI思维链
        logging.info("-" * 70)
        logging.info("💭 AI思维链分析:")
        logging.info("-" * 70)
        logging.info(decision.cot_trace)
        logging.info("-" * 70)
        
        # 6. 打印AI决策
        logging.info(f"📋 AI决策列表 ({len(decision.decisions)} 个):")
        for i, d in enumerate(decision.decisions):
            logging.info(f"  [{i+1}] {d.symbol}: {d.action} - {d.reasoning}")
            if d.action in ["open_long", "open_short"]:
                logging.info(f"      杠杆: {d.leverage}x | 仓位: {d.position_size_usd:.2f} USDT | 止损: {d.stop_loss:.4f} | 止盈: {d.take_profit:.4f}")
        logging.info("")
        
        # 7. 对决策排序：确保先平仓后开仓（防止仓位叠加超限）
        sorted_decisions = self._sort_decisions_by_priority(decision.decisions)
        
        logging.info("🔄 执行顺序（已优化）: 先平仓→后开仓")
        for i, d in enumerate(sorted_decisions):
            logging.info(f"  [{i+1}] {d.symbol} {d.action}")
        logging.info("")
        
        # 执行决策并记录结果
        for d in sorted_decisions:
            action_record = {
                "action": d.action,
                "symbol": d.symbol,
                "quantity": 0,
                "leverage": d.leverage,
                "price": 0,
                "timestamp": time.time(),
                "success": False,
            }
            
            try:
                # ⚠️ 安全检查：防止交易非候选币种（例如 BTC 仅作为市场参考）
                if d.action in ["open_long", "open_short"]:
                    # 检查是否在候选币种池中
                    is_candidate = any(coin.symbol == d.symbol for coin in ctx.candidate_coins)
                    if not is_candidate:
                        raise Exception(f"⚠️  {d.symbol} 不在候选币种池中，拒绝开仓（只能交易用户指定的候选币种）")
                
                self._execute_decision_with_record(d, action_record)
                action_record["success"] = True
                record.execution_log.append(f"✓ {d.symbol} {d.action} 成功")
                # 成功执行后短暂延迟
                time.sleep(1)
            except Exception as e:
                logging.error(f"❌ 执行决策失败 ({d.symbol} {d.action}): {e}")
                action_record["error"] = str(e)
                record.execution_log.append(f"❌ {d.symbol} {d.action} 失败: {e}")
            
            record.decisions.append(action_record)
        
        # 8. 保存决策记录
        if self.decision_logger:
            try:
                self.decision_logger.log_decision(record)
            except Exception as e:
                logging.warning(f"⚠ 保存决策记录失败: {e}")
    
    def _build_trading_context(self) -> Context:
        """构建交易上下文"""
        if not self.trader:
            raise Exception("交易器未初始化")
        
        # 从最新决策记录恢复交易状态（防止重启后丢失状态）
        self._restore_trading_state_from_logs()
        
        # 1. 获取账户信息
        balance = self.trader.get_balance()
        
        # 获取账户字段
        total_wallet_balance = balance.get("total_wallet_balance", 0.0)
        total_unrealized_profit = balance.get("total_unrealized_profit", 0.0)
        available_balance = balance.get("available_balance", 0.0)
        
        # Total Equity = 钱包余额 + 未实现盈亏
        total_equity = total_wallet_balance + total_unrealized_profit
        
        # 2. 获取持仓信息
        positions = self.trader.get_positions()
        
        position_infos = []
        total_margin_used = 0.0
        
        # 当前持仓的key集合（用于清理已平仓的记录）
        current_position_keys = set()
        
        for pos in positions:
            symbol = pos["symbol"]
            side = pos["side"]
            entry_price = pos["entry_price"]
            mark_price = pos["mark_price"]
            quantity = pos["position_amt"]
            if quantity < 0:
                quantity = -quantity  # 空仓数量为负，转为正数
            unrealized_pnl = pos["un_realized_profit"]
            liquidation_price = pos["liquidation_price"]
            
            # 计算盈亏百分比
            pnl_pct = 0.0
            if side == "long":
                pnl_pct = ((mark_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - mark_price) / entry_price) * 100
            
            # 计算占用保证金（估算）
            leverage = 10  # 默认值，实际应该从持仓信息获取
            if "leverage" in pos:
                leverage = int(pos["leverage"])
            margin_used = (quantity * mark_price) / float(leverage)
            total_margin_used += margin_used
            
            # 跟踪持仓首次出现时间
            pos_key = f"{symbol}_{side}"
            current_position_keys.add(pos_key)
            if pos_key not in self.position_first_seen_time:
                # 新持仓，记录当前时间
                self.position_first_seen_time[pos_key] = int(time.time() * 1000)
            update_time = self.position_first_seen_time[pos_key]
            
            position_infos.append(PositionInfo(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                mark_price=mark_price,
                quantity=quantity,
                leverage=leverage,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=pnl_pct,
                liquidation_price=liquidation_price,
                margin_used=margin_used,
                update_time=update_time,
            ))
        
        # 清理已平仓的持仓记录
        keys_to_remove = []
        for key in self.position_first_seen_time:
            if key not in current_position_keys:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self.position_first_seen_time[key]
        
        # 3. 获取合并的候选币种池（AI500 + OI Top，去重）
        # 无论有没有持仓，都分析相同数量的币种（让AI看到所有好机会）
        # AI会根据保证金使用率和现有持仓情况，自己决定是否要换仓
        ai500_limit = 20  # AI500取前20个评分最高的币种
        
        # 获取合并后的币种池（AI500 + OI Top）
        from pool.coin_pool import get_merged_coin_pool
        merged_pool = get_merged_coin_pool(ai500_limit)
        
        # 构建候选币种列表（包含来源信息）
        candidate_coins = []
        for symbol in merged_pool.all_symbols:
            sources = merged_pool.symbol_sources.get(symbol, [])
            candidate_coins.append(CandidateCoin(symbol=symbol, sources=sources))
        
        logging.info(f"📋 合并币种池: AI500前{ai500_limit} + OI_Top20 = 总计{len(candidate_coins)}个候选币种")
        
        # 4. 计算总盈亏
        total_pnl = total_equity - self.initial_balance
        total_pnl_pct = 0.0
        if self.initial_balance > 0:
            total_pnl_pct = (total_pnl / self.initial_balance) * 100
        
        margin_used_pct = 0.0
        if total_equity > 0:
            margin_used_pct = (total_margin_used / total_equity) * 100
        
        # 5. 分析历史表现（最近20个周期）
        performance = None
        if self.decision_logger:
            try:
                performance = self.decision_logger.analyze_performance(20)
            except Exception as e:
                logging.warning(f"⚠️  分析历史表现失败: {e}")
                # 不影响主流程，继续执行（但设置performance为None以避免传递错误数据）
                performance = None
        
        # 6. 构建上下文
        ctx = Context(
            current_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            runtime_minutes=int((time.time() - self.start_time) / 60),
            call_count=self.call_count,
            btc_eth_leverage=self.config.btc_eth_leverage,   # 使用配置的杠杆倍数
            altcoin_leverage=self.config.altcoin_leverage,   # 使用配置的杠杆倍数
            medium_interval=self._minutes_to_interval(self.config.scan_interval_minutes),  # 转换配置的扫描间隔为K线周期（交易主周期）
            account=AccountInfo(
                total_equity=total_equity,
                available_balance=available_balance,
                total_pnl=total_pnl,
                total_pnl_pct=total_pnl_pct,
                margin_used=total_margin_used,
                margin_used_pct=margin_used_pct,
                position_count=len(position_infos),
            ),
            positions=position_infos,
            candidate_coins=candidate_coins,
            performance=performance,  # 添加历史表现分析
            # 交易状态字段（对齐 system_prompt 输入要求）
            last_enter_time=self.last_enter_time,
            last_stop_time=self.last_stop_time,
            last_take_profit_time=self.last_take_profit_time,
            consecutive_losses_count=self.consecutive_losses_count,
            daily_loss_percent=abs(min(0, total_pnl_pct)),
        )
        
        return ctx
    
    def _minutes_to_interval(self, minutes: int) -> str:
        """将分钟数转换为Binance K线间隔字符串"""
        interval_map = {
            1: "1m",
            3: "3m",
            5: "5m",
            15: "15m",
            30: "30m",
            60: "1h",
            120: "2h",
            240: "4h",
            360: "6h",
            480: "8h",
            720: "12h",
            1440: "1d",
            4320: "3d",
            10080: "1w",
        }
        return interval_map.get(minutes, "3m")  # 默认3m
    
    def _calculate_short_interval(self, medium_interval: str) -> str:
        """基于medium interval计算short interval（约为medium的1/3到1/5）"""
        from market.data import interval_to_minutes, SUPPORTED_INTERVALS
        
        medium_minutes = interval_to_minutes(medium_interval)
        if medium_minutes <= 0:
            return "1m"  # 兜底
        
        # 计算目标范围：medium的1/5到1/3
        target_min = medium_minutes / 5.0
        target_max = medium_minutes / 3.0
        
        # 排序的间隔列表
        sorted_intervals = sorted(SUPPORTED_INTERVALS.items(), key=lambda kv: kv[1])
        
        # 找到范围内最接近1/4的候选
        target_mid = medium_minutes / 4.0
        candidates = [(i, m) for i, m in sorted_intervals if target_min <= m <= target_max]
        
        if candidates:
            # 选择最接近1/4的候选
            best = min(candidates, key=lambda x: abs(x[1] - target_mid))
            return best[0]
        
        # 若范围内无候选，选择小于target_min的最大可用
        smaller = [(i, m) for i, m in sorted_intervals if m < target_min]
        if smaller:
            return smaller[-1][0]
        
        # 否则返回最小可用（兜底）
        return sorted_intervals[0][0]
    
    def _restore_trading_state_from_logs(self) -> None:
        """从最新决策记录恢复交易状态（防止重启后丢失状态）"""
        if not self.decision_logger:
            return
        
        try:
            # 获取最新的决策记录
            latest_records = self.decision_logger.get_latest_records(1)
            if not latest_records:
                return
            
            last_record = latest_records[0]
            
            # 恢复交易状态字段
            self.last_enter_time = last_record.get("last_enter_time", "")
            self.last_stop_time = last_record.get("last_stop_time", "")
            self.last_take_profit_time = last_record.get("last_take_profit_time", "")
            self.consecutive_losses_count = last_record.get("consecutive_losses_count", 0)
            
            logging.info(f"💾 已从日志恢复交易状态（最后开仓: {self.last_enter_time or 'null'}, 连续亏损: {self.consecutive_losses_count}）")
        except Exception as e:
            logging.warning(f"⚠️  从日志恢复状态失败: {e}")
    
    def _execute_decision_with_record(self, decision: Decision, action_record: Dict[str, Any]) -> None:
        """执行AI决策并记录详细信息"""
        if not self.trader:
            raise Exception("交易器未初始化")
        
        if decision.action == "open_long":
            self._execute_open_long_with_record(decision, action_record)
        elif decision.action == "open_short":
            self._execute_open_short_with_record(decision, action_record)
        elif decision.action == "close_long":
            self._execute_close_long_with_record(decision, action_record)
        elif decision.action == "close_short":
            self._execute_close_short_with_record(decision, action_record)
        elif decision.action in ["hold", "wait"]:
            # 无需执行，仅记录
            pass
        else:
            raise Exception(f"未知的action: {decision.action}")
    
    def _execute_open_long_with_record(self, decision: Decision, action_record: Dict[str, Any]) -> None:
        """执行开多仓并记录详细信息"""
        if not self.trader:
            raise Exception("交易器未初始化")
        
        logging.info(f"  📈 开多仓: {decision.symbol}")
        
        # ⚠️ 关键：检查是否已有同币种同方向持仓，如果有则拒绝开仓（防止仓位叠加超限）
        positions = self.trader.get_positions()
        for pos in positions:
            if pos["symbol"] == decision.symbol and pos["side"] == "long":
                raise Exception(f"❌ {decision.symbol} 已有多仓，拒绝开仓以防止仓位叠加超限。如需换仓，请先给出 close_long 决策")
        
        # 获取当前价格
        market_data = get_market_data(decision.symbol)
        
        # 计算数量
        quantity = decision.position_size_usd / market_data.current_price
        action_record["quantity"] = quantity
        action_record["price"] = market_data.current_price
        
        # 开仓
        order = self.trader.open_long(decision.symbol, quantity, decision.leverage)
        
        # 记录订单ID
        if "order_id" in order:
            action_record["order_id"] = order["order_id"]
        
        logging.info(f"  ✓ 开仓成功，订单ID: {order.get('order_id')}, 数量: {quantity:.4f}")
        
        # 记录开仓时间
        pos_key = f"{decision.symbol}_long"
        self.position_first_seen_time[pos_key] = int(time.time() * 1000)
        
        # 更新最后开仓时间（ISO 格式）
        from datetime import datetime, timezone
        self.last_enter_time = datetime.now(timezone.utc).isoformat()
        
        # 设置止损止盈
        try:
            self.trader.set_stop_loss(decision.symbol, "LONG", quantity, decision.stop_loss)
        except Exception as e:
            logging.warning(f"  ⚠ 设置止损失败: {e}")
        try:
            self.trader.set_take_profit(decision.symbol, "LONG", quantity, decision.take_profit)
        except Exception as e:
            logging.warning(f"  ⚠ 设置止盈失败: {e}")
    
    def _execute_open_short_with_record(self, decision: Decision, action_record: Dict[str, Any]) -> None:
        """执行开空仓并记录详细信息"""
        if not self.trader:
            raise Exception("交易器未初始化")
        
        logging.info(f"  📉 开空仓: {decision.symbol}")
        
        # ⚠️ 关键：检查是否已有同币种同方向持仓，如果有则拒绝开仓（防止仓位叠加超限）
        positions = self.trader.get_positions()
        for pos in positions:
            if pos["symbol"] == decision.symbol and pos["side"] == "short":
                raise Exception(f"❌ {decision.symbol} 已有空仓，拒绝开仓以防止仓位叠加超限。如需换仓，请先给出 close_short 决策")
        
        # 获取当前价格
        market_data = get_market_data(decision.symbol)
        
        # 计算数量
        quantity = decision.position_size_usd / market_data.current_price
        action_record["quantity"] = quantity
        action_record["price"] = market_data.current_price
        
        # 开仓
        order = self.trader.open_short(decision.symbol, quantity, decision.leverage)
        
        # 记录订单ID
        if "order_id" in order:
            action_record["order_id"] = order["order_id"]
        
        logging.info(f"  ✓ 开仓成功，订单ID: {order.get('order_id')}, 数量: {quantity:.4f}")
        
        # 记录开仓时间
        pos_key = f"{decision.symbol}_short"
        self.position_first_seen_time[pos_key] = int(time.time() * 1000)
        
        # 更新最后开仓时间（ISO 格式）
        from datetime import datetime, timezone
        self.last_enter_time = datetime.now(timezone.utc).isoformat()
        
        # 设置止损止盈
        try:
            self.trader.set_stop_loss(decision.symbol, "SHORT", quantity, decision.stop_loss)
        except Exception as e:
            logging.warning(f"  ⚠ 设置止损失败: {e}")
        try:
            self.trader.set_take_profit(decision.symbol, "SHORT", quantity, decision.take_profit)
        except Exception as e:
            logging.warning(f"  ⚠ 设置止盈失败: {e}")
    
    def _execute_close_long_with_record(self, decision: Decision, action_record: Dict[str, Any]) -> None:
        """执行平多仓并记录详细信息"""
        if not self.trader:
            raise Exception("交易器未初始化")
        
        logging.info(f"  🔄 平多仓: {decision.symbol}")
        
        # 获取当前价格
        market_data = get_market_data(decision.symbol)
        action_record["price"] = market_data.current_price
        
        # 获取持仓信息（判断是止损还是止盈）
        positions = self.trader.get_positions()
        is_stop_loss = False
        is_take_profit = False
        for pos in positions:
            if pos["symbol"] == decision.symbol and pos["side"] == "long":
                entry_price = pos["entry_price"]
                mark_price = pos["mark_price"]
                pnl_pct = ((mark_price - entry_price) / entry_price) * 100
                # 简单判断：亏损 > 1% 为止损，盈利 > 1% 为止盈
                if pnl_pct < -1.0:
                    is_stop_loss = True
                elif pnl_pct > 1.0:
                    is_take_profit = True
                break
        
        # 平仓
        order = self.trader.close_long(decision.symbol, 0)  # 0 = 全部平仓
        
        # 记录订单ID
        if "order_id" in order:
            action_record["order_id"] = order["order_id"]
        
        logging.info("  ✓ 平仓成功")
        
        # 更新最后止损/止盈时间（ISO 格式）
        from datetime import datetime, timezone
        if is_stop_loss:
            self.last_stop_time = datetime.now(timezone.utc).isoformat()
            logging.info(f"  🛡️ 记录止损时间: {self.last_stop_time}")
        elif is_take_profit:
            self.last_take_profit_time = datetime.now(timezone.utc).isoformat()
            logging.info(f"  🎉 记录止盈时间: {self.last_take_profit_time}")
    
    def _execute_close_short_with_record(self, decision: Decision, action_record: Dict[str, Any]) -> None:
        """执行平空仓并记录详细信息"""
        if not self.trader:
            raise Exception("交易器未初始化")
        
        logging.info(f"  🔄 平空仓: {decision.symbol}")
        
        # 获取当前价格
        market_data = get_market_data(decision.symbol)
        action_record["price"] = market_data.current_price
        
        # 获取持仓信息（判断是止损还是止盈）
        positions = self.trader.get_positions()
        is_stop_loss = False
        is_take_profit = False
        for pos in positions:
            if pos["symbol"] == decision.symbol and pos["side"] == "short":
                entry_price = pos["entry_price"]
                mark_price = pos["mark_price"]
                pnl_pct = ((entry_price - mark_price) / entry_price) * 100
                # 简单判断：亏损 > 1% 为止损，盈利 > 1% 为止盈
                if pnl_pct < -1.0:
                    is_stop_loss = True
                elif pnl_pct > 1.0:
                    is_take_profit = True
                break
        
        # 平仓
        order = self.trader.close_short(decision.symbol, 0)  # 0 = 全部平仓
        
        # 记录订单ID
        if "order_id" in order:
            action_record["order_id"] = order["order_id"]
        
        logging.info("  ✓ 平仓成功")
        
        # 更新最后止损/止盈时间（ISO 格式）
        from datetime import datetime, timezone
        if is_stop_loss:
            self.last_stop_time = datetime.now(timezone.utc).isoformat()
            logging.info(f"  🛡️ 记录止损时间: {self.last_stop_time}")
        elif is_take_profit:
            self.last_take_profit_time = datetime.now(timezone.utc).isoformat()
            logging.info(f"  🎉 记录止盈时间: {self.last_take_profit_time}")
    
    def get_id(self) -> str:
        """获取trader ID"""
        return self.id
    
    def get_name(self) -> str:
        """获取trader名称"""
        return self.name
    
    def get_ai_model(self) -> str:
        """获取AI模型"""
        return self.ai_model
    
    def get_decision_logger(self) -> Optional[DecisionLogger]:
        """获取决策日志记录器"""
        return self.decision_logger
    
    def get_status(self) -> Dict[str, Any]:
        """获取系统状态（用于API）"""
        ai_provider = "DeepSeek"
        if self.config.use_qwen:
            ai_provider = "Qwen"
        elif self.config.ai_model == "custom":
            ai_provider = "Custom"
        
        return {
            "trader_id": self.id,
            "trader_name": self.name,
            "ai_model": self.ai_model,
            "exchange": self.exchange,
            "is_running": self.is_running,
            "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.start_time)),
            "runtime_minutes": int((time.time() - self.start_time) / 60),
            "call_count": self.call_count,
            "initial_balance": self.initial_balance,
            "scan_interval": f"{self.config.scan_interval_minutes}m",
            "stop_until": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.stop_until)),
            "last_reset_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.last_reset_time)),
            "ai_provider": ai_provider,
        }
    
    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息（用于API）"""
        if not self.trader:
            raise Exception("交易器未初始化")
        
        try:
            balance = self.trader.get_balance()
        except Exception as e:
            raise Exception(f"获取余额失败: {e}")
        
        # 获取账户字段
        total_wallet_balance = balance.get("total_wallet_balance", 0.0)
        total_unrealized_profit = balance.get("total_unrealized_profit", 0.0)
        available_balance = balance.get("available_balance", 0.0)
        
        # Total Equity = 钱包余额 + 未实现盈亏
        total_equity = total_wallet_balance + total_unrealized_profit
        
        # 获取持仓计算总保证金
        try:
            positions = self.trader.get_positions()
        except Exception as e:
            raise Exception(f"获取持仓失败: {e}")
        
        total_margin_used = 0.0
        total_unrealized_pnl = 0.0
        for pos in positions:
            mark_price = pos["mark_price"]
            quantity = pos["position_amt"]
            if quantity < 0:
                quantity = -quantity
            unrealized_pnl = pos["un_realized_profit"]
            total_unrealized_pnl += unrealized_pnl
            
            leverage = 10
            if "leverage" in pos:
                leverage = int(pos["leverage"])
            margin_used = (quantity * mark_price) / float(leverage)
            total_margin_used += margin_used
        
        total_pnl = total_equity - self.initial_balance
        total_pnl_pct = 0.0
        if self.initial_balance > 0:
            total_pnl_pct = (total_pnl / self.initial_balance) * 100
        
        margin_used_pct = 0.0
        if total_equity > 0:
            margin_used_pct = (total_margin_used / total_equity) * 100
        
        return {
            # 核心字段
            "total_equity": total_equity,           # 账户净值 = wallet + unrealized
            "wallet_balance": total_wallet_balance,    # 钱包余额（不含未实现盈亏）
            "unrealized_profit": total_unrealized_profit, # 未实现盈亏（从API）
            "available_balance": available_balance,      # 可用余额
            
            # 盈亏统计
            "total_pnl": total_pnl,           # 总盈亏 = equity - initial
            "total_pnl_pct": total_pnl_pct,        # 总盈亏百分比
            "total_unrealized_pnl": total_unrealized_pnl, # 未实现盈亏（从持仓计算）
            "initial_balance": self.initial_balance,  # 初始余额
            "daily_pnl": self.daily_pnl,        # 日盈亏
            
            # 持仓信息
            "position_count": len(positions),  # 持仓数量
            "margin_used": total_margin_used, # 保证金占用
            "margin_used_pct": margin_used_pct,   # 保证金使用率
        }
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓列表（用于API）"""
        if not self.trader:
            raise Exception("交易器未初始化")
        
        try:
            positions = self.trader.get_positions()
        except Exception as e:
            raise Exception(f"获取持仓失败: {e}")
        
        result = []
        for pos in positions:
            symbol = pos["symbol"]
            side = pos["side"]
            entry_price = pos["entry_price"]
            mark_price = pos["mark_price"]
            quantity = pos["position_amt"]
            if quantity < 0:
                quantity = -quantity
            unrealized_pnl = pos["un_realized_profit"]
            liquidation_price = pos["liquidation_price"]
            
            leverage = 10
            if "leverage" in pos:
                leverage = int(pos["leverage"])
            
            pnl_pct = 0.0
            if side == "long":
                pnl_pct = ((mark_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - mark_price) / entry_price) * 100
            
            margin_used = (quantity * mark_price) / float(leverage)
            
            result.append({
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "mark_price": mark_price,
                "quantity": quantity,
                "leverage": leverage,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": pnl_pct,
                "liquidation_price": liquidation_price,
                "margin_used": margin_used,
            })
        
        return result
    
    def _sort_decisions_by_priority(self, decisions: List[Decision]) -> List[Decision]:
        """对决策排序：先平仓，再开仓，最后hold/wait
        这样可以避免换仓时仓位叠加超限
        """
        if len(decisions) <= 1:
            return decisions
        
        # 定义优先级
        def get_action_priority(action: str) -> int:
            priority_map = {
                "close_long": 1,
                "close_short": 1,
                "open_long": 2,
                "open_short": 2,
                "hold": 3,
                "wait": 3,
            }
            return priority_map.get(action, 999)  # 未知动作放最后
        
        # 按优先级排序
        return sorted(decisions, key=lambda d: get_action_priority(d.action))
