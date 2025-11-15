#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid交易器测试程序
用于测试下单和撤单功能
"""

import sys
import os
import logging
import time
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.config import load_config
from trader.hyperliquid_trader import HyperliquidTrader

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def find_hyperliquid_trader_config(config_path: str = "config.json") -> Dict[str, Any]:
    """从配置文件中查找Hyperliquid交易器配置"""
    try:
        config = load_config(config_path)
        for trader_config in config.traders:
            if trader_config.exchange == "hyperliquid" and trader_config.enabled:
                return {
                    "private_key": trader_config.hyperliquid_private_key,
                    "testnet": trader_config.hyperliquid_testnet
                }
        raise ValueError("未找到启用的Hyperliquid交易器配置")
    except Exception as e:
        logger.error(f"读取配置失败: {e}")
        raise


def test_hyperliquid_trading():
    """测试Hyperliquid交易功能"""
    logger.info("开始测试Hyperliquid交易功能...")
    
    try:
        # 1. 读取配置
        trader_info = find_hyperliquid_trader_config()
        logger.info("✓ 成功读取Hyperliquid配置")
        
        # 2. 初始化交易器
        trader = HyperliquidTrader(
            private_key=trader_info["private_key"],
            testnet=trader_info["testnet"]
        )
        logger.info("✓ Hyperliquid交易器初始化成功")
        
        # 3. 获取账户余额
        logger.info("正在获取账户余额...")
        balance = trader.get_balance()
        logger.info(f"账户余额: {balance}")
        
        # 4. 获取当前持仓
        logger.info("正在获取当前持仓...")
        positions = trader.get_positions()
        logger.info(f"当前持仓数量: {len(positions)}")
        for pos in positions:
            logger.info(f"  - {pos['symbol']}: {pos['side']} {pos['position_amt']} @ {pos['entry_price']}")
        
        # 5. 测试下单功能 - 使用小量测试
        test_symbol = "ETHUSDT"  # 使用ETH进行测试
        test_quantity = 0.01     # 测试数量
        test_leverage = 5        # 测试杠杆
        
        logger.info(f"开始测试下单功能: {test_symbol}, 数量: {test_quantity}, 杠杆: {test_leverage}x")
        
        # 5.1 获取当前价格
        market_price = trader.get_market_price(test_symbol)
        logger.info(f"当前市场价格: {market_price}")
        
        # 5.2 开多仓测试
        logger.info("执行开多仓操作...")
        open_long_result = trader.open_long(test_symbol, test_quantity, test_leverage)
        logger.info(f"开多仓结果: {open_long_result}")
        
        # 等待一段时间确保订单执行
        time.sleep(2)
        
        # 5.3 检查持仓变化
        new_positions = trader.get_positions()
        logger.info(f"开仓后持仓数量: {len(new_positions)}")
        for pos in new_positions:
            if pos["symbol"] == test_symbol:
                logger.info(f"  - {pos['symbol']}: {pos['side']} {pos['position_amt']} @ {pos['entry_price']}")
        
        # 5.4 平多仓测试
        logger.info("执行平多仓操作...")
        close_long_result = trader.close_long(test_symbol, test_quantity)
        logger.info(f"平多仓结果: {close_long_result}")
        
        # 等待一段时间确保订单执行
        time.sleep(2)
        
        # 5.5 再次检查持仓
        final_positions = trader.get_positions()
        logger.info(f"平仓后持仓数量: {len(final_positions)}")
        for pos in final_positions:
            if pos["symbol"] == test_symbol:
                logger.info(f"  - {pos['symbol']}: {pos['side']} {pos['position_amt']} @ {pos['entry_price']}")
        
        # 6. 测试限价单和撤单功能
        logger.info("测试限价单下单和撤单功能...")
        
        # 6.1 设置一个远离市价的限价单（确保不会立即成交）
        limit_price = market_price * 0.95  # 设置一个比市价低5%的买单（不会立即成交）
        logger.info(f"下单价格: {limit_price:.4f}, 市价: {market_price:.4f}")
        
        # 6.2 下一个限价买单
        coin = trader._convert_symbol_to_hyperliquid(test_symbol)
        rounded_quantity = trader._round_to_sz_decimals(coin, test_quantity)
        rounded_price = trader._round_price_to_sigfigs(limit_price)
        
        logger.info(f"下单参数 - 币种: {coin}, 数量: {rounded_quantity}, 价格: {rounded_price}")
        
        # 使用exchange直接下单（限价单）
        order_type = {"limit": {"tif": "Gtc"}}  # Good till cancel
        order_result = trader.exchange.order(
            name=coin,
            is_buy=True,
            sz=rounded_quantity,
            limit_px=rounded_price,
            order_type=order_type,
            reduce_only=False
        )
        logger.info(f"限价单下单结果: {order_result}")
        
        # 等待一下确保订单已提交
        time.sleep(2)
        
        # 6.3 查询挂单
        logger.info("查询当前挂单...")
        open_orders = trader.info.open_orders(trader.wallet_address)
        logger.info(f"当前挂单数量: {len(open_orders)}")
        # 打印订单结构用于调试
        logger.info(f"订单结构: {open_orders}")
        for order in open_orders:
            if order["coin"] == coin:
                # 使用正确的字段名
                direction = '买入' if order.get('side', '') == 'B' else '卖出'
                logger.info(f"  - 订单ID: {order.get('oid', 'N/A')}, 方向: {direction}, 数量: {order.get('sz', 'N/A')}, 价格: {order.get('limitPx', 'N/A')}")
        
        # 6.4 撤单测试
        logger.info("执行撤单操作...")
        if open_orders:
            for order in open_orders:
                if order["coin"] == coin:
                    trader.exchange.cancel(coin, order["oid"])
                    logger.info(f"  ✓ 已撤销订单: {order['oid']}")
        else:
            logger.info("  没有找到可撤销的订单")
        
        # 6.5 验证撤单结果
        time.sleep(1)
        remaining_orders = trader.info.open_orders(trader.wallet_address)
        remaining_coin_orders = [o for o in remaining_orders if o["coin"] == coin]
        logger.info(f"撤单后剩余{coin}挂单数量: {len(remaining_coin_orders)}")
        
        logger.info("✓ Hyperliquid交易功能测试完成!")
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        raise


if __name__ == "__main__":
    test_hyperliquid_trading()