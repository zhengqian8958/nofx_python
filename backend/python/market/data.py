import requests
import pandas as pd
import pandas_ta as ta  # 正确的导入方式
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

# 全局代理配置
_PROXY_URL: Optional[str] = None

def set_proxy(proxy_url: str):
    """设置全局代理地址"""
    global _PROXY_URL
    _PROXY_URL = proxy_url if proxy_url else None

def _get_proxies() -> Optional[Dict[str, str]]:
    """获取代理配置字典"""
    if _PROXY_URL:
        return {
            "http": _PROXY_URL,
            "https": _PROXY_URL
        }
    return None


@dataclass
class OIData:
    """Open Interest数据"""
    latest: float = 0.0
    average: float = 0.0


@dataclass
class TimeframeData:
    mid_prices: List[float] = field(default_factory=list)
    ema20_values: List[float] = field(default_factory=list)
    macd_values: List[float] = field(default_factory=list)
    rsi7_values: List[float] = field(default_factory=list)
    rsi14_values: List[float] = field(default_factory=list)
    atr3_values: List[float] = field(default_factory=list)
    atr14_values: List[float] = field(default_factory=list)
    volume_values: List[float] = field(default_factory=list)  # 新增 volume


@dataclass
class MarketData:
    """市场数据结构"""
    symbol: str = ""
    current_price: float = 0.0
    current_ema20: float = 0.0
    current_macd: float = 0.0
    current_rsi7: float = 0.0
    open_interest: Optional[OIData] = None
    funding_rate: float = 0.0
    # 动态周期
    short_interval: str = ""
    medium_interval: str = ""
    long_interval: str = ""
    timeframe_short: Optional[TimeframeData] = None
    timeframe_medium: Optional[TimeframeData] = None
    timeframe_long: Optional[TimeframeData] = None


SUPPORTED_INTERVALS = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080
}

_sorted_intervals = sorted(SUPPORTED_INTERVALS.items(), key=lambda kv: kv[1])

def interval_to_minutes(interval: str) -> int:
    return SUPPORTED_INTERVALS.get(interval, 0)

def choose_scaled_interval(base_interval: str, min_multiplier: float = 4.0, max_multiplier: float = 5.0) -> str:
    base_min = interval_to_minutes(base_interval)
    if base_min <= 0:
        return base_interval
    low = int(base_min * min_multiplier)
    high = int(base_min * max_multiplier)
    candidates = [i for i, m in _sorted_intervals if low <= m <= high]
    if candidates:
        # 选择范围内最小的候选，避免过度放大
        return candidates[0]
    # 若范围内无候选，选择大于 high 的最小可用
    bigger = [i for i, m in _sorted_intervals if m > high]
    if bigger:
        return bigger[0]
    # 否则选择最大可用（兜底）
    return _sorted_intervals[-1][0]

