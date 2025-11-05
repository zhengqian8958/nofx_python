import requests
import pandas as pd
import pandas_ta as ta  # 正确的导入方式
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class OIData:
    """Open Interest数据"""
    latest: float = 0.0
    average: float = 0.0


@dataclass
class IntradayData:
    """日内数据(3分钟间隔)"""
    mid_prices: List[float] = field(default_factory=list)
    ema20_values: List[float] = field(default_factory=list)
    macd_values: List[float] = field(default_factory=list)
    rsi7_values: List[float] = field(default_factory=list)
    rsi14_values: List[float] = field(default_factory=list)


@dataclass
class LongerTermData:
    """长期数据(4小时时间框架)"""
    ema20: float = 0.0
    ema50: float = 0.0
    atr3: float = 0.0
    atr14: float = 0.0
    current_volume: float = 0.0
    average_volume: float = 0.0
    macd_values: List[float] = field(default_factory=list)
    rsi14_values: List[float] = field(default_factory=list)


@dataclass
class MarketData:
    """市场数据结构"""
    symbol: str = ""
    current_price: float = 0.0
    price_change_1h: float = 0.0  # 1小时价格变化百分比
    price_change_4h: float = 0.0  # 4小时价格变化百分比
    current_ema20: float = 0.0
    current_macd: float = 0.0
    current_rsi7: float = 0.0
    open_interest: Optional[OIData] = None
    funding_rate: float = 0.0
    intraday_series: Optional[IntradayData] = None
    longer_term_context: Optional[LongerTermData] = None


def get_klines(symbol: str, interval: str, limit: int) -> List[Dict]:
    """从Binance获取K线数据"""
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    
    response = requests.get(url)
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


