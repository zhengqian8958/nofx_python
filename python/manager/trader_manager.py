import logging
import time
import sys
import os
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from threading import Lock, Thread

# 添加项目根目录到sys.path，使绝对导入可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用绝对导入替代相对导入
from config.config import Config, TraderConfig
# 导入AutoTrader类
from trader.auto_trader import AutoTrader, AutoTraderConfig
import threading

if TYPE_CHECKING:
    from trader.auto_trader import AutoTrader, AutoTraderConfig


class TraderManager:
    """管理多个trader实例"""
    
    def __init__(self):
        self.traders: Dict[str, AutoTrader] = {}
        self.lock = Lock()
        self.trader_threads: Dict[str, Thread] = {}
    
    def add_trader(self, cfg: TraderConfig, coin_pool_url: str, max_daily_loss: float, 
                   max_drawdown: float, stop_trading_minutes: int, leverage_config: Any) -> None:
        """添加一个trader"""
        with self.lock:
            if cfg.id in self.traders:
                raise Exception(f"trader ID '{cfg.id}' 已存在")
            
            # 添加调试信息
            print(f"DEBUG: Adding trader {cfg.name} with AI model {cfg.ai_model}")
            print(f"DEBUG: DeepSeek key: {cfg.deepseek_key[:10] if cfg.deepseek_key else None}")
            print(f"DEBUG: Qwen key: {cfg.qwen_key[:10] if cfg.qwen_key else None}")
            print(f"DEBUG: Custom API URL: {cfg.custom_api_url}")
            print(f"DEBUG: Custom API key: {cfg.custom_api_key[:10] if cfg.custom_api_key else None}")
            print(f"DEBUG: Custom model name: {cfg.custom_model_name}")
            
            # 构建AutoTraderConfig
            trader_config = AutoTraderConfig(
                id=cfg.id,
                name=cfg.name,
                ai_model=cfg.ai_model,
                exchange=cfg.exchange,
                binance_api_key=cfg.binance_api_key,
                binance_secret_key=cfg.binance_secret_key,
                hyperliquid_private_key=cfg.hyperliquid_private_key,
                hyperliquid_testnet=cfg.hyperliquid_testnet,
                aster_user=cfg.aster_user,
                aster_signer=cfg.aster_signer,
                aster_private_key=cfg.aster_private_key,
                coin_pool_api_url=coin_pool_url,
                use_qwen=cfg.ai_model == "qwen",
                deepseek_key=cfg.deepseek_key,
                qwen_key=cfg.qwen_key,
                custom_api_url=cfg.custom_api_url,
                custom_api_key=cfg.custom_api_key,
                custom_model_name=cfg.custom_model_name,
                scan_interval_minutes=cfg.scan_interval_minutes,
                initial_balance=cfg.initial_balance,
                btc_eth_leverage=leverage_config.btc_eth_leverage,  # 使用配置的杠杆倍数
                altcoin_leverage=leverage_config.altcoin_leverage,   # 使用配置的杠杆倍数
                max_daily_loss=max_daily_loss,
                max_drawdown=max_drawdown,
                stop_trading_time=stop_trading_minutes * 60,  # 转换为秒
            )
            
            # 创建trader实例
            trader = AutoTrader(trader_config)
            self.traders[cfg.id] = trader
            logging.info(f"✓ Trader '{cfg.name}' ({cfg.ai_model}) 已添加")
    
    def get_trader(self, id: str) -> Optional[AutoTrader]:
        """获取指定ID的trader"""
        with self.lock:
            return self.traders.get(id)
    
    def get_all_traders(self) -> Dict[str, AutoTrader]:
        """获取所有trader"""
        with self.lock:
            return self.traders.copy()
    
    def get_trader_ids(self) -> List[str]:
        """获取所有trader ID列表"""
        with self.lock:
            return list(self.traders.keys())
    
    def start_all(self) -> None:
        """启动所有trader"""
        with self.lock:
            logging.info("🚀 启动所有Trader...")
            for id, trader in self.traders.items():
                logging.info(f"▶️  启动 {trader.get_name()}...")
                # 在独立线程中运行每个trader
                def run_trader(t):
                    try:
                        t.run()
                    except Exception as e:
                        logging.error(f"❌ {t.get_name()} 运行错误: {e}")
                
                thread = threading.Thread(target=run_trader, args=(trader,), daemon=True)
                thread.start()
                self.trader_threads[id] = thread
                logging.info(f"✓ {trader.get_name()} 已在独立线程中启动")
    
    def stop_all(self) -> None:
        """停止所有trader"""
        with self.lock:
            logging.info("⏹  停止所有Trader...")
            for trader in self.traders.values():
                trader.stop()
    
    def get_comparison_data(self) -> Dict[str, Any]:
        """获取对比数据"""
        with self.lock:
            comparison = {}
            traders_data = []
            
            for trader in self.traders.values():
                try:
                    account = trader.get_account_info()
                    status = trader.get_status()
                    
                    traders_data.append({
                        "trader_id": trader.get_id(),
                        "trader_name": trader.get_name(),
                        "ai_model": trader.get_ai_model(),
                        "total_equity": account["total_equity"],
                        "total_pnl": account["total_pnl"],
                        "total_pnl_pct": account["total_pnl_pct"],
                        "position_count": account["position_count"],
                        "margin_used_pct": account["margin_used_pct"],
                        "call_count": status["call_count"],
                        "is_running": status["is_running"],
                    })
                except Exception as e:
                    logging.error(f"获取 {trader.get_name()} 数据失败: {e}")
                    continue
            
            comparison["traders"] = traders_data
            comparison["count"] = len(traders_data)
            
            return comparison