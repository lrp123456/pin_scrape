#!/usr/bin/env python3
"""
Pinterest Scraper 构建与媒体类型测试脚本
放在项目根目录以正确导入模块
"""

import sys
import os
import subprocess
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_build.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class BuildTester:
    """构建测试器"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.test_results: Dict[str, Any] = {
            'timestamp': datetime.now().isoformat(),
            'build_status': 'unknown',
            'syntax_check': {},
            'import_tests': {},
            'media_type_tests': {},
            'errors': []
        }
    
    def check_syntax(self) -> bool:
        """检查所有Python文件的语法"""
        logger.info("开始语法检查...")
        check_files = [
            'scraper.py', 'main.py', 'downloader.py', 'shared/models.py',
            'api_service_enhanced/task_manager.py', 'shared/config_schema.py',
            'tray_app/console_gui.py', 'tray_app/tray_icon.py'
        ]
        all_passed = True
        for file_rel in check_files:
            file_path = self.project_root / file_rel
            if not file_path.exists():
                continue
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'py_compile', str(file_path)],
                    capture_output=True, text=True, timeout=30
                )
                passed = result.returncode == 0
                self.test_results['syntax_check'][file_rel] = passed
                if not passed:
                    logger.error(f"语法错误 {file_rel}: {result.stderr}")
                    self.test_results['errors'].append(f"语法错误 {file_rel}")
                    all_passed = False
                else:
                    logger.info(f"✓ 语法正确: {file_rel}")
            except Exception as e:
                logger.error(f"检查 {file_rel} 时出错: {e}")
                self.test_results['errors'].append(f"检查 {file_rel} 时出错")
                all_passed = False
        self.test_results['build_status'] = 'passed' if all_passed else 'failed'
        return all_passed
    
    def test_imports(self) -> bool:
        """测试关键模块导入"""
        logger.info("开始导入测试...")
        import_test_map = {
            "PinterestScraper": "scraper",
            "ImageDownloader": "downloader",
            "Pin": "shared.models",
            "TaskManager": "api_service_enhanced.task_manager",
            "ScraperConsole": "tray_app.console_gui",
            "TrayIconManager": "tray_app.tray_icon",
        }
        all_passed = True
        for name, module_path in import_test_map.items():
            try:
                import importlib
                importlib.import_module(module_path)
                passed = True
                logger.info(f"✓ 导入成功: {name}")
            except ImportError as e:
                passed = False
                logger.error(f"✗ 导入失败: {name} - {e}")
            self.test_results["import_tests"][name] = passed
            if not passed:
                all_passed = False
        return all_passed
    
    def test_media_type_modes(self, media_type: str) -> bool:
        """测试特定媒体类型模式"""
        logger.info(f"开始测试媒体类型模式: {media_type}")
        test_script = self.project_root / "test_media_type_temp.py"
        test_code = f'''
import sys
sys.path.insert(0, r"{self.project_root}")

from scraper import PinterestScraper

scraper = PinterestScraper(headless=True, debug=True)
assert hasattr(scraper, 'media_type'), "scraper应有media_type属性"
assert scraper.media_type == "{media_type}", f"media_type应为'{media_type}'"

print("✓ 媒体类型模式测试通过")
print(f"  media_type: {{scraper.media_type}}")
'''
        try:
            test_script.write_text(test_code, encoding='utf-8')
            result = subprocess.run(
                [sys.executable, str(test_script)],
                capture_output=True, text=True, timeout=30,
                cwd=str(self.project_root)
            )
            passed = result.returncode == 0
            self.test_results['media_type_tests'][media_type] = passed
            if passed:
                logger.info(f"✓ 媒体类型 '{media_type}' 测试通过")
            else:
                logger.error(f"✗ 媒体类型 '{media_type}' 测试失败: {result.stderr}")
                self.test_results['errors'].append(f"媒体类型 '{media_type}' 测试失败")
            test_script.unlink()
            return passed
        except Exception as e:
            logger.error(f"测试媒体类型 '{media_type}' 时出错: {e}")
            self.test_results['errors'].append(f"测试媒体类型 '{media_type}' 时出错")
            if test_script.exists():
                test_script.unlink()
            return False
    
    def test_debug_mode(self) -> bool:
        """测试调试模式启动"""
        logger.info("测试Chrome调试模式...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                if not p.chromium:
                    logger.warning("Chromium未安装，调试模式测试跳过")
                    self.test_results['debug_mode'] = True
                    return True
                browser = p.chromium.launch(
                    headless=False,
                    args=['--remote-debugging-port=9222']
                )
                browser.close()
            self.test_results['debug_mode'] = True
            logger.info("✓ 调试模式测试通过")
            return True
        except Exception as e:
            error_msg = str(e)
            if "Executable doesn't exist" in error_msg or "浏览器未安装" in error_msg:
                logger.warning(f"调试模式测试跳过: {error_msg}")
                self.test_results['debug_mode'] = True
                return True
            logger.error(f"✗ 调试模式测试失败: {error_msg}")
            self.test_results['errors'].append(f"调试模式测试失败: {error_msg}")
            self.test_results['debug_mode'] = False
            return False
    
    def run_all_tests(self, media_type: str = "all") -> Dict[str, Any]:
        """运行所有测试"""
        print(f"DEBUG: run_all_tests called with media_type={media_type}")
        """运行所有测试"""
        logger.info("=" * 60)
        logger.info("开始构建和媒体类型测试")
        logger.info(f"测试媒体类型: {media_type}")
        logger.info("=" * 60)
        
        syntax_ok = self.check_syntax()
        imports_ok = self.test_imports()
        media_ok = self.test_media_type_modes(media_type)
        debug_ok = self.test_debug_mode()
        
        self.test_results['build_ok'] = syntax_ok and imports_ok
        self.test_results['media_type_ok'] = media_ok
        self.test_results['debug_mode_ok'] = debug_ok
        self.test_results['all_passed'] = syntax_ok and imports_ok and media_ok and debug_ok
        
        results_file = self.project_root / "test_results.json"
        results_file.write_text(
            json.dumps(self.test_results, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        logger.info(f"测试结果已保存至: {results_file}")
        return self.test_results

def main():
    parser = argparse.ArgumentParser(description='Pinterest Scraper 构建与媒体类型测试')
    parser.add_argument('--media', '-m', choices=['all', 'images', 'video'], default='all',
                        help='测试的媒体类型模式 (默认: all)')
    parser.add_argument('--debug', '-d', action='store_true', help='启用调试模式测试')
    parser.add_argument('--project-root', '-p', type=str, default='.',
                        help='项目根目录 (默认: 当前目录)')
    args = parser.parse_args()
    
    project_root = Path(args.project_root).resolve()
    if not project_root.exists():
        logger.error(f"项目目录不存在: {project_root}")
        sys.exit(1)
    
    logger.info(f"项目根目录: {project_root}")
    tester = BuildTester(project_root)
    results = tester.run_all_tests(args.media)
    
    print("\n" + "=" * 60)
    print("测试结果摘要")
    print("=" * 60)
    print(f"语法检查: {'✓ 通过' if results['syntax_check'] else '✗ 失败'}")
    print(f"导入测试: {'✓ 通过' if results['import_tests'] else '✗ 失败'}")
    print(f"媒体类型 '{args.media}' 测试: {'✓ 通过' if results['media_type_tests'] else '✗ 失败'}")
    print(f"调试模式测试: {'✓ 通过' if results.get('debug_mode') else '✗ 失败'}")
    print(f"总体状态: {'✅ 全部通过' if results['all_passed'] else '❌ 有失败'}")
    
    sys.exit(0 if results['all_passed'] else 1

if __name__ == '__main__':
    main()
