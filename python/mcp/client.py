import json
import time
import requests
from typing import Dict, List, Optional, Tuple
from enum import Enum


class Provider(Enum):
    """AI提供商类型"""
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    CUSTOM = "custom"


class Config:
    """AI API配置"""
    def __init__(self):
        self.provider: Provider = Provider.DEEPSEEK
        self.api_key: str = ""
        self.secret_key: str = ""  # 阿里云需要
        self.base_url: str = "https://api.deepseek.com/v1"
        self.model: str = "deepseek-chat"
        self.timeout: int = 120  # 增加到120秒，因为AI需要分析大量数据


# 默认配置
default_config = Config()


def set_deepseek_api_key(api_key: str) -> None:
    """设置DeepSeek API密钥"""
    global default_config
    default_config.provider = Provider.DEEPSEEK
    default_config.api_key = api_key
    default_config.base_url = "https://api.deepseek.com/v1"
    default_config.model = "deepseek-chat"


def set_qwen_api_key(api_key: str, secret_key: str) -> None:
    """设置阿里云Qwen API密钥"""
    global default_config
    default_config.provider = Provider.QWEN
    default_config.api_key = api_key
    default_config.secret_key = secret_key
    default_config.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_config.model = "qwen-plus"  # 可选: qwen-turbo, qwen-plus, qwen-max


def set_custom_api(api_url: str, api_key: str, model_name: str) -> None:
    """设置自定义OpenAI兼容API"""
    global default_config
    default_config.provider = Provider.CUSTOM
    default_config.api_key = api_key
    default_config.base_url = api_url
    default_config.model = model_name
    default_config.timeout = 120


def call_with_messages(system_prompt: str, user_prompt: str) -> str:
    """使用 system + user prompt 调用AI API（推荐）"""
    global default_config
    
    # 添加调试信息
    print(f"DEBUG: AI Provider: {default_config.provider}")
    print(f"DEBUG: API Key: {default_config.api_key[:10]}..." if default_config.api_key else "DEBUG: API Key: None")
    print(f"DEBUG: Base URL: {default_config.base_url}")
    print(f"DEBUG: Model: {default_config.model}")
    
    if not default_config.api_key:
        raise Exception("AI API密钥未设置，请先调用 set_deepseek_api_key() 或 set_qwen_api_key()")
    
    # 重试配置
    max_retries = 3
    last_err = None
    
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"⚠️  AI API调用失败，正在重试 ({attempt}/{max_retries})...")
        
        try:
            result = _call_once(system_prompt, user_prompt)
            if attempt > 1:
                print("✓ AI API重试成功")
            return result
        except Exception as e:
            last_err = e
            # 如果不是网络错误，不重试
            if not _is_retryable_error(str(e)):
                raise e
            
            # 重试前等待
            if attempt < max_retries:
                wait_time = attempt * 2
                print(f"⏳ 等待{wait_time}秒后重试...")
                time.sleep(wait_time)
    
    raise Exception(f"重试{max_retries}次后仍然失败: {last_err}")


def _call_once(system_prompt: str, user_prompt: str) -> str:
    """单次调用AI API（内部使用）"""
    global default_config
    
    # 构建 messages 数组
    messages = []
    
    # 如果有 system prompt，添加 system message
    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt,
        })
    
    # 添加 user message
    messages.append({
        "role": "user",
        "content": user_prompt,
    })
    
    # 构建请求体
    request_body = {
        "model": default_config.model,
        "messages": messages,
        "temperature": 0.5,  # 降低temperature以提高JSON格式稳定性
        "max_tokens": 2000,
    }
    
    # 注意：response_format 参数仅 OpenAI 支持，DeepSeek/Qwen 不支持
    # 我们通过强化 prompt 和后处理来确保 JSON 格式正确
    
    # 创建HTTP请求
    url = f"{default_config.base_url}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
    }
    
    # 根据不同的Provider设置认证方式
    if default_config.provider == Provider.DEEPSEEK:
        headers["Authorization"] = f"Bearer {default_config.api_key}"
    elif default_config.provider == Provider.QWEN:
        # 阿里云Qwen使用API-Key认证
        headers["Authorization"] = f"Bearer {default_config.api_key}"
    else:
        headers["Authorization"] = f"Bearer {default_config.api_key}"
    
    # 发送请求
    try:
        response = requests.post(
            url,
            headers=headers,
            json=request_body,
            timeout=default_config.timeout
        )
        response.raise_for_status()
        
        result = response.json()
        
        if not result.get("choices"):
            raise Exception("API返回空响应")
        
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        raise Exception(f"发送请求失败: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"解析响应失败: {e}")
    except Exception as e:
        raise Exception(f"API返回错误: {e}")


def _is_retryable_error(err_str: str) -> bool:
    """判断错误是否可重试"""
    # 网络错误、超时、EOF等可以重试
    retryable_errors = [
        "EOF",
        "timeout",
        "connection reset",
        "connection refused",
        "temporary failure",
        "no such host",
    ]
    for retryable in retryable_errors:
        if retryable in err_str:
            return True
    return False