def calculate_intraday_series(klines: List[Dict]) -> IntradayData:
    """计算日内系列数据"""
    data = IntradayData()
    
    # 转换为pandas DataFrame
    df = pd.DataFrame(klines)
    
    if df.empty:
        return data
        
    close_prices = df['close']
    
    # 获取最近10个数据点
    start = max(0, len(klines) - 10)
    
    # 批量计算技术指标
    # EMA20
    if len(close_prices) >= 20:
        ema20_series = ta.ema(close_prices, length=20)
        if ema20_series is not None:
            for i in range(start, len(klines)):
                if i >= 19:  # 需要至少20个数据点来计算EMA
                    data.ema20_values.append(float(ema20_series.iloc[i]) if not pd.isna(ema20_series.iloc[i]) else 0.0)
    
    # MACD
    if len(close_prices) >= 26:
        macd_df = ta.macd(close_prices, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            macd_series = macd_df['MACD_12_26_9']
            for i in range(start, len(klines)):
                if i >= 25:  # 需要至少26个数据点来计算MACD
                    data.macd_values.append(float(macd_series.iloc[i]) if not pd.isna(macd_series.iloc[i]) else 0.0)
    
    # RSI
    if len(close_prices) >= 14:
        rsi7_series = ta.rsi(close_prices, length=7)
        rsi14_series = ta.rsi(close_prices, length=14)
        
        for i in range(start, len(klines)):
            # RSI7
            if i >= 7 and rsi7_series is not None:
                data.rsi7_values.append(float(rsi7_series.iloc[i]) if not pd.isna(rsi7_series.iloc[i]) else 0.0)
                
            # RSI14
            if i >= 14 and rsi14_series is not None:
                data.rsi14_values.append(float(rsi14_series.iloc[i]) if not pd.isna(rsi14_series.iloc[i]) else 0.0)
    
    # Mid prices
    for i in range(start, len(klines)):
        data.mid_prices.append(klines[i]['close'])
    
    return data


def calculate_longer_term_data(klines: List[Dict]) -> LongerTermData:
    """计算长期数据"""
    data = LongerTermData()
    
    # 转换为pandas DataFrame
    df = pd.DataFrame(klines)
    
    if df.empty:
        return data
        
    close_prices = df['close']
    high_prices = df['high']
    low_prices = df['low']
    volumes = df['volume']
    
    # 计算EMA
    if len(close_prices) >= 20:
        ema20_series = ta.ema(close_prices, length=20)
        if ema20_series is not None and not ema20_series.empty:
            data.ema20 = float(ema20_series.iloc[-1]) if not pd.isna(ema20_series.iloc[-1]) else 0.0
            
    if len(close_prices) >= 50:
        ema50_series = ta.ema(close_prices, length=50)
        if ema50_series is not None and not ema50_series.empty:
            data.ema50 = float(ema50_series.iloc[-1]) if not pd.isna(ema50_series.iloc[-1]) else 0.0
    
    # 计算ATR
    if len(high_prices) >= 14:
        atr3_series = ta.atr(high_prices, low_prices, close_prices, length=3)
        if atr3_series is not None and not atr3_series.empty:
            data.atr3 = float(atr3_series.iloc[-1]) if not pd.isna(atr3_series.iloc[-1]) else 0.0
            
        atr14_series = ta.atr(high_prices, low_prices, close_prices, length=14)
        if atr14_series is not None and not atr14_series.empty:
            data.atr14 = float(atr14_series.iloc[-1]) if not pd.isna(atr14_series.iloc[-1]) else 0.0
    
    # 计算成交量
    if len(volumes) > 0:
        data.current_volume = float(volumes.iloc[-1])
        data.average_volume = float(volumes.mean())
    
    # 计算MACD和RSI序列
    start = max(0, len(klines) - 10)
    
    # MACD序列
    if len(close_prices) >= 26:
        macd_df = ta.macd(close_prices, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            macd_series = macd_df['MACD_12_26_9']
            for i in range(start, len(klines)):
                if i >= 25:  # 需要至少26个数据点来计算MACD
                    data.macd_values.append(float(macd_series.iloc[i]) if not pd.isna(macd_series.iloc[i]) else 0.0)
    
    # RSI14序列
    if len(close_prices) >= 14:
        rsi14_series = ta.rsi(close_prices, length=14)
        if rsi14_series is not None:
            for i in range(start, len(klines)):
                if i >= 14:
                    data.rsi14_values.append(float(rsi14_series.iloc[i]) if not pd.isna(rsi14_series.iloc[i]) else 0.0)
    
    return data


def get_open_interest_data(symbol: str) -> OIData:
    """获取OI数据"""
    url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
    
    response = requests.get(url)
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
    
    response = requests.get(url)
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


def get(symbol: str) -> MarketData:
    """获取指定代币的市场数据"""
    # 标准化symbol
    symbol = normalize_symbol(symbol)
    
    # 获取3分钟K线数据 (最近10个)
    klines_3m = get_klines(symbol, "3m", 40)  # 多获取一些用于计算
    
    # 获取4小时K线数据 (最近10个)
    klines_4h = get_klines(symbol, "4h", 60)  # 多获取用于计算指标
    
    # 转换为pandas DataFrame
    df_3m = pd.DataFrame(klines_3m)
    df_4h = pd.DataFrame(klines_4h)
    
    # 计算当前指标 (基于3分钟最新数据)
    current_price = klines_3m[-1]["close"] if klines_3m else 0.0
    current_ema20 = 0.0
    current_macd = 0.0
    current_rsi7 = 0.0
    
    if not df_3m.empty:
        close_prices_3m = df_3m['close']
        
        # EMA20
        if len(close_prices_3m) >= 20:
            ema20_series = ta.ema(close_prices_3m, length=20)
            if ema20_series is not None and not ema20_series.empty:
                current_ema20 = float(ema20_series.iloc[-1]) if not pd.isna(ema20_series.iloc[-1]) else 0.0
                
        # MACD
        if len(close_prices_3m) >= 26:
            macd_df = ta.macd(close_prices_3m, fast=12, slow=26, signal=9)
            if macd_df is not None and not macd_df.empty:
                current_macd = float(macd_df.iloc[-1]['MACD_12_26_9']) if not pd.isna(macd_df.iloc[-1]['MACD_12_26_9']) else 0.0
                
        # RSI7
        if len(close_prices_3m) >= 7:
            rsi7_series = ta.rsi(close_prices_3m, length=7)
            if rsi7_series is not None and not rsi7_series.empty:
                current_rsi7 = float(rsi7_series.iloc[-1]) if not pd.isna(rsi7_series.iloc[-1]) else 0.0
    
    # 计算价格变化百分比
    # 1小时价格变化 = 20个3分钟K线前的价格
    price_change_1h = 0.0
    if len(klines_3m) >= 21:  # 至少需要21根K线 (当前 + 20根前)
        price_1h_ago = klines_3m[-21]["close"]
        if price_1h_ago > 0:
            price_change_1h = ((current_price - price_1h_ago) / price_1h_ago) * 100
    
    # 4小时价格变化 = 1个4小时K线前的价格
    price_change_4h = 0.0
    if len(klines_4h) >= 2:
        price_4h_ago = klines_4h[-2]["close"]
        if price_4h_ago > 0:
            price_change_4h = ((current_price - price_4h_ago) / price_4h_ago) * 100
    
    # 获取OI数据
    oi_data = None
    try:
        oi_data = get_open_interest_data(symbol)
    except Exception:
        # OI失败不影响整体,使用默认值
        oi_data = OIData(latest=0, average=0)
    
    # 获取Funding Rate
    funding_rate = 0.0
    try:
        funding_rate = get_funding_rate(symbol)
    except Exception:
        pass
    
    # 计算日内系列数据
    intraday_data = calculate_intraday_series(klines_3m)
    
    # 计算长期数据
    longer_term_data = calculate_longer_term_data(klines_4h)
    
    return MarketData(
        symbol=symbol,
        current_price=current_price,
        price_change_1h=price_change_1h,
        price_change_4h=price_change_4h,
        current_ema20=current_ema20,
        current_macd=current_macd,
        current_rsi7=current_rsi7,
        open_interest=oi_data,
        funding_rate=funding_rate,
        intraday_series=intraday_data,
        longer_term_context=longer_term_data,
    )


def format_market_data(data: MarketData) -> str:
    """格式化输出市场数据"""
    result = []
    
    result.append(f"current_price = {data.current_price:.2f}, current_ema20 = {data.current_ema20:.3f}, current_macd = {data.current_macd:.3f}, current_rsi (7 period) = {data.current_rsi7:.3f}\n\n")
    
    result.append(f"In addition, here is the latest {data.symbol} open interest and funding rate for perps:\n\n")
    
    if data.open_interest:
        result.append(f"Open Interest: Latest: {data.open_interest.latest:.2f} Average: {data.open_interest.average:.2f}\n\n")
    
    result.append(f"Funding Rate: {data.funding_rate:.2e}\n\n")
    
    if data.intraday_series:
        result.append("Intraday series (3‑minute intervals, oldest → latest):\n\n")
        
        if data.intraday_series.mid_prices:
            mid_prices_str = ", ".join([f"{p:.3f}" for p in data.intraday_series.mid_prices])
            result.append(f"Mid prices: [{mid_prices_str}]\n\n")
        
        if data.intraday_series.ema20_values:
            ema20_str = ", ".join([f"{p:.3f}" for p in data.intraday_series.ema20_values])
            result.append(f"EMA indicators (20‑period): [{ema20_str}]\n\n")
        
        if data.intraday_series.macd_values:
            macd_str = ", ".join([f"{p:.3f}" for p in data.intraday_series.macd_values])
            result.append(f"MACD indicators: [{macd_str}]\n\n")
        
        if data.intraday_series.rsi7_values:
            rsi7_str = ", ".join([f"{p:.3f}" for p in data.intraday_series.rsi7_values])
            result.append(f"RSI indicators (7‑Period): [{rsi7_str}]\n\n")
        
        if data.intraday_series.rsi14_values:
            rsi14_str = ", ".join([f"{p:.3f}" for p in data.intraday_series.rsi14_values])
            result.append(f"RSI indicators (14‑Period): [{rsi14_str}]\n\n")
    
    if data.longer_term_context:
        result.append("Longer‑term context (4‑hour timeframe):\n\n")
        
        result.append(f"20‑Period EMA: {data.longer_term_context.ema20:.3f} vs. 50‑Period EMA: {data.longer_term_context.ema50:.3f}\n\n")
        
        result.append(f"3‑Period ATR: {data.longer_term_context.atr3:.3f} vs. 14‑Period ATR: {data.longer_term_context.atr14:.3f}\n\n")
        
        result.append(f"Current Volume: {data.longer_term_context.current_volume:.3f} vs. Average Volume: {data.longer_term_context.average_volume:.3f}\n\n")
        
        if data.longer_term_context.macd_values:
            macd_str = ", ".join([f"{p:.3f}" for p in data.longer_term_context.macd_values])
            result.append(f"MACD indicators: [{macd_str}]\n\n")
        
        if data.longer_term_context.rsi14_values:
            rsi14_str = ", ".join([f"{p:.3f}" for p in data.longer_term_context.rsi14_values])
            result.append(f"RSI indicators (14‑Period): [{rsi14_str}]\n\n")
    
    return "".join(result)