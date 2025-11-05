from trader.interface import Trader
from typing import Dict, List, Any, Optional
import logging


class DummyAsterTrader(Trader):
    """Aster交易所的Dummy实现，用于避免报错"""
    
    def __init__(self, user: Optional[str] = None, signer: Optional[str] = None, private_key: Optional[str] = None):
        """
        初始化Dummy Aster Trader
        :param user: 主钱包地址
        :param signer: API钱包地址
        :param private_key: API钱包私钥
        """
        self.user = user or ""
        self.signer = signer or ""
        self.private_key = private_key or ""
        logging.info("Intialized Dummy Aster Trader (for avoiding errors only)")
    
    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        return {
            "total_wallet_balance": 0.0,
            "total_unrealized_profit": 0.0,
            "available_balance": 0.0,
        }
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有持仓"""
        return []
    
    def set_leverage(self, symbol: str, leverage: int) -> None:
        """设置杠杆"""
        pass
    
    def open_long(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开多仓"""
        logging.warning(f"Dummy Aster Trader: open_long called for {symbol} (not implemented)")
        return {"order_id": "dummy_order_id"}
    
    def open_short(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开空仓"""
        logging.warning(f"Dummy Aster Trader: open_short called for {symbol} (not implemented)")
        return {"order_id": "dummy_order_id"}
    
    def close_long(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平多仓"""
        logging.warning(f"Dummy Aster Trader: close_long called for {symbol} (not implemented)")
        return {"order_id": "dummy_order_id"}
    
    def close_short(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平空仓"""
        logging.warning(f"Dummy Aster Trader: close_short called for {symbol} (not implemented)")
        return {"order_id": "dummy_order_id"}
    
    def cancel_all_orders(self, symbol: str) -> None:
        """取消该币种的所有挂单"""
        pass
    
    def get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        # 返回一个默认价格
        return 100.0
    
    def calculate_position_size(self, balance: float, risk_percent: float, price: float, leverage: int) -> float:
        """计算仓位大小"""
        return 0.0
    
    def set_stop_loss(self, symbol: str, position_side: str, quantity: float, stop_price: float) -> None:
        """设置止损单"""
        logging.warning(f"Dummy Aster Trader: set_stop_loss called for {symbol} (not implemented)")
    
    def set_take_profit(self, symbol: str, position_side: str, quantity: float, take_profit_price: float) -> None:
        """设置止盈单"""
        logging.warning(f"Dummy Aster Trader: set_take_profit called for {symbol} (not implemented)")