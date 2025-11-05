from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class Trader(ABC):
    """交易器接口，支持多平台"""
    
    @abstractmethod
    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有持仓"""
        pass
    
    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int) -> None:
        """设置杠杆"""
        pass
    
    @abstractmethod
    def open_long(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开多仓"""
        pass
    
    @abstractmethod
    def open_short(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开空仓"""
        pass
    
    @abstractmethod
    def close_long(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平多仓"""
        pass
    
    @abstractmethod
    def close_short(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平空仓"""
        pass
    
    @abstractmethod
    def cancel_all_orders(self, symbol: str) -> None:
        """取消该币种的所有挂单"""
        pass
    
    @abstractmethod
    def get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        pass
    
    @abstractmethod
    def calculate_position_size(self, balance: float, risk_percent: float, price: float, leverage: int) -> float:
        """计算仓位大小"""
        pass
    
    @abstractmethod
    def set_stop_loss(self, symbol: str, position_side: str, quantity: float, stop_price: float) -> None:
        """设置止损单"""
        pass
    
    @abstractmethod
    def set_take_profit(self, symbol: str, position_side: str, quantity: float, take_profit_price: float) -> None:
        """设置止盈单"""
        pass