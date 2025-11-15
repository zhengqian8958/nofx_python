#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试脚本，用于查看Hyperliquid订单结构
"""

import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.config import load_config
from trader.hyperliquid_trader import HyperliquidTrader

def debug_orders():
    """调试订单结构"""
    try:
        # 读取配置
        config = load_config()
        for trader_config in config.traders:
            if trader_config.exchange == "hyperliquid" and trader_config.enabled:
                # 初始化交易器
                trader = HyperliquidTrader(
                    private_key=trader_config.hyperliquid_private_key or "",
                    testnet=trader_config.hyperliquid_testnet
                )
                
                # 获取挂单
                open_orders = trader.info.open_orders(trader.wallet_address)
                print("Open orders structure:")
                print(json.dumps(open_orders, indent=2, default=str))
                break
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_orders()