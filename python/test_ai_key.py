import sys
import os

# 添加项目根目录到sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.config import load_config
from mcp.client import default_config

def test_ai_key():
    """测试AI密钥配置"""
    print("=== AI密钥配置测试 ===")
    
    # 加载配置
    try:
        cfg = load_config("config.json")
        print(f"✓ 配置加载成功")
        print(f"  共有 {len(cfg.traders)} 个trader配置")
        
        # 检查启用的trader
        enabled_traders = [t for t in cfg.traders if t.enabled]
        print(f"  启用的trader数量: {len(enabled_traders)}")
        
        for i, trader in enumerate(enabled_traders):
            print(f"\nTrader {i+1}: {trader.name}")
            print(f"  AI模型: {trader.ai_model}")
            if trader.ai_model == "deepseek":
                print(f"  DeepSeek密钥: {'已设置' if trader.deepseek_key else '未设置'}")
                if trader.deepseek_key:
                    print(f"  密钥前缀: {trader.deepseek_key[:10]}...")
            elif trader.ai_model == "qwen":
                print(f"  Qwen密钥: {'已设置' if trader.qwen_key else '未设置'}")
                if trader.qwen_key:
                    print(f"  密钥前缀: {trader.qwen_key[:10]}...")
            elif trader.ai_model == "custom":
                print(f"  自定义API URL: {trader.custom_api_url}")
                print(f"  自定义API密钥: {'已设置' if trader.custom_api_key else '未设置'}")
                print(f"  自定义模型名: {trader.custom_model_name}")
                
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return
    
    print("\n=== MCP客户端默认配置 ===")
    print(f"Provider: {default_config.provider}")
    print(f"API密钥: {'已设置' if default_config.api_key else '未设置'}")
    if default_config.api_key:
        print(f"API密钥前缀: {default_config.api_key[:10]}...")
    print(f"Base URL: {default_config.base_url}")
    print(f"模型: {default_config.model}")

if __name__ == "__main__":
    test_ai_key()