def calculate_timeframe_series(klines: List[Dict]) -> TimeframeData:
    data = TimeframeData()
    df = pd.DataFrame(klines)
    if df.empty:
        return data
    start = max(0, len(klines) - 10)
    close_prices = df['close']
    high_prices = df['high']
    low_prices = df['low']
    # EMA20
    if len(close_prices) >= 20:
        ema20_series = ta.ema(close_prices, length=20)
        if ema20_series is not None:
            for i in range(start, len(klines)):
                if i >= 19:
                    data.ema20_values.append(float(ema20_series.iloc[i]) if not pd.isna(ema20_series.iloc[i]) else 0.0)
    # MACD
    if len(close_prices) >= 26:
        macd_df = ta.macd(close_prices, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            macd_series = macd_df['MACD_12_26_9']
            for i in range(start, len(klines)):
                if i >= 25:
                    data.macd_values.append(float(macd_series.iloc[i]) if not pd.isna(macd_series.iloc[i]) else 0.0)
    # RSI
    if len(close_prices) >= 14:
        rsi7_series = ta.rsi(close_prices, length=7)
        rsi14_series = ta.rsi(close_prices, length=14)
        for i in range(start, len(klines)):
            if i >= 7 and rsi7_series is not None:
                data.rsi7_values.append(float(rsi7_series.iloc[i]) if not pd.isna(rsi7_series.iloc[i]) else 0.0)
            if i >= 14 and rsi14_series is not None:
                data.rsi14_values.append(float(rsi14_series.iloc[i]) if not pd.isna(rsi14_series.iloc[i]) else 0.0)
    # ATR
    if len(high_prices) >= 14:
        atr3_series = ta.atr(high_prices, low_prices, close_prices, length=3)
        atr14_series = ta.atr(high_prices, low_prices, close_prices, length=14)
        for i in range(start, len(klines)):
            if atr3_series is not None and not pd.isna(atr3_series.iloc[i]):
                data.atr3_values.append(float(atr3_series.iloc[i]))
            else:
                data.atr3_values.append(0.0)
            if atr14_series is not None and not pd.isna(atr14_series.iloc[i]):
                data.atr14_values.append(float(atr14_series.iloc[i]))
            else:
                data.atr14_values.append(0.0)
    # Mid prices
    for i in range(start, len(klines)):
        data.mid_prices.append(klines[i]['close'])
    # Volume
    if 'volume' in df.columns:
        volumes = df['volume']
        for i in range(start, len(klines)):
            data.volume_values.append(float(volumes.iloc[i]) if not pd.isna(volumes.iloc[i]) else 0.0)
    return data

def get_klines(symbol: str, interval: str, limit: int) -> List[Dict]:
    """从Binance获取K线数据"""
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    
    response = requests.get(url, proxies=_get_proxies())
    response.raise_for_status()
    
    raw_data = response.json()
    
    klines = []
    for item in raw_data:
        kline = {
            "open_time": int(item[0]),
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5]),
            "close_time": int(item[6]),
        }
        klines.append(kline)
    
    return klines


def get_open_interest_data(symbol: str) -> OIData:
    """获取OI数据"""
    url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
    
    response = requests.get(url, proxies=_get_proxies())
    response.raise_for_status()
    
    result = response.json()
    oi = float(result["openInterest"])
    
    return OIData(
        latest=oi,
        average=oi * 0.999  # 近似平均值
    )


def get_funding_rate(symbol: str) -> float:
    """获取资金费率"""
    url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
    
    response = requests.get(url, proxies=_get_proxies())
    response.raise_for_status()
    
    result = response.json()
    rate = float(result["lastFundingRate"])
    return rate


def normalize_symbol(symbol: str) -> str:
    """标准化symbol,确保是USDT交易对"""
    symbol = symbol.upper()
    if symbol.endswith("USDT"):
        return symbol
    return symbol + "USDT"


