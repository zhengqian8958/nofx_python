import json
import os
import logging
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class TraderConfig:
    """单个trader的配置"""
    id: str
    name: str
    ai_model: str  # "qwen" or "deepseek"
    
    # 交易平台选择
    exchange: str = "binance"  # "binance" or "hyperliquid"
    
    # 币安配置
    binance_api_key: Optional[str] = None
    binance_secret_key: Optional[str] = None
    
    # Hyperliquid配置
    hyperliquid_private_key: Optional[str] = None
    hyperliquid_testnet: bool = False
    
    # Aster配置
    aster_user: Optional[str] = None
    aster_signer: Optional[str] = None
    aster_private_key: Optional[str] = None
    
    # AI配置
    qwen_key: Optional[str] = None
    deepseek_key: Optional[str] = None
    
    # 自定义AI API配置
    custom_api_url: Optional[str] = None
    custom_api_key: Optional[str] = None
    custom_model_name: Optional[str] = None
    
    # 启用配置
    enabled: bool = True
    
    initial_balance: float = 0.0
    scan_interval_minutes: int = 3


@dataclass
class LeverageConfig:
    """杠杆配置"""
    btc_eth_leverage: int = 5  # BTC和ETH的杠杆倍数
    altcoin_leverage: int = 5   # 山寨币的杠杆倍数


@dataclass
class Config:
    """总配置"""
    traders: List[TraderConfig] = field(default_factory=list)
    use_default_coins: bool = True
    custom_coins: List[str] = field(default_factory=list)  # 自定义币种列表
    coin_pool_api_url: str = ""
    oi_top_api_url: str = ""
    api_server_port: int = 8080
    max_daily_loss: float = 0.0
    max_drawdown: float = 0.0
    stop_trading_minutes: int = 0
    leverage: LeverageConfig = field(default_factory=LeverageConfig)


def load_config(filename: str = "config.json") -> Config:
    """从文件加载配置"""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"配置文件 {filename} 不存在")
    
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    config = Config()
    
    # 加载基础配置
    config.use_default_coins = data.get("use_default_coins", True)
    config.custom_coins = data.get("custom_coins", [])
    config.coin_pool_api_url = data.get("coin_pool_api_url", "")
    config.oi_top_api_url = data.get("oi_top_api_url", "")
    config.api_server_port = data.get("api_server_port", 8080)
    config.max_daily_loss = data.get("max_daily_loss", 0.0)
    config.max_drawdown = data.get("max_drawdown", 0.0)
    config.stop_trading_minutes = data.get("stop_trading_minutes", 0)
    
    # 加载杠杆配置
    leverage_data = data.get("leverage", {})
    config.leverage = LeverageConfig(
        btc_eth_leverage=leverage_data.get("btc_eth_leverage", 5),
        altcoin_leverage=leverage_data.get("altcoin_leverage", 5)
    )
    
    # 加载traders配置
    traders_data = data.get("traders", [])
    for trader_data in traders_data:
        trader = TraderConfig(
            id=trader_data.get("id", ""),
            name=trader_data.get("name", ""),
            ai_model=trader_data.get("ai_model", "deepseek"),
            exchange=trader_data.get("exchange", "binance"),
            binance_api_key=trader_data.get("binance_api_key"),
            binance_secret_key=trader_data.get("binance_secret_key"),
            hyperliquid_private_key=trader_data.get("hyperliquid_private_key"),
            hyperliquid_testnet=trader_data.get("hyperliquid_testnet", False),
            aster_user=trader_data.get("aster_user"),
            aster_signer=trader_data.get("aster_signer"),
            aster_private_key=trader_data.get("aster_private_key"),
            qwen_key=trader_data.get("qwen_key"),
            deepseek_key=trader_data.get("deepseek_key"),
            custom_api_url=trader_data.get("custom_api_url"),
            custom_api_key=trader_data.get("custom_api_key"),
            custom_model_name=trader_data.get("custom_model_name"),
            enabled=trader_data.get("enabled", True),
            initial_balance=trader_data.get("initial_balance", 0.0),
            scan_interval_minutes=trader_data.get("scan_interval_minutes", 3)
        )
        config.traders.append(trader)
    
    # 验证配置
    validate_config(config)
    
    return config


