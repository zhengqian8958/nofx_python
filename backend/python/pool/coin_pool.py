import json
import time
import logging
import requests
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class CoinInfo:
    """币种信息"""
    pair: str = ""  # 交易对符号（例如：BTCUSDT）
    score: float = 0.0  # 当前评分
    start_time: int = 0  # 开始时间（Unix时间戳）
    start_price: float = 0.0  # 开始价格
    last_score: float = 0.0  # 最新评分
    max_score: float = 0.0  # 最高评分
    max_price: float = 0.0  # 最高价格
    increase_percent: float = 0.0  # 涨幅百分比
    is_available: bool = True  # 是否可交易（内部使用）


@dataclass
class OIPosition:
    """持仓量数据"""
    symbol: str = ""
    rank: int = 0
    current_oi: float = 0.0  # 当前持仓量
    oi_delta: float = 0.0  # 持仓量变化
    oi_delta_percent: float = 0.0  # 持仓量变化百分比
    oi_delta_value: float = 0.0  # 持仓量变化价值
    price_delta_percent: float = 0.0  # 价格变化百分比
    net_long: float = 0.0  # 净多仓
    net_short: float = 0.0  # 净空仓


# 默认主流币种池（当AI500和OI Top都失败时使用）
default_mainstream_coins = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "HYPEUSDT",
]

# 添加自定义币种列表
custom_coins = []


class CoinPoolConfig:
    """币种池配置"""
    def __init__(self):
        self.api_url: str = ""
        self.timeout: int = 30  # 增加到30秒
        self.cache_dir: str = "coin_pool_cache"
        self.use_default_coins: bool = False  # 默认不使用


coin_pool_config = CoinPoolConfig()


def set_coin_pool_api(api_url: str) -> None:
    """设置币种池API"""
    global coin_pool_config
    coin_pool_config.api_url = api_url


def set_oi_top_api(api_url: str) -> None:
    """设置OI Top API"""
    global oi_top_config
    oi_top_config.api_url = api_url


def set_use_default_coins(use_default: bool) -> None:
    """设置是否使用默认主流币种"""
    global coin_pool_config
    coin_pool_config.use_default_coins = use_default


def get_coin_pool() -> List[CoinInfo]:
    """获取币种池列表（带重试和缓存机制）"""
    global coin_pool_config, custom_coins
    
    # 优先检查是否设置了自定义币种列表
    if custom_coins:
        logging.info(f"✓ 使用自定义币种列表: {custom_coins}")
        return _convert_symbols_to_coins(custom_coins)
    
    # 检查是否启用默认币种列表
    if coin_pool_config.use_default_coins:
        logging.info("✓ 已启用默认主流币种列表")
        return _convert_symbols_to_coins(default_mainstream_coins)
    
    # 检查API URL是否配置
    if not coin_pool_config.api_url.strip():
        logging.info("⚠️  未配置币种池API URL，使用默认主流币种列表")
        return _convert_symbols_to_coins(default_mainstream_coins)
    
    max_retries = 3
    last_err = None
    
    # 尝试从API获取
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            logging.info(f"⚠️  第{attempt}次重试获取币种池（共{max_retries}次）...")
            time.sleep(2)  # 重试前等待2秒
        
        try:
            coins = _fetch_coin_pool()
            if attempt > 1:
                logging.info(f"✓ 第{attempt}次重试成功")
            # 成功获取后保存到缓存
            try:
                _save_coin_pool_cache(coins)
            except Exception as e:
                logging.warning(f"⚠️  保存币种池缓存失败: {e}")
            return coins
        except Exception as e:
            last_err = e
            logging.error(f"❌ 第{attempt}次请求失败: {e}")
    
    # API获取失败，尝试使用缓存
    logging.info("⚠️  API请求全部失败，尝试使用历史缓存数据...")
    try:
        cached_coins = _load_coin_pool_cache()
        logging.info(f"✓ 使用历史缓存数据（共{len(cached_coins)}个币种）")
        return cached_coins
    except Exception as e:
        pass
    
    # 缓存也失败，使用默认主流币种
    logging.info(f"⚠️  无法加载缓存数据（最后错误: {last_err}），使用默认主流币种列表")
    return _convert_symbols_to_coins(default_mainstream_coins)


