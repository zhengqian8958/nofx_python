import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AccountSnapshot:
    """账户状态快照"""
    total_balance: float = 0.0
    available_balance: float = 0.0
    total_unrealized_profit: float = 0.0
    position_count: int = 0
    margin_used_pct: float = 0.0


@dataclass
class PositionSnapshot:
    """持仓快照"""
    symbol: str = ""
    side: str = ""
    position_amt: float = 0.0
    entry_price: float = 0.0
    mark_price: float = 0.0
    unrealized_profit: float = 0.0
    leverage: float = 0.0
    liquidation_price: float = 0.0


@dataclass
class DecisionAction:
    """决策执行记录"""
    action: str = ""
    symbol: str = ""
    quantity: float = 0.0
    leverage: int = 0
    price: float = 0.0
    order_id: Optional[int] = None
    timestamp: float = 0.0
    success: bool = False
    error: str = ""


@dataclass
class DecisionRecord:
    """决策记录"""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    cycle_number: int = 0
    success: bool = True
    error_message: str = ""
    input_prompt: str = ""
    cot_trace: str = ""
    decision_json: str = ""
    execution_log: List[str] = field(default_factory=list)
    account_state: Dict[str, Any] = field(default_factory=dict)
    positions: List[Dict[str, Any]] = field(default_factory=list)
    candidate_coins: List[str] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    # 交易状态字段（对齐 system_prompt 输入要求）
    last_enter_time: str = ""  # 最后开仓时间 ISO 格式
    last_stop_time: str = ""  # 最后止损时间 ISO 格式
    last_take_profit_time: str = ""  # 最后止盈时间 ISO 格式
    consecutive_losses_count: int = 0  # 连续亏损次数
    daily_loss_percent: float = 0.0  # 单日亏损百分比


class DecisionLogger:
    """决策日志记录器"""
    
    def __init__(self, log_dir: str = "decision_logs"):
        self.log_dir = log_dir
        self.log_file = os.path.join(log_dir, "decisions.jsonl")
        self.stats_file = os.path.join(log_dir, "statistics.json")
        
        # 确保日志目录存在
        os.makedirs(log_dir, exist_ok=True)
        
        # 初始化统计数据
        self._init_statistics()
    
    def _init_statistics(self) -> None:
        """初始化统计数据"""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, "r", encoding="utf-8") as f:
                    self.stats = json.load(f)
            except Exception:
                self.stats = self._get_default_stats()
        else:
            self.stats = self._get_default_stats()
            self._save_statistics()
    
    def _get_default_stats(self) -> Dict[str, Any]:
        """获取默认统计数据"""
        return {
            "total_decisions": 0,
            "successful_decisions": 0,
            "failed_decisions": 0,
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "first_log_time": None,
            "last_log_time": None,
        }
    
    def _save_statistics(self) -> None:
        """保存统计数据"""
        try:
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.warning(f"保存统计数据失败: {e}")
    
    def log_decision(self, record: DecisionRecord) -> None:
        """记录决策"""
        # 更新统计数据
        self.stats["total_decisions"] += 1
        if record.success:
            self.stats["successful_decisions"] += 1
        else:
            self.stats["failed_decisions"] += 1
        
        # 更新执行统计
        for decision in record.decisions:
            self.stats["total_executions"] += 1
            if decision.get("success", False):
                self.stats["successful_executions"] += 1
            else:
                self.stats["failed_executions"] += 1
        
        # 更新时间戳
        if not self.stats["first_log_time"]:
            self.stats["first_log_time"] = record.timestamp
        self.stats["last_log_time"] = record.timestamp
        
        # 保存统计数据
        self._save_statistics()
        
        # 保存决策记录
        try:
            # 为记录添加周期号
            record.cycle_number = self.stats["total_decisions"]
            
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")
        except Exception as e:
            logging.error(f"保存决策记录失败: {e}")
    
    def get_latest_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最新的决策记录"""
        records = []
        
        if not os.path.exists(self.log_file):
            return records
        
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # 从后往前读取，获取最新的记录
            for line in reversed(lines[-limit:]):
                try:
                    record = json.loads(line.strip())
                    records.append(record)
                except json.JSONDecodeError:
                    continue
            
            # 按时间顺序排列（从旧到新）
            records.reverse()
        except Exception as e:
            logging.error(f"读取决策记录失败: {e}")
        
        return records
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats
    
    def analyze_performance(self, cycles: int = 20) -> Dict[str, Any]:
        """分析最近N个周期的交易表现"""
        records = self.get_latest_records(cycles)
        
        if not records:
            return {
                "sharpe_ratio": 0.0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "max_drawdown": 0.0,
                "profit_factor": 0.0,
                "cycle_count": 0,
            }
        
        # 计算收益率序列
        returns = []
        equity_curve = []
        peak_equity = 0.0
        max_drawdown = 0.0
        
        # 计算盈亏统计
        wins = []
        losses = []
        
        for record in records:
            # 获取账户状态
            account_state = record.get("account_state", {})
            total_balance = account_state.get("total_balance", 0.0)
            total_pnl = account_state.get("total_unrealized_profit", 0.0)
            
            # 计算收益率（相对于初始余额）
            # 注意：这里需要知道初始余额才能计算收益率
            # 在实际应用中，可以从配置或其他地方获取初始余额
            # 这里我们简化处理，假设初始余额为1000
            initial_balance = 1000.0
            if total_balance > 0:
                return_pct = ((total_balance - initial_balance) / initial_balance) * 100
                returns.append(return_pct)
                equity_curve.append(total_balance)
                
                # 计算最大回撤
                if total_balance > peak_equity:
                    peak_equity = total_balance
                drawdown = (peak_equity - total_balance) / peak_equity * 100 if peak_equity > 0 else 0
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            # 分析执行结果
            for decision in record.get("decisions", []):
                if decision.get("success", False):
                    # 这里简化处理，实际应该从交易结果计算盈亏
                    # 暂时使用模拟数据
                    profit = decision.get("profit", 0.0)
                    if profit > 0:
                        wins.append(profit)
                    elif profit < 0:
                        losses.append(abs(profit))
        
        # 计算夏普比率
        sharpe_ratio = 0.0
        if returns:
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            if std_return > 0:
                sharpe_ratio = avg_return / std_return
        
        # 计算胜率
        win_rate = 0.0
        if wins or losses:
            win_rate = len(wins) / (len(wins) + len(losses)) * 100
        
        # 计算平均盈亏
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        
        # 计算盈亏比
        profit_factor = 0.0
        total_wins = sum(wins)
        total_losses = sum(losses)
        if total_losses > 0:
            profit_factor = total_wins / total_losses
        
        # 计算总盈亏
        total_pnl = sum(wins) - sum(losses)
        
        return {
            "sharpe_ratio": sharpe_ratio,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_drawdown": max_drawdown,
            "profit_factor": profit_factor,
            "cycle_count": len(records),
        }