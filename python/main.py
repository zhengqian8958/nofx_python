import sys
import logging
import signal
import time
import os
from typing import List

# 添加项目根目录到sys.path，使绝对导入可用
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 使用绝对导入替代相对导入
from config.config import load_config, Config, TraderConfig
from manager.trader_manager import TraderManager
from api.server import Server
import threading


def setup_logging() -> None:
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def main() -> None:
    """主函数"""
    setup_logging()
    
    logging.info("╔════════════════════════════════════════════════════════════╗")
    logging.info("║    🏆 AI模型交易竞赛系统 - Qwen vs DeepSeek               ║")
    logging.info("╚════════════════════════════════════════════════════════════╝")
    logging.info("")
    
    # 加载配置文件
    config_file = "config.json"
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    logging.info(f"📋 加载配置文件: {config_file}")
    try:
        cfg = load_config(config_file)
    except Exception as e:
        logging.error(f"❌ 加载配置失败: {e}")
        sys.exit(1)
    
    logging.info(f"✓ 配置加载成功，共{len(cfg.traders)}个trader参赛")
    logging.info("")
    
    # 设置自定义币种列表
    if cfg.custom_coins:
        from pool.coin_pool import set_custom_coins
        set_custom_coins(cfg.custom_coins)
        logging.info(f"✓ 已设置自定义币种列表: {cfg.custom_coins}")
    else:
        # 设置是否使用默认主流币种
        from pool.coin_pool import set_use_default_coins
        set_use_default_coins(cfg.use_default_coins)
        if cfg.use_default_coins:
            logging.info("✓ 已启用默认主流币种列表（BTC、ETH、SOL、BNB、XRP、DOGE、ADA、HYPE）")
    
    # 设置币种池API URL
    if cfg.coin_pool_api_url:
        from pool.coin_pool import set_coin_pool_api
        set_coin_pool_api(cfg.coin_pool_api_url)
        logging.info("✓ 已配置AI500币种池API")
    if cfg.oi_top_api_url:
        from pool.coin_pool import set_oi_top_api
        set_oi_top_api(cfg.oi_top_api_url)
        logging.info("✓ 已配置OI Top API")
    
    # 创建TraderManager
    trader_manager = TraderManager()
    
    # 添加所有启用的trader
    enabled_traders = [t for t in cfg.traders if t.enabled]
    for i, trader_cfg in enumerate(enabled_traders):
        logging.info(f"📦 [{i+1}/{len(enabled_traders)}] 初始化 {trader_cfg.name} ({trader_cfg.ai_model.upper()}模型)...")
        
        try:
            trader_manager.add_trader(
                trader_cfg,
                cfg.coin_pool_api_url,
                cfg.max_daily_loss,
                cfg.max_drawdown,
                cfg.stop_trading_minutes,
                cfg.leverage,  # 传递杠杆配置
            )
        except Exception as e:
            logging.error(f"❌ 初始化trader失败: {e}")
            sys.exit(1)
    
    logging.info("")
    logging.info("🏁 竞赛参赛者:")
    for trader_cfg in enabled_traders:
        logging.info(f"  • {trader_cfg.name} ({trader_cfg.ai_model.upper()}) - 初始资金: {trader_cfg.initial_balance:.0f} USDT")
    
    logging.info("")
    logging.info("🤖 AI全权决策模式:")
    logging.info(f"  • AI将自主决定每笔交易的杠杆倍数（山寨币最高{cfg.leverage.altcoin_leverage}倍，BTC/ETH最高{cfg.leverage.btc_eth_leverage}倍）")
    logging.info("  • AI将自主决定每笔交易的仓位大小")
    logging.info("  • AI将自主设置止损和止盈价格")
    logging.info("  • AI将基于市场数据、技术指标、账户状态做出全面分析")
    logging.info("")
    logging.info("⚠️  风险提示: AI自动交易有风险，建议小额资金测试！")
    logging.info("")
    logging.info("按 Ctrl+C 停止运行")
    logging.info("=" * 60)
    logging.info("")
    
    # 创建并启动API服务器
    api_server = Server(trader_manager, cfg.api_server_port)
    
    # 使用正确的异步方式启动API服务器
    def start_api_server():
        try:
            api_server.start()
        except Exception as e:
            logging.error(f"API服务器启动失败: {e}")
    
    # 在单独的线程中启动API服务器
    server_thread = threading.Thread(target=start_api_server, daemon=True)
    server_thread.start()
    
    # 设置优雅退出
    def signal_handler(sig, frame):
        logging.info("")
        logging.info("")
        logging.info("📛 收到退出信号，正在停止所有trader...")
        trader_manager.stop_all()
        logging.info("")
        logging.info("👋 感谢使用AI交易竞赛系统！")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动所有trader（在独立线程中运行）
    def start_traders():
        trader_manager.start_all()
    
    trader_thread = threading.Thread(target=start_traders, daemon=True)
    trader_thread.start()
    
    # 保持主线程运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()