def _fetch_coin_pool() -> List[CoinInfo]:
    """实际执行币种池请求"""
    global coin_pool_config
    logging.info("🔄 正在请求AI500币种池...")
    
    try:
        response = requests.get(coin_pool_config.api_url, timeout=coin_pool_config.timeout)
        response.raise_for_status()
        
        data = response.json()
        
        if not data.get("success"):
            raise Exception("API返回失败状态")
        
        if not data.get("data", {}).get("coins"):
            raise Exception("币种列表为空")
        
        # 解析API响应
        coins_data = data["data"]["coins"]
        coins = []
        for coin_data in coins_data:
            coin = CoinInfo(
                pair=coin_data["pair"],
                score=coin_data["score"],
                start_time=coin_data["start_time"],
                start_price=coin_data["start_price"],
                last_score=coin_data["last_score"],
                max_score=coin_data["max_score"],
                max_price=coin_data["max_price"],
                increase_percent=coin_data["increase_percent"],
                is_available=True
            )
            coins.append(coin)
        
        logging.info(f"✓ 成功获取{len(coins)}个币种")
        return coins
    except requests.exceptions.RequestException as e:
        raise Exception(f"请求币种池API失败: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"JSON解析失败: {e}")
    except Exception as e:
        raise Exception(f"获取币种池失败: {e}")


def _save_coin_pool_cache(coins: List[CoinInfo]) -> None:
    """保存币种池到缓存文件"""
    global coin_pool_config
    
    # 确保缓存目录存在
    os.makedirs(coin_pool_config.cache_dir, exist_ok=True)
    
    cache = {
        "coins": [
            {
                "pair": coin.pair,
                "score": coin.score,
                "start_time": coin.start_time,
                "start_price": coin.start_price,
                "last_score": coin.last_score,
                "max_score": coin.max_score,
                "max_price": coin.max_price,
                "increase_percent": coin.increase_percent,
                "is_available": coin.is_available,
            }
            for coin in coins
        ],
        "fetched_at": time.time(),
        "source_type": "api",
    }
    
    cache_path = os.path.join(coin_pool_config.cache_dir, "latest.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    
    logging.info(f"💾 已保存币种池缓存（{len(coins)}个币种）")


def _load_coin_pool_cache() -> List[CoinInfo]:
    """从缓存文件加载币种池"""
    global coin_pool_config
    cache_path = os.path.join(coin_pool_config.cache_dir, "latest.json")
    
    # 检查文件是否存在
    if not os.path.exists(cache_path):
        raise Exception("缓存文件不存在")
    
    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)
    
    # 检查缓存年龄
    cache_age = time.time() - cache["fetched_at"]
    if cache_age > 24 * 3600:
        logging.info(f"⚠️  缓存数据较旧（{cache_age/3600:.1f}小时前），但仍可使用")
    else:
        logging.info(f"📂 缓存数据时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cache['fetched_at']))}（{cache_age/60:.1f}分钟前）")
    
    coins = []
    for coin_data in cache["coins"]:
        coin = CoinInfo(
            pair=coin_data["pair"],
            score=coin_data["score"],
            start_time=coin_data["start_time"],
            start_price=coin_data["start_price"],
            last_score=coin_data["last_score"],
            max_score=coin_data["max_score"],
            max_price=coin_data["max_price"],
            increase_percent=coin_data["increase_percent"],
            is_available=coin_data["is_available"],
        )
        coins.append(coin)
    
    return coins


def get_available_coins() -> List[str]:
    """获取可用的币种列表（过滤不可用的）"""
    coins = get_coin_pool()
    
    symbols = []
    for coin in coins:
        if coin.is_available:
            # 确保symbol格式正确（转为大写USDT交易对）
            symbol = _normalize_symbol(coin.pair)
            symbols.append(symbol)
    
    if not symbols:
        raise Exception("没有可用的币种")
    
    return symbols


def get_top_rated_coins(limit: int) -> List[str]:
    """获取评分最高的N个币种（按评分从大到小排序）"""
    coins = get_coin_pool()
    
    # 过滤可用的币种
    available_coins = [coin for coin in coins if coin.is_available]
    
    if not available_coins:
        raise Exception("没有可用的币种")
    
    # 按Score降序排序
    available_coins.sort(key=lambda x: x.score, reverse=True)
    
    # 取前N个
    max_count = min(limit, len(available_coins))
    
    symbols = []
    for i in range(max_count):
        symbol = _normalize_symbol(available_coins[i].pair)
        symbols.append(symbol)
    
    return symbols


def _normalize_symbol(symbol: str) -> str:
    """标准化币种符号"""
    # 移除空格
    symbol = symbol.replace(" ", "")
    
    # 转为大写
    symbol = symbol.upper()
    
    # 确保以USDT结尾
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"
    
    return symbol


def _convert_symbols_to_coins(symbols: List[str]) -> List[CoinInfo]:
    """将币种符号列表转换为CoinInfo列表"""
    coins = []
    for symbol in symbols:
        coins.append(CoinInfo(pair=symbol, is_available=True))
    return coins


# ========== OI Top（持仓量增长Top20）数据 ==========

class OITopConfig:
    """OI Top配置"""
    def __init__(self):
        self.api_url: str = ""
        self.timeout: int = 30
        self.cache_dir: str = "coin_pool_cache"


oi_top_config = OITopConfig()


def get_oi_top_positions() -> List[OIPosition]:
    """获取持仓量增长Top20数据（带重试和缓存）"""
    global oi_top_config
    
    # 检查API URL是否配置
    if not oi_top_config.api_url.strip():
        logging.info("⚠️  未配置OI Top API URL，跳过OI Top数据获取")
        return []  # 返回空列表，不是错误
    
    max_retries = 3
    last_err = None
    
    # 尝试从API获取
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            logging.info(f"⚠️  第{attempt}次重试获取OI Top数据（共{max_retries}次）...")
            time.sleep(2)
        
        try:
            positions = _fetch_oi_top()
            if attempt > 1:
                logging.info(f"✓ 第{attempt}次重试成功")
            # 成功获取后保存到缓存
            try:
                _save_oi_top_cache(positions)
            except Exception as e:
                logging.warning(f"⚠️  保存OI Top缓存失败: {e}")
            return positions
        except Exception as e:
            last_err = e
            logging.error(f"❌ 第{attempt}次请求OI Top失败: {e}")
    
    # API获取失败，尝试使用缓存
    logging.info("⚠️  OI Top API请求全部失败，尝试使用历史缓存数据...")
    try:
        cached_positions = _load_oi_top_cache()
        logging.info(f"✓ 使用历史OI Top缓存数据（共{len(cached_positions)}个币种）")
        return cached_positions
    except Exception as e:
        pass
    
    # 缓存也失败，返回空列表（OI Top是可选的）
    logging.info(f"⚠️  无法加载OI Top缓存数据（最后错误: {last_err}），跳过OI Top数据")
    return []


def _fetch_oi_top() -> List[OIPosition]:
    """实际执行OI Top请求"""
    global oi_top_config
    logging.info("🔄 正在请求OI Top数据...")
    
    try:
        response = requests.get(oi_top_config.api_url, timeout=oi_top_config.timeout)
        response.raise_for_status()
        
        data = response.json()
        
        if not data.get("success"):
            raise Exception("OI Top API返回失败状态")
        
        if not data.get("data", {}).get("positions"):
            raise Exception("OI Top持仓列表为空")
        
        # 解析API响应
        positions_data = data["data"]["positions"]
        positions = []
        for pos_data in positions_data:
            pos = OIPosition(
                symbol=pos_data["symbol"],
                rank=pos_data["rank"],
                current_oi=pos_data["current_oi"],
                oi_delta=pos_data["oi_delta"],
                oi_delta_percent=pos_data["oi_delta_percent"],
                oi_delta_value=pos_data["oi_delta_value"],
                price_delta_percent=pos_data["price_delta_percent"],
                net_long=pos_data["net_long"],
                net_short=pos_data["net_short"],
            )
            positions.append(pos)
        
        logging.info(f"✓ 成功获取{len(positions)}个OI Top币种（时间范围: {data['data'].get('time_range', 'unknown')}）")
        return positions
    except requests.exceptions.RequestException as e:
        raise Exception(f"请求OI Top API失败: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"OI Top JSON解析失败: {e}")
    except Exception as e:
        raise Exception(f"获取OI Top数据失败: {e}")


def _save_oi_top_cache(positions: List[OIPosition]) -> None:
    """保存OI Top数据到缓存"""
    global oi_top_config
    
    os.makedirs(oi_top_config.cache_dir, exist_ok=True)
    
    cache = {
        "positions": [
            {
                "symbol": pos.symbol,
                "rank": pos.rank,
                "current_oi": pos.current_oi,
                "oi_delta": pos.oi_delta,
                "oi_delta_percent": pos.oi_delta_percent,
                "oi_delta_value": pos.oi_delta_value,
                "price_delta_percent": pos.price_delta_percent,
                "net_long": pos.net_long,
                "net_short": pos.net_short,
            }
            for pos in positions
        ],
        "fetched_at": time.time(),
        "source_type": "api",
    }
    
    cache_path = os.path.join(oi_top_config.cache_dir, "oi_top_latest.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    
    logging.info(f"💾 已保存OI Top缓存（{len(positions)}个币种）")


def _load_oi_top_cache() -> List[OIPosition]:
    """从缓存加载OI Top数据"""
    global oi_top_config
    cache_path = os.path.join(oi_top_config.cache_dir, "oi_top_latest.json")
    
    if not os.path.exists(cache_path):
        raise Exception("OI Top缓存文件不存在")
    
    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)
    
    cache_age = time.time() - cache["fetched_at"]
    if cache_age > 24 * 3600:
        logging.info(f"⚠️  OI Top缓存数据较旧（{cache_age/3600:.1f}小时前），但仍可使用")
    else:
        logging.info(f"📂 OI Top缓存数据时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cache['fetched_at']))}（{cache_age/60:.1f}分钟前）")
    
    positions = []
    for pos_data in cache["positions"]:
        pos = OIPosition(
            symbol=pos_data["symbol"],
            rank=pos_data["rank"],
            current_oi=pos_data["current_oi"],
            oi_delta=pos_data["oi_delta"],
            oi_delta_percent=pos_data["oi_delta_percent"],
            oi_delta_value=pos_data["oi_delta_value"],
            price_delta_percent=pos_data["price_delta_percent"],
            net_long=pos_data["net_long"],
            net_short=pos_data["net_short"],
        )
        positions.append(pos)
    
    return positions


def get_oi_top_symbols() -> List[str]:
    """获取OI Top的币种符号列表"""
    positions = get_oi_top_positions()
    
    symbols = []
    for pos in positions:
        symbol = _normalize_symbol(pos.symbol)
        symbols.append(symbol)
    
    return symbols


@dataclass
class MergedCoinPool:
    """合并的币种池（AI500 + OI Top）"""
    ai500_coins: List[CoinInfo] = field(default_factory=list)  # AI500评分币种
    oi_top_coins: List[OIPosition] = field(default_factory=list)  # 持仓量增长Top20
    all_symbols: List[str] = field(default_factory=list)  # 所有不重复的币种符号
    symbol_sources: Dict[str, List[str]] = field(default_factory=dict)  # 每个币种的来源（"ai500"/"oi_top"）


def get_merged_coin_pool(ai500_limit: int) -> MergedCoinPool:
    """获取合并后的币种池（AI500 + OI Top，去重）"""
    # 1. 获取AI500数据
    try:
        ai500_top_symbols = get_top_rated_coins(ai500_limit)
    except Exception as e:
        logging.warning(f"⚠️  获取AI500数据失败: {e}")
        ai500_top_symbols = []  # 失败时用空列表
    
    # 2. 获取OI Top数据
    try:
        oi_top_symbols = get_oi_top_symbols()
    except Exception as e:
        logging.warning(f"⚠️  获取OI Top数据失败: {e}")
        oi_top_symbols = []  # 失败时用空列表
    
    # 3. 合并并去重
    symbol_set = set()
    symbol_sources = {}
    
    # 添加AI500币种
    for symbol in ai500_top_symbols:
        symbol_set.add(symbol)
        if symbol not in symbol_sources:
            symbol_sources[symbol] = []
        symbol_sources[symbol].append("ai500")
    
    # 添加OI Top币种
    for symbol in oi_top_symbols:
        symbol_set.add(symbol)
        if symbol not in symbol_sources:
            symbol_sources[symbol] = []
        symbol_sources[symbol].append("oi_top")
    
    # 转换为数组
    all_symbols = list(symbol_set)
    
    # 获取完整数据
    ai500_coins = get_coin_pool()
    oi_top_coins = get_oi_top_positions()
    
    merged = MergedCoinPool(
        ai500_coins=ai500_coins,
        oi_top_coins=oi_top_coins,
        all_symbols=all_symbols,
        symbol_sources=symbol_sources,
    )
    
    logging.info(f"📊 币种池合并完成: AI500={len(ai500_top_symbols)}, OI_Top={len(oi_top_symbols)}, 总计(去重)={len(all_symbols)}")
    
    return merged


def set_custom_coins(coins: List[str]) -> None:
    """设置自定义币种列表"""
    global custom_coins
    custom_coins = coins
    logging.info(f"✓ 已设置自定义币种列表: {custom_coins}")