def get(symbol: str, short_interval: str = "3m") -> MarketData:
    """获取指定代币的市场数据（支持 short/medium/long 动态周期）"""
    # 标准化symbol
    symbol = normalize_symbol(symbol)
    # 计算周期
    short = short_interval
    medium = choose_scaled_interval(short)
    long = choose_scaled_interval(medium)
    
    # 获取K线数据
    klines_short = get_klines(symbol, short, 60)
    klines_medium = get_klines(symbol, medium, 60)
    klines_long = get_klines(symbol, long, 120)
    
    # 当前价格与短周期指标
    current_price = klines_short[-1]["close"] if klines_short else 0.0
    current_ema20 = 0.0
    current_macd = 0.0
    current_rsi7 = 0.0
    df_short = pd.DataFrame(klines_short)
    if not df_short.empty:
        close_prices_short = df_short['close']
        if len(close_prices_short) >= 20:
            ema20_series = ta.ema(close_prices_short, length=20)
            if ema20_series is not None and not ema20_series.empty:
                current_ema20 = float(ema20_series.iloc[-1]) if not pd.isna(ema20_series.iloc[-1]) else 0.0
        if len(close_prices_short) >= 26:
            macd_df = ta.macd(close_prices_short, fast=12, slow=26, signal=9)
            if macd_df is not None and not macd_df.empty:
                current_macd = float(macd_df.iloc[-1]['MACD_12_26_9']) if not pd.isna(macd_df.iloc[-1]['MACD_12_26_9']) else 0.0
        if len(close_prices_short) >= 7:
            rsi7_series = ta.rsi(close_prices_short, length=7)
            if rsi7_series is not None and not rsi7_series.empty:
                current_rsi7 = float(rsi7_series.iloc[-1]) if not pd.isna(rsi7_series.iloc[-1]) else 0.0
    
    # 获取OI数据
    oi_data = None
    try:
        oi_data = get_open_interest_data(symbol)
    except Exception:
        oi_data = OIData(latest=0, average=0)
    
    # 获取Funding Rate
    funding_rate = 0.0
    try:
        funding_rate = get_funding_rate(symbol)
    except Exception:
        pass
    
    # 计算三个周期的指标序列
    tf_short = calculate_timeframe_series(klines_short)
    tf_medium = calculate_timeframe_series(klines_medium)
    tf_long = calculate_timeframe_series(klines_long)
    
    return MarketData(
        symbol=symbol,
        current_price=current_price,
        current_ema20=current_ema20,
        current_macd=current_macd,
        current_rsi7=current_rsi7,
        open_interest=oi_data,
        funding_rate=funding_rate,
        short_interval=short,
        medium_interval=medium,
        long_interval=long,
        timeframe_short=tf_short,
        timeframe_medium=tf_medium,
        timeframe_long=tf_long,
    )


def format_market_data(data: MarketData) -> str:
    """格式化输出市场数据（short/medium/long 动态周期，对齐 system_prompt 输入要求）"""
    result = []
    
    result.append(f"current_price = {data.current_price:.2f}, current_ema20 = {data.current_ema20:.3f}, current_macd = {data.current_macd:.3f}, current_rsi (7 period) = {data.current_rsi7:.3f}\n\n")
    
    result.append(f"In addition, here is the latest {data.symbol} open interest and funding rate for perps:\n\n")
    
    if data.open_interest:
        result.append(f"Open Interest: Latest: {data.open_interest.latest:.2f} Average: {data.open_interest.average:.2f}\n\n")
    
    result.append(f"Funding Rate: {data.funding_rate:.2e}\n\n")
    
    def append_tf(label: str, tf: Optional[TimeframeData], interval: str):
        if tf is None:
            return
        result.append(f"{label} ({interval} interval, oldest → latest):\n\n")
        if tf.mid_prices:
            result.append(f"prices: [{', '.join([f'{p:.3f}' for p in tf.mid_prices])}]\n\n")
        if tf.ema20_values:
            result.append(f"ema20: [{', '.join([f'{p:.3f}' for p in tf.ema20_values])}]\n\n")
        if tf.macd_values:
            result.append(f"macd: [{', '.join([f'{p:.3f}' for p in tf.macd_values])}]\n\n")
        if tf.rsi7_values:
            result.append(f"rsi7: [{', '.join([f'{p:.3f}' for p in tf.rsi7_values])}]\n\n")
        if tf.rsi14_values:
            result.append(f"rsi14: [{', '.join([f'{p:.3f}' for p in tf.rsi14_values])}]\n\n")
        if tf.atr3_values:
            result.append(f"atr3: [{', '.join([f'{p:.3f}' for p in tf.atr3_values])}]\n\n")
        if tf.atr14_values:
            result.append(f"atr14: [{', '.join([f'{p:.3f}' for p in tf.atr14_values])}]\n\n")
        if tf.volume_values:
            result.append(f"volume: [{', '.join([f'{p:.2f}' for p in tf.volume_values])}]\n\n")
    
    append_tf("Short timeframe", data.timeframe_short, data.short_interval)
    append_tf("Medium timeframe", data.timeframe_medium, data.medium_interval)
    append_tf("Long timeframe", data.timeframe_long, data.long_interval)
    
    return "".join(result)