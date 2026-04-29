#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""页面失效修复专项测试脚本

测试目标：验证 _is_page_alive, _safe_go_back, _ensure_page_alive 的健壮性

运行方式：
    方式1 - 连接已有浏览器（推荐，需要 Chrome 在 9222 端口运行）：
        python test_page_robustness.py --connect

    方式2 - 自动启动浏览器：
        python test_page_robustness.py

    方式3 - 详细调试输出：
        python test_page_robustness.py --connect --debug
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper import PinterestScraper


class PageRobustnessTester:
    def __init__(self, connect=False, debug=False):
        self.connect = connect
        self.debug = debug
        self.scraper = None

    def setup(self):
        """初始化爬虫"""
        print("\n[初始化] 启动 PinterestScraper...")
        if self.connect:
            self.scraper = PinterestScraper(
                headless=False,
                debug=self.debug,
                cdp_endpoint="http://localhost:9222",
                log_file="test_robustness.log"
            )
        else:
            self.scraper = PinterestScraper(
                headless=False,
                debug=self.debug,
                log_file="test_robustness.log"
            )
        self.scraper.start()
        print("[初始化] 完成")

    def teardown(self):
        """关闭爬虫"""
        if self.scraper:
            print("\n[清理] 关闭浏览器...")
            self.scraper.close()
            print("[清理] 完成")

    # ------------------------------------------------------------------
    # 测试1: _is_page_alive 基础检测
    # ------------------------------------------------------------------
    def test_is_page_alive_normal(self):
        """测试1: 正常页面存活检测"""
        print("\n" + "=" * 60)
        print("测试1: _is_page_alive - 正常页面")
        print("=" * 60)

        self.scraper.page.goto("https://kr.pinterest.com")
        time.sleep(2)

        alive = self.scraper._is_page_alive()
        print(f"  页面存活状态: {alive}")
        assert alive, "正常页面应该返回 True"
        print("  ✓ 通过")

    def test_is_page_alive_after_close(self):
        """测试2: 页面关闭后检测"""
        print("\n" + "=" * 60)
        print("测试2: _is_page_alive - 页面关闭后")
        print("=" * 60)

        # 打开一个新页面，然后关闭它
        new_page = self.scraper.context.new_page()
        new_page.goto("https://example.com")
        time.sleep(1)

        alive_before = self.scraper._is_page_alive()
        print(f"  原页面存活状态(新页打开时): {alive_before}")

        new_page.close()
        time.sleep(1)

        # 原页面应该仍然存活
        alive_after = self.scraper._is_page_alive()
        print(f"  原页面存活状态(新页关闭后): {alive_after}")
        assert alive_after, "关闭新页面不应影响原页面"
        print("  ✓ 通过")

    # ------------------------------------------------------------------
    # 测试2: _safe_go_back 安全后退
    # ------------------------------------------------------------------
    def test_safe_go_back_normal(self):
        """测试3: 正常后退场景"""
        print("\n" + "=" * 60)
        print("测试3: _safe_go_back - 正常后退")
        print("=" * 60)

        # 先访问两个不同页面
        self.scraper.page.goto("https://kr.pinterest.com/search/pins/?q=design")
        time.sleep(2)
        before_url = self.scraper.page.url
        print(f"  当前URL: {before_url}")

        self.scraper.page.goto("https://kr.pinterest.com/search/pins/?q=home")
        time.sleep(2)
        print(f"  跳转后URL: {self.scraper.page.url}")

        # 安全后退
        result = self.scraper._safe_go_back()
        print(f"  后退结果: {result}")
        print(f"  后退后URL: {self.scraper.page.url}")

        assert result, "正常后退应该返回 True"
        assert self.scraper._is_page_alive(), "后退后页面应该仍然存活"
        print("  ✓ 通过")

    def test_safe_go_back_to_blank(self):
        """测试4: 后退到 about:blank 的防护"""
        print("\n" + "=" * 60)
        print("测试4: _safe_go_back - 异常页面检测")
        print("=" * 60)

        # 导航到 about:blank 模拟页面死亡状态
        print("  模拟导航到 about:blank...")
        self.scraper.page.goto("about:blank")
        time.sleep(1)

        alive = self.scraper._is_page_alive()
        print(f"  about:blank 页面存活状态: {alive}")

        # about:blank 在 Playwright 中仍然是"存活"的，但 _safe_go_back 会检测 URL
        # 如果当前已经在 about:blank，尝试后退应该能检测到异常
        result = self.scraper._safe_go_back(fallback_url="https://kr.pinterest.com")
        print(f"  带 fallback 的后退结果: {result}")

        # 检查是否恢复到了 fallback URL
        current_url = self.scraper.page.url
        print(f"  当前URL: {current_url}")

        assert "pinterest.com" in current_url, f"应该恢复到 fallback URL，实际: {current_url}"
        print("  ✓ 通过")

    # ------------------------------------------------------------------
    # 测试3: _ensure_page_alive 页面恢复
    # ------------------------------------------------------------------
    def test_ensure_page_alive(self):
        """测试5: 页面失效后自动恢复"""
        print("\n" + "=" * 60)
        print("测试5: _ensure_page_alive - 页面恢复")
        print("=" * 60)

        # 先确保在正常页面
        self.scraper.page.goto("https://kr.pinterest.com/search/pins/?q=art")
        time.sleep(2)
        print(f"  初始URL: {self.scraper.page.url}")

        # 导航到 about:blank 模拟失效
        self.scraper.page.goto("about:blank")
        time.sleep(1)
        print(f"  失效后URL: {self.scraper.page.url}")

        # 尝试恢复
        recovered = self.scraper._ensure_page_alive(
            fallback_url="https://kr.pinterest.com/search/pins/?q=design"
        )
        print(f"  恢复结果: {recovered}")
        print(f"  恢复后URL: {self.scraper.page.url}")

        assert recovered, "恢复应该成功"
        assert self.scraper._is_page_alive(), "恢复后页面应该存活"
        assert "search" in self.scraper.page.url, "应该恢复到搜索页"
        print("  ✓ 通过")

    # ------------------------------------------------------------------
    # 测试4: 实际爬坡场景压力测试
    # ------------------------------------------------------------------
    def test_climb_with_page_check(self):
        """测试6: 爬坡循环中页面检查的实际效果"""
        print("\n" + "=" * 60)
        print("测试6: 爬坡循环页面存活检查")
        print("=" * 60)

        keyword = "design"
        print(f"  搜索关键词: {keyword}")

        # 执行一次真实的搜索（使用少量数据，快速完成）
        pins = self.scraper.search(
            keyword=keyword,
            max_pins=5,
            min_saves=0
        )

        print(f"  收集到 {len(pins)} 个 pin")
        for p in pins[:3]:
            print(f"    - {p.id}: saves={p.saves}")

        # 关键验证：整个过程没有因为页面失效而崩溃
        assert self.scraper._is_page_alive(), "搜索完成后页面应该仍然存活"
        print("  ✓ 通过")

    def test_multiple_back_operations(self):
        """测试7: 连续多次后退操作"""
        print("\n" + "=" * 60)
        print("测试7: 连续多次后退的压力测试")
        print("=" * 60)

        # 构建一个历史栈：A -> B -> C -> D
        urls = [
            "https://kr.pinterest.com/search/pins/?q=a",
            "https://kr.pinterest.com/search/pins/?q=b",
            "https://kr.pinterest.com/search/pins/?q=c",
            "https://kr.pinterest.com/search/pins/?q=d",
        ]

        for i, url in enumerate(urls):
            self.scraper.page.goto(url)
            time.sleep(1)
            print(f"  访问 [{i+1}]: {url}")

        # 连续后退 3 次
        for i in range(3):
            result = self.scraper._safe_go_back()
            print(f"  第 {i+1} 次后退结果: {result}, URL: {self.scraper.page.url}")
            assert result, f"第 {i+1} 次后退应该成功"
            assert self.scraper._is_page_alive(), f"第 {i+1} 次后退后页面应存活"

        print("  ✓ 通过")

    # ------------------------------------------------------------------
    # 运行所有测试
    # ------------------------------------------------------------------
    def run_all_tests(self):
        tests = [
            ("基础存活检测", self.test_is_page_alive_normal),
            ("关闭后检测", self.test_is_page_alive_after_close),
            ("正常后退", self.test_safe_go_back_normal),
            ("异常页面防护", self.test_safe_go_back_to_blank),
            ("页面恢复", self.test_ensure_page_alive),
            ("爬坡场景", self.test_climb_with_page_check),
            ("连续后退压力", self.test_multiple_back_operations),
        ]

        passed = 0
        failed = 0
        results = []

        print("\n" + "=" * 60)
        print("Pinterest 页面失效修复 专项测试")
        print("=" * 60)
        print(f"测试数量: {len(tests)}")
        print(f"连接模式: {'CDP (9222)' if self.connect else '自动启动'}")
        print(f"调试模式: {'开' if self.debug else '关'}")

        for name, test_func in tests:
            print(f"\n{'─' * 60}")
            print(f"准备运行: {name}")
            try:
                test_func()
                passed += 1
                results.append((name, "通过", ""))
            except Exception as e:
                failed += 1
                results.append((name, "失败", str(e)))
                print(f"\n  ✗ 失败: {e}")
                import traceback
                traceback.print_exc()

        # 打印总结
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        for name, status, error in results:
            symbol = "✓" if status == "通过" else "✗"
            print(f"{symbol} {name}: {status}")
            if error:
                print(f"    错误: {error}")

        print(f"\n总计: {passed} 通过, {failed} 失败")
        success_rate = passed / len(tests) * 100
        print(f"成功率: {success_rate:.1f}%")

        return failed == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(description="页面失效修复专项测试")
    parser.add_argument("--connect", action="store_true", help="连接到已有浏览器 (localhost:9222)")
    parser.add_argument("--debug", action="store_true", help="启用调试输出")
    args = parser.parse_args()

    tester = PageRobustnessTester(connect=args.connect, debug=args.debug)

    try:
        tester.setup()
        all_passed = tester.run_all_tests()
    finally:
        tester.teardown()

    if all_passed:
        print("\n🎉 所有测试通过！页面失效修复工作正常。")
        sys.exit(0)
    else:
        print("\n⚠️  有测试失败，请检查修复。")
        sys.exit(1)


if __name__ == "__main__":
    main()
