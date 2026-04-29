"""验证码识别功能测试脚本

测试captcha-recognizer库是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

def test_captcha_recognizer():
    """测试captcha-recognizer库"""
    try:
        from captcha_recognizer.slider import Slider
        print("✅ captcha-recognizer库导入成功")
        
        # 创建Slider实例
        slider = Slider()
        print("✅ Slider实例创建成功")
        
        # 测试识别功能（使用示例图片）
        # 注意：这里需要一个实际的滑块验证码图片才能测试
        # 由于没有实际图片，我们只测试库是否能正常导入和初始化
        
        print("\n✅ captcha-recognizer库测试通过")
        print("安装命令：pip install captcha-recognizer opencv-python numpy")
        
        return True
        
    except ImportError as e:
        print(f"❌ captcha-recognizer库导入失败: {e}")
        print("请安装：pip install captcha-recognizer opencv-python numpy")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_captcha_solver():
    """测试CaptchaSolver类"""
    try:
        from scrapers.sanvjia_scraper import CaptchaSolver
        
        print("\n测试 CaptchaSolver 类...")
        solver = CaptchaSolver(debug=True)
        
        if solver.slider_recognizer:
            print("✅ CaptchaSolver初始化成功，captcha-recognizer已加载")
        else:
            print("⚠️ CaptchaSolver初始化成功，但captcha-recognizer未加载")
        
        return True
        
    except Exception as e:
        print(f"❌ CaptchaSolver测试失败: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("验证码识别功能测试")
    print("=" * 50)
    
    success1 = test_captcha_recognizer()
    success2 = test_captcha_solver()
    
    print("\n" + "=" * 50)
    if success1 and success2:
        print("✅ 所有测试通过")
    else:
        print("❌ 部分测试失败")
    print("=" * 50)
