"""
测试FastAPI实现的简单脚本
这个脚本用于验证FastAPI服务器的基本功能
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_fastapi_implementation():
    """测试FastAPI实现"""
    print("测试FastAPI实现...")
    
    # 检查是否可以导入FastAPI相关模块
    try:
        from fastapi import FastAPI
        print("✓ FastAPI导入成功")
    except ImportError as e:
        print(f"✗ FastAPI导入失败: {e}")
        return False
    
    try:
        import uvicorn
        print("✓ Uvicorn导入成功")
    except ImportError as e:
        print(f"✗ Uvicorn导入失败: {e}")
        return False
    
    try:
        from api.server import Server
        print("✓ Server类导入成功")
    except ImportError as e:
        print(f"✗ Server类导入失败: {e}")
        return False
    
    print("所有导入测试通过!")
    return True

if __name__ == "__main__":
    test_fastapi_implementation()