def validate_config(config: Config) -> None:
    """验证配置有效性"""
    if not config.traders:
        raise ValueError("至少需要配置一个trader")
    
    trader_ids = set()
    for i, trader in enumerate(config.traders):
        if not trader.id:
            raise ValueError(f"trader[{i}]: ID不能为空")
        
        if trader.id in trader_ids:
            raise ValueError(f"trader[{i}]: ID '{trader.id}' 重复")
        trader_ids.add(trader.id)
        
        if not trader.name:
            raise ValueError(f"trader[{i}]: Name不能为空")
        
        if trader.ai_model not in ["qwen", "deepseek", "custom"]:
            raise ValueError(f"trader[{i}]: ai_model必须是 'qwen', 'deepseek' 或 'custom'")
        
        # 验证交易平台配置
        if trader.exchange not in ["binance", "hyperliquid", "aster"]:
            raise ValueError(f"trader[{i}]: exchange必须是 'binance', 'hyperliquid' 或 'aster'")
        
        # 根据平台验证对应的密钥
        if trader.exchange == "binance":
            if not trader.binance_api_key or not trader.binance_secret_key:
                raise ValueError(f"trader[{i}]: 使用币安时必须配置binance_api_key和binance_secret_key")
        elif trader.exchange == "hyperliquid":
            if not trader.hyperliquid_private_key:
                raise ValueError(f"trader[{i}]: 使用Hyperliquid时必须配置hyperliquid_private_key")
        elif trader.exchange == "aster":
            if not trader.aster_user or not trader.aster_signer or not trader.aster_private_key:
                raise ValueError(f"trader[{i}]: 使用Aster时必须配置aster_user, aster_signer和aster_private_key")
        
        if trader.ai_model == "qwen" and not trader.qwen_key:
            raise ValueError(f"trader[{i}]: 使用Qwen时必须配置qwen_key")
        if trader.ai_model == "deepseek" and not trader.deepseek_key:
            raise ValueError(f"trader[{i}]: 使用DeepSeek时必须配置deepseek_key")
        if trader.ai_model == "custom":
            if not trader.custom_api_url:
                raise ValueError(f"trader[{i}]: 使用自定义API时必须配置custom_api_url")
            if not trader.custom_api_key:
                raise ValueError(f"trader[{i}]: 使用自定义API时必须配置custom_api_key")
            if not trader.custom_model_name:
                raise ValueError(f"trader[{i}]: 使用自定义API时必须配置custom_model_name")
        
        if trader.initial_balance <= 0:
            raise ValueError(f"trader[{i}]: initial_balance必须大于0")
        
        if trader.scan_interval_minutes <= 0:
            trader.scan_interval_minutes = 3  # 默认3分钟
    
    if config.api_server_port <= 0:
        config.api_server_port = 8080  # 默认8080端口
    
    # 设置杠杆默认值（适配币安子账户限制，最大5倍）
    if config.leverage.btc_eth_leverage <= 0:
        config.leverage.btc_eth_leverage = 5  # 默认5倍（安全值，适配子账户）
    if config.leverage.btc_eth_leverage > 5:
        logging.warning(f"警告: BTC/ETH杠杆设置为{config.leverage.btc_eth_leverage}x，如果使用子账户可能会失败（子账户限制≤5x）")
    
    if config.leverage.altcoin_leverage <= 0:
        config.leverage.altcoin_leverage = 5  # 默认5倍（安全值，适配子账户）
    if config.leverage.altcoin_leverage > 5:
        logging.warning(f"警告: 山寨币杠杆设置为{config.leverage.altcoin_leverage}x，如果使用子账户可能会失败（子账户限制≤5x）")