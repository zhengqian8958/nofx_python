import requests

def test_binance_connectivity() -> bool:
    """测试Binance网络接口是否畅通"""
    try:
        # 测试获取BTCUSDT的K线数据
        url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=1"
        proxy_str = "http://bhhftd7dai-corp.mobile.res-country-DE-state-2951839-city-2867714-hold-session-session-690e57c8c3c6e:iu3i7lOrrqzLKO4i@lpm-shared-26.asocks-servers.net:443"
        proxies = {"http":f"{proxy_str}","https":f"{proxy_str}"}
        response = requests.get(url, timeout=10, proxies=proxies)
        
        # 检查响应状态码
        if response.status_code == 200:
            # 检查响应内容是否为有效的JSON
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                print("✅ Binance网络接口测试成功")
                print(f"   响应状态码: {response.status_code}")
                print(f"   返回数据点数: {len(data)}")
                return True
            else:
                print("❌ Binance网络接口测试失败: 返回数据格式不正确")
                return False
        else:
            print(f"❌ Binance网络接口测试失败: HTTP状态码 {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        print("❌ Binance网络接口测试失败: 请求超时")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Binance网络接口测试失败: 网络连接错误")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Binance网络接口测试失败: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Binance网络接口测试失败: 未知错误 - {str(e)}")
        return False


if __name__ == "__main__":
    # 测试Binance连接
    if test_binance_connectivity():
        print("Binance连接正常，可以继续执行交易操作")
    else:
        print("Binance连接异常，请检查网络或API配置")
