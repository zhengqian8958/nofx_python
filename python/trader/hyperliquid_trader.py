import time
import logging
from typing import Dict, List, Any, Optional
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL
from eth_account import Account
from .interface import Trader


class HyperliquidTrader(Trader):
    """Hyperliquid交易器"""
    
    def __init__(self, private_key: str, testnet: bool = False):
        """
        初始化Hyperliquid交易器
        
        Args:
            private_key: 私钥（十六进制格式，带0x前缀）
            testnet: 是否使用测试网
        """
        # 选择API URL
        api_url = TESTNET_API_URL if testnet else MAINNET_API_URL
        
        # 从私钥生成钱包地址
        account = Account.from_key(private_key)
        self.wallet_address = account.address
        
        # 创建Info和Exchange客户端
        self.info = Info(api_url, skip_ws=True)
        self.exchange = Exchange(account, api_url)
        
        # 获取meta信息（包含精度等配置）
        self.meta = self.info.meta()
        
        logging.info(f"✓ Hyperliquid交易器初始化成功 (testnet={testnet}, wallet={self.wallet_address})")
    
    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        logging.info("🔄 正在调用Hyperliquid API获取账户余额...")
        
        try:
            # 获取账户状态
            user_state = self.info.user_state(self.wallet_address)
            
            # 解析余额信息
            account_value = float(user_state["crossMarginSummary"]["accountValue"])
            total_margin_used = float(user_state["crossMarginSummary"]["totalMarginUsed"])
            
            # 关键修复：从所有持仓中累加真正的未实现盈亏
            total_unrealized_pnl = 0.0
            for asset_pos in user_state["assetPositions"]:
                unrealized_pnl = float(asset_pos["position"]["unrealizedPnl"])
                total_unrealized_pnl += unrealized_pnl
            
            # 正确理解Hyperliquid字段：
            # AccountValue = 账户净值（包含未实现盈亏）= 这是真正的总资产
            # 钱包余额（已实现）= AccountValue - 未实现盈亏
            wallet_balance = account_value - total_unrealized_pnl
            
            result = {
                "total_wallet_balance": wallet_balance,        # 钱包余额（已实现部分）
                "available_balance": account_value - total_margin_used,  # 可用余额
                "total_unrealized_profit": total_unrealized_pnl,         # 未实现盈亏
            }
            
            logging.info(f"✓ Hyperliquid API返回: 账户净值={account_value:.2f}, 钱包余额={result['total_wallet_balance']:.2f}, 可用={result['available_balance']:.2f}, 未实现盈亏={result['total_unrealized_profit']:.2f}")
            return result
        except Exception as e:
            logging.error(f"❌ Hyperliquid API调用失败: {e}")
            raise Exception(f"获取账户信息失败: {e}")
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有持仓"""
        try:
            # 获取账户状态
            user_state = self.info.user_state(self.wallet_address)
            
            result = []
            
            # 遍历所有持仓
            for asset_pos in user_state["assetPositions"]:
                position = asset_pos["position"]
                
                # 持仓数量
                pos_amt = float(position["szi"])
                
                if pos_amt == 0:
                    continue  # 跳过无持仓的
                
                pos_dict = {}
                
                # 标准化symbol格式（Hyperliquid使用如"BTC"，我们转换为"BTCUSDT"）
                symbol = position["coin"] + "USDT"
                pos_dict["symbol"] = symbol
                
                # 持仓数量和方向
                if pos_amt > 0:
                    pos_dict["side"] = "long"
                    pos_dict["position_amt"] = pos_amt
                else:
                    pos_dict["side"] = "short"
                    pos_dict["position_amt"] = -pos_amt  # 转为正数
                
                # 价格信息
                entry_price = 0.0
                liquidation_px = 0.0
                if position["entryPx"] is not None:
                    entry_price = float(position["entryPx"])
                if position["liquidationPx"] is not None:
                    liquidation_px = float(position["liquidationPx"])
                
                position_value = float(position["positionValue"])
                unrealized_pnl = float(position["unrealizedPnl"])
                
                # 计算mark price（positionValue / abs(posAmt)）
                mark_price = 0.0
                if pos_amt != 0:
                    mark_price = position_value / abs(pos_amt)
                
                pos_dict["entry_price"] = entry_price
                pos_dict["mark_price"] = mark_price
                pos_dict["un_realized_profit"] = unrealized_pnl
                pos_dict["leverage"] = float(position["leverage"]["value"])
                pos_dict["liquidation_price"] = liquidation_px
                
                result.append(pos_dict)
            
            return result
        except Exception as e:
            raise Exception(f"获取持仓失败: {e}")
    
    def set_leverage(self, symbol: str, leverage: int) -> None:
        """设置杠杆"""
        try:
            # Hyperliquid symbol格式（去掉USDT后缀）
            coin = self._convert_symbol_to_hyperliquid(symbol)
            
            # 调用update_leverage (leverage: int, coin: str, is_cross: bool)
            # false = 逐仓模式
            self.exchange.update_leverage(leverage, coin, False)
            
            logging.info(f"  ✓ {symbol} 杠杆已切换为 {leverage}x")
        except Exception as e:
            raise Exception(f"设置杠杆失败: {e}")
    
    def open_long(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开多仓"""
        # 先取消该币种的所有委托单
        try:
            self.cancel_all_orders(symbol)
        except Exception as e:
            logging.warning(f"  ⚠ 取消旧委托单失败: {e}")
        
        # 设置杠杆
        self.set_leverage(symbol, leverage)
        
        # Hyperliquid symbol格式
        coin = self._convert_symbol_to_hyperliquid(symbol)
        
        # 获取当前价格（用于市价单）
        price = self.get_market_price(symbol)
        
        # 关键：根据币种精度要求，四舍五入数量
        rounded_quantity = self._round_to_sz_decimals(coin, quantity)
        logging.info(f"  📏 数量精度处理: {quantity:.8f} -> {rounded_quantity:.8f} (szDecimals={self._get_sz_decimals(coin)})")
        
        # 关键：价格也需要处理为5位有效数字
        aggressive_price = self._round_price_to_sigfigs(price * 1.01)
        logging.info(f"  💰 价格精度处理: {price*1.01:.8f} -> {aggressive_price:.8f} (5位有效数字)")
        
        # 创建市价买入订单（使用IOC limit order with aggressive price）
        order_type = {"limit": {"tif": "Ioc"}}  # Immediate or Cancel (类似市价单)
        
        try:
            order_result = self.exchange.order(
                coin=coin,
                is_buy=True,
                sz=rounded_quantity,  # 使用四舍五入后的数量
                limit_px=aggressive_price,  # 使用处理后的价格
                order_type=order_type,
                reduce_only=False
            )
            
            logging.info(f"✓ 开多仓成功: {symbol} 数量: {rounded_quantity}")
            
            result = {
                "order_id": 0,  # Hyperliquid没有返回order ID
                "symbol": symbol,
                "status": "FILLED",
            }
            return result
        except Exception as e:
            raise Exception(f"开多仓失败: {e}")
    
    def open_short(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开空仓"""
        # 先取消该币种的所有委托单
        try:
            self.cancel_all_orders(symbol)
        except Exception as e:
            logging.warning(f"  ⚠ 取消旧委托单失败: {e}")
        
        # 设置杠杆
        self.set_leverage(symbol, leverage)
        
        # Hyperliquid symbol格式
        coin = self._convert_symbol_to_hyperliquid(symbol)
        
        # 获取当前价格
        price = self.get_market_price(symbol)
        
        # 关键：根据币种精度要求，四舍五入数量
        rounded_quantity = self._round_to_sz_decimals(coin, quantity)
        logging.info(f"  📏 数量精度处理: {quantity:.8f} -> {rounded_quantity:.8f} (szDecimals={self._get_sz_decimals(coin)})")
        
        # 关键：价格也需要处理为5位有效数字
        aggressive_price = self._round_price_to_sigfigs(price * 0.99)
        logging.info(f"  💰 价格精度处理: {price*0.99:.8f} -> {aggressive_price:.8f} (5位有效数字)")
        
        # 创建市价卖出订单
        order_type = {"limit": {"tif": "Ioc"}}
        
        try:
            order_result = self.exchange.order(
                coin=coin,
                is_buy=False,
                sz=rounded_quantity,  # 使用四舍五入后的数量
                limit_px=aggressive_price,  # 使用处理后的价格
                order_type=order_type,
                reduce_only=False
            )
            
            logging.info(f"✓ 开空仓成功: {symbol} 数量: {rounded_quantity}")
            
            result = {
                "order_id": 0,
                "symbol": symbol,
                "status": "FILLED",
            }
            return result
        except Exception as e:
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
        
        # Hyperliquid symbol格式
        coin = self._convert_symbol_to_hyperliquid(symbol)
        
        # 获取当前价格
        price = self.get_market_price(symbol)
        
        # 关键：根据币种精度要求，四舍五入数量
        rounded_quantity = self._round_to_sz_decimals(coin, quantity)
        logging.info(f"  📏 数量精度处理: {quantity:.8f} -> {rounded_quantity:.8f} (szDecimals={self._get_sz_decimals(coin)})")
        
        # 关键：价格也需要处理为5位有效数字
        aggressive_price = self._round_price_to_sigfigs(price * 0.99)
        logging.info(f"  💰 价格精度处理: {price*0.99:.8f} -> {aggressive_price:.8f} (5位有效数字)")
        
        # 创建平仓订单（卖出 + ReduceOnly）
        order_type = {"limit": {"tif": "Ioc"}}
        
        try:
            order_result = self.exchange.order(
                coin=coin,
                is_buy=False,
                sz=rounded_quantity,  # 使用四舍五入后的数量
                limit_px=aggressive_price,  # 使用处理后的价格
                order_type=order_type,
                reduce_only=True  # 只平仓，不开新仓
            )
            
            logging.info(f"✓ 平多仓成功: {symbol} 数量: {rounded_quantity}")
            
            # 平仓后取消该币种的所有挂单
            try:
                self.cancel_all_orders(symbol)
            except Exception as e:
                logging.warning(f"  ⚠ 取消挂单失败: {e}")
            
            result = {
                "order_id": 0,
                "symbol": symbol,
                "status": "FILLED",
            }
            return result
        except Exception as e:
            raise Exception(f"平多仓失败: {e}")
    
    def close_short(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平空仓"""
        # 如果数量为0，获取当前持仓数量
        if quantity == 0:
            positions = self.get_positions()
            for pos in positions:
                if pos["symbol"] == symbol and pos["side"] == "short":
                    quantity = pos["position_amt"]
                    break
            
            if quantity == 0:
                raise Exception(f"没有找到 {symbol} 的空仓")
        
        # Hyperliquid symbol格式
        coin = self._convert_symbol_to_hyperliquid(symbol)
        
        # 获取当前价格
        price = self.get_market_price(symbol)
        
        # 关键：根据币种精度要求，四舍五入数量
        rounded_quantity = self._round_to_sz_decimals(coin, quantity)
        logging.info(f"  📏 数量精度处理: {quantity:.8f} -> {rounded_quantity:.8f} (szDecimals={self._get_sz_decimals(coin)})")
        
        # 关键：价格也需要处理为5位有效数字
        aggressive_price = self._round_price_to_sigfigs(price * 1.01)
        logging.info(f"  💰 价格精度处理: {price*1.01:.8f} -> {aggressive_price:.8f} (5位有效数字)")
        
        # 创建平仓订单（买入 + ReduceOnly）
        order_type = {"limit": {"tif": "Ioc"}}
        
        try:
            order_result = self.exchange.order(
                coin=coin,
                is_buy=True,
                sz=rounded_quantity,  # 使用四舍五入后的数量
                limit_px=aggressive_price,  # 使用处理后的价格
                order_type=order_type,
                reduce_only=True
            )
            
            logging.info(f"✓ 平空仓成功: {symbol} 数量: {rounded_quantity}")
            
            # 平仓后取消该币种的所有挂单
            try:
                self.cancel_all_orders(symbol)
            except Exception as e:
                logging.warning(f"  ⚠ 取消挂单失败: {e}")
            
            result = {
                "order_id": 0,
                "symbol": symbol,
                "status": "FILLED",
            }
            return result
        except Exception as e:
            raise Exception(f"平空仓失败: {e}")
    
    def cancel_all_orders(self, symbol: str) -> None:
        """取消该币种的所有挂单"""
        try:
            coin = self._convert_symbol_to_hyperliquid(symbol)
            
            # 获取所有挂单
            open_orders = self.info.open_orders(self.wallet_address)
            
            # 取消该币种的所有挂单
            for order in open_orders:
                if order["coin"] == coin:
                    self.exchange.cancel(coin, order["oid"])
            
            logging.info(f"  ✓ 已取消 {symbol} 的所有挂单")
        except Exception as e:
            raise Exception(f"取消挂单失败: {e}")
    
    def get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        try:
            coin = self._convert_symbol_to_hyperliquid(symbol)
            
            # 获取所有市场价格
            all_mids = self.info.all_mids()
            
            # 查找对应币种的价格
            if coin in all_mids:
                return float(all_mids[coin])
            
            raise Exception(f"未找到 {symbol} 的价格")
        except Exception as e:
            raise Exception(f"获取价格失败: {e}")
    
    def calculate_position_size(self, balance: float, risk_percent: float, price: float, leverage: int) -> float:
        """计算仓位大小"""
        risk_amount = balance * (risk_percent / 100.0)
        position_value = risk_amount * float(leverage)
        quantity = position_value / price
        return quantity
    
    def set_stop_loss(self, symbol: str, position_side: str, quantity: float, stop_price: float) -> None:
        """设置止损单"""
        try:
            coin = self._convert_symbol_to_hyperliquid(symbol)
            
            is_buy = position_side == "SHORT"  # 空仓止损=买入，多仓止损=卖出
            
            # 关键：根据币种精度要求，四舍五入数量
            rounded_quantity = self._round_to_sz_decimals(coin, quantity)
            
            # 关键：价格也需要处理为5位有效数字
            rounded_stop_price = self._round_price_to_sigfigs(stop_price)
            
            # 创建止损单（Trigger Order）
            order_type = {
                "trigger": {
                    "triggerPx": str(rounded_stop_price),
                    "isMarket": True,
                    "tpsl": "sl"  # stop loss
                }
            }
            
            self.exchange.order(
                coin=coin,
                is_buy=is_buy,
                sz=rounded_quantity,    # 使用四舍五入后的数量
                limit_px=rounded_stop_price,   # 使用处理后的价格
                order_type=order_type,
                reduce_only=True
            )
            
            logging.info(f"  止损价设置: {rounded_stop_price:.4f}")
        except Exception as e:
            raise Exception(f"设置止损失败: {e}")
    
    def set_take_profit(self, symbol: str, position_side: str, quantity: float, take_profit_price: float) -> None:
        """设置止盈单"""
        try:
            coin = self._convert_symbol_to_hyperliquid(symbol)
            
            is_buy = position_side == "SHORT"  # 空仓止盈=买入，多仓止盈=卖出
            
            # 关键：根据币种精度要求，四舍五入数量
            rounded_quantity = self._round_to_sz_decimals(coin, quantity)
            
            # 关键：价格也需要处理为5位有效数字
            rounded_take_profit_price = self._round_price_to_sigfigs(take_profit_price)
            
            # 创建止盈单（Trigger Order）
            order_type = {
                "trigger": {
                    "triggerPx": str(rounded_take_profit_price),
                    "isMarket": True,
                    "tpsl": "tp"  # take profit
                }
            }
            
            self.exchange.order(
                coin=coin,
                is_buy=is_buy,
                sz=rounded_quantity,          # 使用四舍五入后的数量
                limit_px=rounded_take_profit_price,   # 使用处理后的价格
                order_type=order_type,
                reduce_only=True
            )
            
            logging.info(f"  止盈价设置: {rounded_take_profit_price:.4f}")
        except Exception as e:
            raise Exception(f"设置止盈失败: {e}")
    
    def _convert_symbol_to_hyperliquid(self, symbol: str) -> str:
        """将标准symbol转换为Hyperliquid格式"""
        # 去掉USDT后缀
        if len(symbol) > 4 and symbol.endswith("USDT"):
            return symbol[:-4]
        return symbol
    
    def _get_sz_decimals(self, coin: str) -> int:
        """获取币种的数量精度"""
        if self.meta is None:
            logging.warning("⚠️  meta信息为空，使用默认精度4")
            return 4  # 默认精度
        
        # 在meta.universe中查找对应的币种
        for asset in self.meta["universe"]:
            if asset["name"] == coin:
                return asset["szDecimals"]
        
        logging.warning(f"⚠️  未找到 {coin} 的精度信息，使用默认精度4")
        return 4  # 默认精度
    
    def _round_to_sz_decimals(self, coin: str, quantity: float) -> float:
        """将数量四舍五入到正确的精度"""
        sz_decimals = self._get_sz_decimals(coin)
        
        # 计算倍数（10^szDecimals）
        multiplier = 1.0
        for i in range(sz_decimals):
            multiplier *= 10.0
        
        # 四舍五入
        return round(quantity * multiplier) / multiplier
    
    def _round_price_to_sigfigs(self, price: float) -> float:
        """将价格四舍五入到5位有效数字"""
        if price == 0:
            return 0
        
        sigfigs = 5  # Hyperliquid标准：5位有效数字
        
        # 计算价格的数量级
        magnitude = abs(price)
        
        # 计算需要的倍数
        multiplier = 1.0
        while magnitude >= 10:
            magnitude /= 10
            multiplier /= 10
        while magnitude < 1:
            magnitude *= 10
            multiplier *= 10
        
        # 应用有效数字精度
        for i in range(sigfigs - 1):
            multiplier *= 10
        
        # 四舍五入
        rounded = round(price * multiplier) / multiplier
        return rounded