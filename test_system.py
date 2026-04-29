#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pinterest 爬虫系统稳定性测试脚本"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper import PinterestScraper


class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = False
        self.message = ""
        self.duration = 0
        self.details = {}


class SystemTester:
    def __init__(self, cdp_endpoint="http://localhost:9222", debug=False):
        self.cdp_endpoint = cdp_endpoint
        self.debug = debug
        self.results = []

    def run_test(self, test_func):
        result = TestResult(test_func.__name__)
        print(f"\n{'=' * 60}")
        print(f"测试: {test_func.__doc__}")
        print(f"{'=' * 60}")
        
        start_time = time.time()
        try:
            test_func(result)
            result.passed = True
        except Exception as e:
            result.passed = False
            result.message = str(e)
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
        
        result.duration = time.time() - start_time
        self.results.append(result)
        
        if result.passed:
            print(f"✓ 测试通过 ({result.duration:.2f}秒)")
        else:
            print(f"✗ 测试失败 ({result.duration:.2f}秒)")
        
        return result.passed

    def test_viewport_size(self, result):
        """测试1: 视口大小设置"""
        with PinterestScraper(
            headless=False,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint
        ) as scraper:
            viewport = scraper.page.viewport_size
            result.details['viewport'] = viewport
            
            print(f"视口大小: {viewport}")
            
            if viewport['width'] < 1000 or viewport['height'] < 500:
                raise AssertionError(f"视口大小异常: {viewport}")
            
            result.message = f"视口大小正常: {viewport}"

    def test_page_load(self, result):
        """测试2: 页面加载"""
        with PinterestScraper(
            headless=False,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint
        ) as scraper:
            scraper.page.goto("https://kr.pinterest.com/search/pins/?q=test", wait_until="domcontentloaded")
            time.sleep(3)
            
            url = scraper.page.url
            title = scraper.page.title()
            
            result.details['url'] = url
            result.details['title'] = title
            
            print(f"URL: {url}")
            print(f"标题: {title}")
            
            if "pinterest.com" not in url:
                raise AssertionError(f"页面加载失败，URL: {url}")
            
            result.message = "页面加载成功"

    def test_pin_detection(self, result):
        """测试3: Pin 元素检测"""
        with PinterestScraper(
            headless=False,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint
        ) as scraper:
            scraper.page.goto("https://kr.pinterest.com/search/pins/?q=design", wait_until="domcontentloaded")
            time.sleep(5)
            
            pin_ids = scraper._get_search_page_pin_ids()
            result.details['pin_count'] = len(pin_ids)
            result.details['sample_ids'] = pin_ids[:3] if pin_ids else []
            
            print(f"检测到 {len(pin_ids)} 个 pin")
            if pin_ids:
                print(f"示例 ID: {pin_ids[:3]}")
            
            if len(pin_ids) == 0:
                raise AssertionError("未检测到任何 pin 元素")
            
            result.message = f"检测到 {len(pin_ids)} 个 pin"

    def test_data_extraction(self, result):
        """测试4: 数据提取"""
        with PinterestScraper(
            headless=False,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint
        ) as scraper:
            scraper.page.goto("https://kr.pinterest.com/search/pins/?q=design", wait_until="domcontentloaded")
            time.sleep(5)
            
            pin_ids = scraper._get_search_page_pin_ids()
            if not pin_ids:
                raise AssertionError("未找到 pin，无法测试数据提取")
            
            test_pin_id = pin_ids[0]
            print(f"测试 pin ID: {test_pin_id}")
            
            pin_link = scraper.page.query_selector(f'a[href*="/pin/{test_pin_id}"]')
            if not pin_link:
                raise AssertionError(f"未找到 pin {test_pin_id} 的链接")
            
            pin_link.click()
            time.sleep(3)
            
            details = scraper._extract_pin_details_from_modal()
            result.details['extracted_data'] = details
            
            print(f"提取的数据: {json.dumps(details, ensure_ascii=False, indent=2)}")
            
            if not details or not details.get('id'):
                raise AssertionError("数据提取失败")
            
            result.message = f"成功提取数据，saves={details.get('saves', 0)}"

    def test_scroll_collection(self, result):
        """测试5: 滚动收集模式"""
        with PinterestScraper(
            headless=False,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint
        ) as scraper:
            pins = scraper.search(keyword="design", max_pins=5, min_saves=0)
            
            result.details['collected_count'] = len(pins)
            result.details['sample_pins'] = [
                {'id': p.id, 'saves': p.saves, 'title': p.title[:30]}
                for p in pins[:3]
            ]
            
            print(f"收集到 {len(pins)} 个 pin")
            for i, pin in enumerate(pins[:3], 1):
                print(f"  {i}. ID={pin.id}, saves={pin.saves}, title={pin.title[:30]}")
            
            if len(pins) == 0:
                raise AssertionError("滚动收集模式未收集到任何数据")
            
            result.message = f"收集到 {len(pins)} 个 pin"

    def test_explore_mode(self, result):
        """测试6: 探索模式（带筛选）"""
        with PinterestScraper(
            headless=False,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint
        ) as scraper:
            pins = scraper.search(keyword="design", max_pins=3, min_saves=50)
            
            result.details['collected_count'] = len(pins)
            result.details['qualified_pins'] = [
                {'id': p.id, 'saves': p.saves, 'title': p.title[:30]}
                for p in pins
            ]
            
            print(f"收集到 {len(pins)} 个达标 pin (min_saves=50)")
            for i, pin in enumerate(pins, 1):
                print(f"  {i}. ID={pin.id}, saves={pin.saves}, title={pin.title[:30]}")
            
            if len(pins) == 0:
                print("警告: 未收集到达标 pin，可能是筛选条件太严格")
            
            result.message = f"探索模式收集到 {len(pins)} 个达标 pin"

    def run_all_tests(self):
        print("\n" + "=" * 60)
        print("Pinterest 爬虫系统稳定性测试")
        print("=" * 60)
        
        tests = [
            self.test_viewport_size,
            self.test_page_load,
            self.test_pin_detection,
            self.test_data_extraction,
            self.test_scroll_collection,
            self.test_explore_mode,
        ]
        
        for test in tests:
            self.run_test(test)
            time.sleep(2)
        
        self.print_summary()

    def print_summary(self):
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        for result in self.results:
            status = "✓" if result.passed else "✗"
            print(f"{status} {result.name}: {result.message} ({result.duration:.2f}秒)")
        
        print(f"\n通过: {passed}/{total}")
        print(f"成功率: {passed/total*100:.1f}%")
        
        if passed == total:
            print("\n🎉 所有测试通过！系统稳定。")
        else:
            print(f"\n⚠️  {total - passed} 个测试失败，需要修复。")
        
        report_file = "test_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'total': total,
                'passed': passed,
                'failed': total - passed,
                'results': [
                    {
                        'name': r.name,
                        'passed': r.passed,
                        'message': r.message,
                        'duration': r.duration,
                        'details': r.details
                    }
                    for r in self.results
                ]
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n详细报告已保存到: {report_file}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Pinterest 爬虫系统稳定性测试")
    parser.add_argument("--cdp-endpoint", default="http://localhost:9222", help="Chrome CDP 端点")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    
    args = parser.parse_args()
    
    tester = SystemTester(cdp_endpoint=args.cdp_endpoint, debug=args.debug)
    tester.run_all_tests()
