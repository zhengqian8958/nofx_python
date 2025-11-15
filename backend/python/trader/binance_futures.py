import time
import logging
from typing import Dict, List, Any, Optional
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from .interface import Trader


class FuturesTrader(Trader):
    """币安合约交易器"""
    
    def __init__(self, api_key: str, secret_key: str):
        self.client = Client(api_key, secret_key)
    
    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        logging.info("🔄 正在调用币安API获取账户余额...")
        try:
            account = self.client.futures_account()
            
            result = {
                "total_wallet_balance": float(account["totalWalletBalance"]),
                "available_balance": float(account["availableBalance"]),
                "total_unrealized_profit": float(account["totalUnrealizedProfit"]),
            }
            
            logging.info(f"✓ 币安API返回: 总余额={account['totalWalletBalance']}, 可用={account['availableBalance']}, 未实现盈亏={account['totalUnrealizedProfit']}")
            return result
        except BinanceAPIException as e:
            logging.error(f"❌ 币安API调用失败: {e}")
            raise Exception(f"获取账户信息失败: {e}")
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有持仓"""
        try:
            positions = self.client.futures_position_information()
            
            result = []
            for pos in positions:
                pos_amt = float(pos["positionAmt"])
                if pos_amt == 0:
                    continue  # 跳过无持仓的
                
                pos_dict = {
                    "symbol": pos["symbol"],
                    "position_amt": pos_amt,
                    "entry_price": float(pos["entryPrice"]),
                    "mark_price": float(pos["markPrice"]),
                    "un_realized_profit": float(pos["unRealizedProfit"]),
                    "leverage": float(pos["leverage"]),
                    "liquidation_price": float(pos["liquidationPrice"]),
                }
                
                # 判断方向
                if pos_amt > 0:
                    pos_dict["side"] = "long"
                else:
                    pos_dict["side"] = "short"
                
                result.append(pos_dict)
            
            return result
        except BinanceAPIException as e:
            raise Exception(f"获取持仓失败: {e}")
    
    def set_leverage(self, symbol: str, leverage: int) -> None:
        """设置杠杆（智能判断+冷却期）"""
        # 先尝试获取当前杠杆（从持仓信息）
        current_leverage = 0
        try:
            positions = self.get_positions()
            for pos in positions:
                if pos["symbol"] == symbol:
                    current_leverage = int(pos["leverage"])
                    break
        except Exception:
            pass
        
        # 如果当前杠杆已经是目标杠杆，跳过
        if current_leverage == leverage and current_leverage > 0:
            logging.info(f"  ✓ {symbol} 杠杆已是 {leverage}x，无需切换")
            return
        
        # 切换杠杆
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logging.info(f"  ✓ {symbol} 杠杆已切换为 {leverage}x")
            
            # 切换杠杆后等待5秒（避免冷却期错误）
            logging.info("  ⏱ 等待5秒冷却期...")
            time.sleep(5)
        except BinanceAPIException as e:
            # 如果错误信息包含"No need to change"，说明杠杆已经是目标值
            if "No need to change" in str(e):
                logging.info(f"  ✓ {symbol} 杠杆已是 {leverage}x")
                return
            raise Exception(f"设置杠杆失败: {e}")
    
    def open_long(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开多仓"""
        # 先取消该币种的所有委托单（清理旧的止损止盈单）
        try:
            self.cancel_all_orders(symbol)
        except Exception as e:
            logging.warning(f"  ⚠ 取消旧委托单失败（可能没有委托单）: {e}")
        
        # 设置杠杆
        self.set_leverage(symbol, leverage)
        
        # 设置逐仓模式
        try:
            self.client.futures_change_margin_type(symbol=symbol, marginType="ISOLATED")
            logging.info(f"  ✓ {symbol} 保证金模式已切换为 ISOLATED")
            
            # 切换保证金模式后等待3秒（避免冷却期错误）
            logging.info("  ⏱ 等待3秒冷却期...")
            time.sleep(3)
        except BinanceAPIException as e:
            # 如果已经是该模式，不算错误
            if "No need to change" in str(e):
                logging.info(f"  ✓ {symbol} 保证金模式已是 ISOLATED")
            else:
                raise Exception(f"设置保证金模式失败: {e}")
        
        # 格式化数量到正确精度
        quantity_str = self._format_quantity(symbol, quantity)
        
        # 创建市价买入订单
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                positionSide=POSITION_SIDE_LONG,
                type=ORDER_TYPE_MARKET,
                quantity=quantity_str,
            )
            
            logging.info(f"✓ 开多仓成功: {symbol} 数量: {quantity_str}")
            logging.info(f"  订单ID: {order['orderId']}")
            
            result = {
                "order_id": order["orderId"],
                "symbol": order["symbol"],
                "status": order["status"],
            }
            return result
        except BinanceAPIException as e:
            raise Exception(f"开多仓失败: {e}")
    
    def open_short(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开空仓"""
        # 先取消该币种的所有委托单（清理旧的止损止盈单）
        try:
            self.cancel_all_orders(symbol)
        except Exception as e:
            logging.warning(f"  ⚠ 取消旧委托单失败（可能没有委托单）: {e}")
        
        # 设置杠杆
        self.set_leverage(symbol, leverage)
        
        # 设置逐仓模式
        try:
            self.client.futures_change_margin_type(symbol=symbol, marginType="ISOLATED")
            logging.info(f"  ✓ {symbol} 保证金模式已切换为 ISOLATED")
            
            # 切换保证金模式后等待3秒（避免冷却期错误）
            logging.info("  ⏱ 等待3秒冷却期...")
            time.sleep(3)
        except BinanceAPIException as e:
            # 如果已经是该模式，不算错误
            if "No need to change" in str(e):
                logging.info(f"  ✓ {symbol} 保证金模式已是 ISOLATED")
            else:
                raise Exception(f"设置保证金模式失败: {e}")
        
        # 格式化数量到正确精度
        quantity_str = self._format_quantity(symbol, quantity)
        
        # 创建市价卖出订单
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                positionSide=POSITION_SIDE_SHORT,
                type=ORDER_TYPE_MARKET,
                quantity=quantity_str,
            )
            
            logging.info(f"✓ 开空仓成功: {symbol} 数量: {quantity_str}")
            logging.info(f"  订单ID: {order['orderId']}")
            
            result = {
                "order_id": order["orderId"],
                "symbol": order["symbol"],
                "status": order["status"],
            }
            return result
        except BinanceAPIException as e:
            raise Exception(f"开空仓失败: {e}")
    
    def close_long(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平多仓"""
        # 如果数量为0，获取当前持仓数量
        if quantity == 0:
            positions = self.get_positions()
            for pos in positions:
                if pos["symbol"] == symbol and pos["side"] == "long":
                    quantity = pos["position_amt"]
                    break
            
            if quantity == 0:
                raise Exception(f"没有找到 {symbol} 的多仓")
        
        # 格式化数量
        quantity_str = self._format_quantity(symbol, quantity)
        
        # 创建市价卖出订单（平多）
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                positionSide=POSITION_SIDE_LONG,
                type=ORDER_TYPE_MARKET,
                quantity=quantity_str,
            )
            
            logging.info(f"✓ 平多仓成功: {symbol} 数量: {quantity_str}")
            
            # 平仓后取消该币种的所有挂单（止损止盈单）
            try:
                self.cancel_all_orders(symbol)
            except Exception as e:
                logging.warning(f"  ⚠ 取消挂单失败: {e}")
            
            result = {
                "order_id": order["orderId"],
                "symbol": order["symbol"],
                "status": order["status"],
            }
            return result
        except BinanceAPIException as e:
            raise Exception(f"平多仓失败: {e}")
    
    def close_short(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平空仓"""
        # 如果数量为0，获取当前持仓数量
        if quantity == 0:
            positions = self.get_positions()
            for pos in positions:
                if pos["symbol"] == symbol and pos["side"] == "short":
                    quantity = -pos["position_amt"]  # 空仓数量是负的，取绝对值
                    break
            
            if quantity == 0:
                raise Exception(f"没有找到 {symbol} 的空仓")
        
        # 格式化数量
        quantity_str = self._format_quantity(symbol, quantity)
        
        # 创建市价买入订单（平空）
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                positionSide=POSITION_SIDE_SHORT,
                type=ORDER_TYPE_MARKET,
                quantity=quantity_str,
            )
            
            logging.info(f"✓ 平空仓成功: {symbol} 数量: {quantity_str}")
            
            # 平仓后取消该币种的所有挂单（止损止盈单）
            try:
                self.cancel_all_orders(symbol)
            except Exception as e:
                logging.warning(f"  ⚠ 取消挂单失败: {e}")
            
            result = {
                "order_id": order["orderId"],
                "symbol": order["symbol"],
                "status": order["status"],
            }
            return result
        except BinanceAPIException as e:
            raise Exception(f"平空仓失败: {e}")
    
    def cancel_all_orders(self, symbol: str) -> None:
        """取消该币种的所有挂单"""
        try:
            self.client.futures_cancel_all_orders(symbol=symbol)
            logging.info(f"  ✓ 已取消 {symbol} 的所有挂单")
        except BinanceAPIException as e:
            raise Exception(f"取消挂单失败: {e}")
    
    def get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker["price"])
        except BinanceAPIException as e:
            raise Exception(f"获取价格失败: {e}")
    
    def calculate_position_size(self, balance: float, risk_percent: float, price: float, leverage: int) -> float:
        """计算仓位大小"""
        risk_amount = balance * (risk_percent / 100.0)
        position_value = risk_amount * float(leverage)
        quantity = position_value / price
        return quantity
    
    def set_stop_loss(self, symbol: str, position_side: str, quantity: float, stop_price: float) -> None:
        """设置止损单"""
        side = SIDE_SELL if position_side == "LONG" else SIDE_BUY
        pos_side = POSITION_SIDE_LONG if position_side == "LONG" else POSITION_SIDE_SHORT
        
        # 格式化数量
        quantity_str = self._format_quantity(symbol, quantity)
        
        try:
            self.client.futures_create_order(
                symbol=symbol,
                side=side,
                positionSide=pos_side,
                type=ORDER_TYPE_STOP_MARKET,
                stopPrice=str(stop_price),
                quantity=quantity_str,
                workingType="CONTRACT_PRICE",
                closePosition=True,
            )
            
            logging.info(f"  止损价设置: {stop_price:.4f}")
        except BinanceAPIException as e:
            raise Exception(f"设置止损失败: {e}")
    
    def set_take_profit(self, symbol: str, position_side: str, quantity: float, take_profit_price: float) -> None:
        """设置止盈单"""
        side = SIDE_SELL if position_side == "LONG" else SIDE_BUY
        pos_side = POSITION_SIDE_LONG if position_side == "LONG" else POSITION_SIDE_SHORT
        
        # 格式化数量
        quantity_str = self._format_quantity(symbol, quantity)
        
        try:
            self.client.futures_create_order(
                symbol=symbol,
                side=side,
                positionSide=pos_side,
                type=ORDER_TYPE_TAKE_PROFIT_MARKET,
                stopPrice=str(take_profit_price),
                quantity=quantity_str,
                workingType="CONTRACT_PRICE",
                closePosition=True,
            )
            
            logging.info(f"  止盈价设置: {take_profit_price:.4f}")
        except BinanceAPIException as e:
            raise Exception(f"设置止盈失败: {e}")
    
    def _get_symbol_precision(self, symbol: str) -> int:
        """获取交易对的数量精度"""
        try:
            exchange_info = self.client.futures_exchange_info()
            for s in exchange_info["symbols"]:
                if s["symbol"] == symbol:
                    # 从LOT_SIZE filter获取精度
                    for f in s["filters"]:
                        if f["filterType"] == "LOT_SIZE":
                            step_size = f["stepSize"]
                            precision = self._calculate_precision(step_size)
                            logging.info(f"  {symbol} 数量精度: {precision} (stepSize: {step_size})")
                            return precision
            logging.warning(f"  ⚠ {symbol} 未找到精度信息，使用默认精度3")
            return 3  # 默认精度为3
        except BinanceAPIException as e:
            logging.warning(f"  ⚠ 获取 {symbol} 精度失败: {e}，使用默认精度3")
            return 3  # 默认精度为3
    
    def _calculate_precision(self, step_size: str) -> int:
        """从stepSize计算精度"""
        # 去除尾部的0
        step_size = self._trim_trailing_zeros(step_size)
        
        # 查找小数点
        dot_index = -1
        for i, char in enumerate(step_size):
            if char == '.':
                dot_index = i
                break
        
        # 如果没有小数点或小数点在最后，精度为0
        if dot_index == -1 or dot_index == len(step_size) - 1:
            return 0
        
        # 返回小数点后的位数
        return len(step_size) - dot_index - 1
    
    def _trim_trailing_zeros(self, s: str) -> str:
        """去除尾部的0"""
        # 如果没有小数点，直接返回
        if '.' not in s:
            return s
        
        # 从后向前遍历，去除尾部的0
        while s and s[-1] == '0':
            s = s[:-1]
        
        # 如果最后一位是小数点，也去掉
        if s and s[-1] == '.':
            s = s[:-1]
        
        return s
    
    def _format_quantity(self, symbol: str, quantity: float) -> str:
        """格式化数量到正确的精度"""
        try:
            precision = self._get_symbol_precision(symbol)
            format_str = f"{{:.{precision}f}}"
            return format_str.format(quantity)
        except Exception:
            # 如果获取失败，使用默认格式
            return f"{quantity:.3f}"