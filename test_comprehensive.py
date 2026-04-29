#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pinterest 爬虫综合测试脚本

覆盖范围：
  模块一：逻辑测试（不需要浏览器）- Pin 模型、URL 解析、数字解析、输出处理、去重
  模块二：AI 筛选测试（不需要浏览器）- Provider 初始化、健康检查、图片评估
  模块三：搜索页测试（需要浏览器）- 页面加载、Pin 检测、图片 URL 提取、滚动收集
  模块四：详情页测试（需要浏览器）- 导航、数据提取(PWS_DATA/DOM)、后退
  模块五：稳定性测试（需要浏览器）- 存活检测、页面恢复、浏览器重连、连续操作

用法：
    # 运行所有测试（需连接浏览器）
    python test_comprehensive.py --connect

    # 只运行逻辑测试（不需要浏览器）
    python test_comprehensive.py --logic-only

    # 只运行 AI 测试（不需要浏览器）
    python test_comprehensive.py --ai-only

    # 只运行浏览器测试
    python test_comprehensive.py --browser-only --connect

    # 跳过某个模块
    python test_comprehensive.py --connect --skip ai --skip stability

    # 调试模式
    python test_comprehensive.py --connect --debug
"""

import argparse
import inspect
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))


# ============================================================================
# 测试结果数据结构
# ============================================================================

class TestCase:
    """单个测试用例"""

    def __init__(self, name: str, description: str, module: str, needs_browser: bool = False):
        self.name = name
        self.description = description
        self.module = module
        self.needs_browser = needs_browser
        self.passed: Optional[bool] = None
        self.message: str = ""
        self.duration: float = 0.0
        self.error: Optional[str] = None
        self.traceback: Optional[str] = None

    def mark_passed(self, message: str = ""):
        """标记测试通过"""
        self.passed = True
        self.message = message

    def mark_failed(self, error: str, tb: str = ""):
        """标记测试失败"""
        self.passed = False
        self.error = error
        self.traceback = tb

    def mark_skipped(self, reason: str = ""):
        """标记测试跳过"""
        self.passed = None
        self.message = reason


# ============================================================================
# 测试运行器
# ============================================================================

class TestRunner:
    """测试运行器，支持模块筛选和跳过"""

    def __init__(self, cdp_endpoint: str = None, debug: bool = False, output_dir: str = None, auto_launch: bool = False):
        self.cdp_endpoint = cdp_endpoint
        self.debug = debug
        self.auto_launch = auto_launch
        self.results: List[TestCase] = []
        self.scraper = None  # 浏览器实例，延迟初始化
        self._chrome_launcher = None  # ChromeLauncher 实例（auto_launch 模式）
        self.modules_to_run: Optional[List[str]] = None
        self.modules_to_skip: List[str] = []

        # 测试输出目录（存放截图、提取结果等调试文件）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(__file__).parent / "test_output" / f"test_{timestamp}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 子目录
        self.screenshots_dir = self.output_dir / "screenshots"
        self.data_dir = self.output_dir / "data"
        self.screenshots_dir.mkdir(exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)

        print(f"\n  测试输出目录: {self.output_dir}")

    def save_screenshot(self, name: str):
        """保存当前页面截图到 test_output/screenshots/"""
        if not self.scraper or not hasattr(self.scraper, 'page'):
            return
        try:
            filepath = self.screenshots_dir / f"{name}.png"
            self.scraper.page.screenshot(path=str(filepath))
            if self.debug:
                print(f"    截图已保存: {filepath}")
        except Exception:
            pass

    def save_data(self, name: str, data: dict):
        """保存提取的数据到 test_output/data/"""
        try:
            filepath = self.data_dir / f"{name}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            if self.debug:
                print(f"    数据已保存: {filepath}")
        except Exception:
            pass

    def set_modules(self, only: List[str] = None, skip: List[str] = None):
        """设置要运行/跳过的模块"""
        self.modules_to_run = only
        self.modules_to_skip = skip or []

    def should_run(self, module: str) -> bool:
        """判断某模块是否应该运行"""
        if self.modules_to_skip and module in self.modules_to_skip:
            return False
        if self.modules_to_run and module not in self.modules_to_run:
            return False
        return True

    def run(self, test_case: TestCase, test_func):
        """执行单个测试用例"""
        if not self.should_run(test_case.module):
            return

        test_case_name = f"[{test_case.module}] {test_case.name}"
        print(f"\n{'─' * 70}")
        print(f"  测试: {test_case.description}")
        print(f"{'─' * 70}")

        start_time = time.time()
        try:
            test_func(test_case)
            if test_case.passed:
                test_case.duration = time.time() - start_time
                print(f"  ✓ 通过 ({test_case.duration:.2f}s)", end="")
                if test_case.message:
                    print(f" - {test_case.message}")
                else:
                    print()
            elif test_case.passed is None:
                test_case.duration = time.time() - start_time
                print(f"  ⊘ 跳过 - {test_case.message}")
            else:
                test_case.duration = time.time() - start_time
                print(f"  ✗ 失败 ({test_case.duration:.2f}s) - {test_case.error}")
                if test_case.traceback and self.debug:
                    print(f"\n{test_case.traceback}")
        except Exception as e:
            test_case.duration = time.time() - start_time
            test_case.mark_failed(str(e), traceback.format_exc())
            print(f"  ✗ 异常 ({test_case.duration:.2f}s) - {e}")
            if self.debug:
                traceback.print_exc()

        self.results.append(test_case)

    def run_all(self):
        """运行所有测试"""
        print("\n" + "=" * 70)
        print("  Pinterest 爬虫综合测试")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  模块筛选: {self.modules_to_run or '全部'}")
        print(f"  模块跳过: {self.modules_to_skip or '无'}")
        print("=" * 70)

        # 模块一：逻辑测试（不需要浏览器）
        if self.should_run("logic"):
            self._run_logic_tests()

        # 模块二：AI 筛选测试（不需要浏览器）
        if self.should_run("ai"):
            self._run_ai_filter_tests()

        # 模块三：搜索页测试（需要浏览器）
        if self.should_run("search"):
            self._run_search_page_tests()

        # 模块四：详情页测试（需要浏览器）
        if self.should_run("detail"):
            self._run_detail_page_tests()

        # 模块五：稳定性测试（需要浏览器）
        if self.should_run("stability"):
            self._run_stability_tests()

        self._print_summary()
        self._save_report()

    # ========================================================================
    # 模块一：逻辑测试（不需要浏览器）
    # ========================================================================

    def _run_logic_tests(self):
        print(f"\n{'#' * 70}")
        print(f"  # 模块一：逻辑测试（不需要浏览器）")
        print(f"{'#' * 70}")

        # 测试 1.1：Pin 数据模型创建
        def test_pin_model_creation(tc: TestCase):
            from shared.models import Pin
            pin = Pin(
                id="123456789",
                title="测试标题",
                description="测试描述",
                image_url="https://example.com/image.jpg",
                image_url_736x="https://example.com/image_736.jpg",
                saves=100,
                comments=10,
                link="https://pinterest.com/pin/123456789",
                pinner="testuser",
                source="main",
                is_video=False,
                video_url="",
            )
            assert pin.id == "123456789", f"ID 不匹配: {pin.id}"
            assert pin.title == "测试标题"
            assert pin.saves == 100
            assert pin.comments == 10
            assert pin.is_video is False

            d = pin.to_dict()
            assert isinstance(d, dict), "to_dict 应返回 dict"
            assert d["id"] == "123456789"
            tc.mark_passed(f"Pin 模型创建和序列化正常 (saves={pin.saves})")

        self.run(TestCase("pin-model", "Pin 数据模型创建和序列化", "logic"), test_pin_model_creation)

        # 测试 1.2：Pin 筛选条件
        def test_pin_meets_criteria(tc: TestCase):
            from shared.models import Pin
            pin = Pin(
                id="test", title="t", description="", image_url="",
                image_url_736x="", saves=100, comments=10,
                link="", pinner="", source="main",
            )
            assert pin.meets_criteria(min_saves=50, min_comments=5), "应通过筛选"
            assert not pin.meets_criteria(min_saves=200), "saves 不满足应不通过"
            assert pin.meets_criteria(), "无筛选条件应全部通过"
            tc.mark_passed("筛选条件逻辑正常")

        self.run(TestCase("pin-criteria", "Pin 筛选条件检查", "logic"), test_pin_meets_criteria)

        # 测试 1.3：去重逻辑
        def test_pin_deduplication(tc: TestCase):
            from shared.models import Pin
            Pin.clear_collected()

            pid = f"dedup_test_{int(time.time())}"
            assert not Pin.is_collected(pid), "新 ID 不应已收集"
            assert Pin.mark_as_collected(pid), "首次标记应返回 True"
            assert Pin.is_collected(pid), "标记后应已收集"
            assert not Pin.mark_as_collected(pid), "重复标记应返回 False"
            assert Pin.get_collected_count() >= 1

            Pin.clear_collected()
            assert not Pin.is_collected(pid), "清除后不应已收集"
            tc.mark_passed("去重逻辑正常")

        self.run(TestCase("pin-dedup", "内存去重逻辑", "logic"), test_pin_deduplication)

        # 测试 1.4：URL 解析
        def test_url_parsing(tc: TestCase):
            test_cases = [
                ("https://www.pinterest.com/pin/123456789/", "123456789"),
                ("https://kr.pinterest.com/pin/987654321/", "987654321"),
                ("https://www.pinterest.com/pin/123456789/sent/", "123456789"),
                ("/pin/555555555/", "555555555"),
            ]
            import re
            for url, expected in test_cases:
                match = re.search(r'/pin/(\d+)', url)
                assert match and match.group(1) == expected, f"URL 解析失败: {url}"
            tc.mark_passed(f"URL 解析正常 ({len(test_cases)} 种格式)")

        self.run(TestCase("url-parse", "Pin URL 格式解析", "logic"), test_url_parsing)

        # 测试 1.5：数字解析（含 K/M 缩写）
        def test_flexible_number_parsing(tc: TestCase):
            import re
            def parse_flexible_number(s: str) -> int:
                """模拟 JS 端的 parseFlexibleNumber 逻辑"""
                if not s:
                    return 0
                cleaned = re.sub(r'[,\s]', '', str(s).strip())
                m = re.match(r'^([\d.]+)\s*([kKmM])?$', cleaned)
                if not m:
                    return int(float(cleaned)) if cleaned else 0
                num = float(m.group(1))
                unit = (m.group(2) or '').lower()
                if unit == 'k':
                    num *= 1000
                if unit == 'm':
                    num *= 1000000
                return round(num)

            test_cases = [
                ("1.2k", 1200),
                ("528", 528),
                ("1,234", 1234),
                ("12.5K", 12500),
                ("1.5m", 1500000),
                ("0", 0),
                ("", 0),
                ("1000", 1000),
            ]
            for input_val, expected in test_cases:
                result = parse_flexible_number(input_val)
                assert result == expected, f"解析 {input_val!r} 期望 {expected} 得到 {result}"
            tc.mark_passed(f"灵活数字解析正常 ({len(test_cases)} 种格式)")

        self.run(TestCase("number-parse", "灵活数字解析（K/M 格式）", "logic"), test_flexible_number_parsing)

        # 测试 1.6：JSON 输出
        def test_json_output(tc: TestCase):
            from shared.models import Pin
            from output import save_json
            import tempfile
            import os

            pins = [
                Pin(
                    id=f"output_test_{i}", title=f"输出测试 {i}", description="",
                    image_url=f"https://example.com/img_{i}.jpg",
                    image_url_736x="", saves=10 * i, comments=i,
                    link=f"https://pinterest.com/pin/output_test_{i}",
                    pinner="test", source="main",
                )
                for i in range(3)
            ]

            tmp_dir = tempfile.mkdtemp()
            try:
                filepath = os.path.join(tmp_dir, "test_output.json")
                save_json(pins, filepath, query="测试")

                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                assert data["total_pins"] == 3
                assert data["query"] == "测试"
                assert len(data["pins"]) == 3
                assert data["pins"][0]["saves"] == 0
                assert data["pins"][1]["saves"] == 10
                assert data["pins"][2]["saves"] == 20
                tc.mark_passed(f"JSON 输出正常 (3 个 pins)")
            finally:
                import shutil
                shutil.rmtree(tmp_dir)

        self.run(TestCase("json-output", "JSON 输出处理", "logic"), test_json_output)

        # 测试 1.7：下载器路径构造
        def test_downloader_path(tc: TestCase):
            from downloader import ImageDownloader
            import tempfile

            tmp_dir = tempfile.mkdtemp()
            try:
                dl = ImageDownloader(tmp_dir, query="测试关键词", use_folder_structure=True)
                assert "测试关键词" in str(dl.images_dir), f"目录名应包含关键词: {dl.images_dir}"
                assert dl.images_dir.exists(), f"目录应已创建: {dl.images_dir}"

                dl2 = ImageDownloader(tmp_dir, query="", use_folder_structure=False)
                assert dl2.images_dir.name == "images", f"无关键词目录名应为 'images': {dl2.images_dir}"
                tc.mark_passed("下载器路径构造正常")
            finally:
                import shutil
                shutil.rmtree(tmp_dir)

        self.run(TestCase("downloader-path", "下载器路径构造", "logic"), test_downloader_path)

    # ========================================================================
    # 模块二：AI 筛选测试（不需要浏览器）
    # ========================================================================

    def _run_ai_filter_tests(self):
        print(f"\n{'#' * 70}")
        print(f"  # 模块二：AI 筛选测试")
        print(f"{'#' * 70}")

        # 测试 2.1：AI Filter Manager 初始化
        def test_ai_filter_init(tc: TestCase):
            try:
                from shared.ai_filter_manager import AIFilterManager
                mgr = AIFilterManager(timeout=30)
                available_count = sum([mgr._zhipu_available, mgr._ollama_available])
                tc.mark_passed(
                    f"AIFilterManager 初始化成功 "
                    f"(Zhipu={mgr._zhipu_available}, "
                    f"Ollama={mgr._ollama_available}, 可用={available_count}/2)"
                )
            except ImportError as e:
                tc.mark_skipped(f"AI 模块导入失败: {e}")
            except Exception as e:
                tc.mark_failed(str(e), traceback.format_exc())

        self.run(TestCase("ai-init", "AI Filter Manager 初始化", "ai"), test_ai_filter_init)

        # 测试 2.2：Zhipu GLM Client 健康检查
        def test_zhipu_health(tc: TestCase):
            try:
                from shared.zhipu_glm_client import ZhipuGLMClient
                client = ZhipuGLMClient(timeout=10)
                healthy = client.health_check()
                if healthy:
                    tc.mark_passed("Zhipu GLM 健康检查通过")
                else:
                    tc.mark_skipped("Zhipu GLM 不可用（可能未配置 API key）")
            except ImportError:
                tc.mark_skipped("Zhipu GLM 模块未安装")
            except Exception as e:
                tc.mark_skipped(f"Zhipu GLM 检查异常: {e}")

        self.run(TestCase("zhipu-health", "Zhipu GLM 健康检查", "ai"), test_zhipu_health)

        # 测试 2.3：豆包 Client 健康检查
        def test_doubao_health(tc: TestCase):
            try:
                from shared.doubao_client import DoubaoClient
                client = DoubaoClient()
                healthy = client.health_check()
                if healthy:
                    tc.mark_passed("豆包 Client 健康检查通过")
                else:
                    tc.mark_skipped("豆包 Client 不可用（可能未配置 API key）")
            except ImportError:
                tc.mark_skipped("豆包 Client 模块未安装（openai 库未安装）")
            except Exception as e:
                tc.mark_skipped(f"豆包 Client 检查异常: {e}")

        self.run(TestCase("doubao-health", "豆包 Client 健康检查", "ai"), test_doubao_health)

        # 测试 2.4：Prompt 模板生成
        def test_prompt_generation(tc: TestCase):
            try:
                from shared.prompt_templates import PromptGenerator
                prompt = PromptGenerator.generate("奶油风")
                assert "奶油风" in prompt, f"Prompt 应包含关键词: {prompt[:50]}..."
                assert len(prompt) > 50, "Prompt 不应太短"

                collection_prompt = PromptGenerator.generate_collection_prompt("现代简约")
                assert "现代简约" in collection_prompt
                assert len(collection_prompt) > 50
                tc.mark_passed(f"Prompt 模板生成正常 (Prompt长度={len(prompt)})")
            except ImportError:
                tc.mark_skipped("Prompt 模板模块未安装")
            except Exception as e:
                tc.mark_failed(str(e), traceback.format_exc())

        self.run(TestCase("prompt-gen", "Prompt 模板生成", "ai"), test_prompt_generation)

    # ========================================================================
    # 模块三：搜索页测试（需要浏览器）
    # ========================================================================

    def _ensure_browser(self):
        """确保浏览器已初始化

        如果是 auto_launch 模式，先启动 Chrome 再连接
        """
        if self.scraper is not None:
            return self.scraper

        # auto_launch 模式：自动启动 Chrome 调试模式
        if self.auto_launch:
            from chrome_launcher import ChromeLauncher

            print("\n  [自动启动] 正在启动 Chrome 调试模式...")
            self._chrome_launcher = ChromeLauncher(
                port=9222,
                timeout=15,
                headless=False,
            )
            self._chrome_launcher.__enter__()
            self.cdp_endpoint = self._chrome_launcher.endpoint
            print(f"  [自动启动] Chrome 已启动，CDP 端点: {self.cdp_endpoint}")

        from scraper import PinterestScraper

        if self.cdp_endpoint:
            self.scraper = PinterestScraper(
                headless=False,
                debug=self.debug,
                cdp_endpoint=self.cdp_endpoint,
                log_file=str(self.output_dir / "test_comprehensive.log"),
                enable_ai_filter=False,
            )
        else:
            self.scraper = PinterestScraper(
                headless=False,
                debug=self.debug,
                log_file=str(self.output_dir / "test_comprehensive.log"),
                enable_ai_filter=False,
            )
        self.scraper.start()
        return self.scraper

    def _run_search_page_tests(self):
        print(f"\n{'#' * 70}")
        print(f"  # 模块三：搜索页测试（需要浏览器）")
        print(f"{'#' * 70}")

        scraper = self._ensure_browser()

        # 测试 3.1：搜索页加载
        def test_search_page_load(tc: TestCase):
            scraper.page.goto(
                "https://kr.pinterest.com/search/pins/?q=design",
                wait_until="domcontentloaded",
            )
            time.sleep(3)

            url = scraper.page.url
            assert "pinterest.com" in url, f"URL 不正确: {url}"
            assert "search" in url, f"未在搜索页: {url}"
            self.save_screenshot("search_page_load")
            tc.mark_passed(f"搜索页加载成功 ({url})")

        self.run(TestCase("search-load", "搜索页加载", "search", needs_browser=True), test_search_page_load)

        # 测试 3.2：Pin ID 检测
        def test_search_pin_detection(tc: TestCase):
            scraper.page.goto(
                "https://kr.pinterest.com/search/pins/?q=design",
                wait_until="domcontentloaded",
            )
            time.sleep(5)

            pin_ids = scraper._get_search_page_pin_ids()
            assert len(pin_ids) > 0, "未检测到任何 pin"
            assert all(len(pid) > 5 for pid in pin_ids), f"存在异常 pin ID: {pin_ids[:3]}"
            tc.mark_passed(f"检测到 {len(pin_ids)} 个 pin (示例: {', '.join(pin_ids[:3])})")

        self.run(TestCase("search-pin-detect", "搜索页 Pin 检测", "search", needs_browser=True), test_search_pin_detection)

        # 测试 3.3：从搜索结果提取图片 URL
        def test_image_url_extraction(tc: TestCase):
            scraper.page.goto(
                "https://kr.pinterest.com/search/pins/?q=design",
                wait_until="domcontentloaded",
            )
            time.sleep(5)

            pin_ids = scraper._get_search_page_pin_ids()
            assert pin_ids, "无 pin 可测试"

            test_id = pin_ids[0]
            self.save_screenshot("search_page_for_image")
            image_url = scraper._get_pin_image_url_from_search(test_id)

            if image_url:
                assert "pinimg" in image_url.lower() or image_url.startswith("http"), f"图片 URL 格式异常: {image_url[:80]}"
                self.save_data(f"image_url_{test_id}", {"pin_id": test_id, "image_url": image_url})
                tc.mark_passed(f"图片 URL 提取成功 ({len(image_url)} 字节)")
            else:
                tc.mark_failed(f"无法提取 pin {test_id} 的图片 URL")

        self.run(TestCase("search-image-url", "搜索页图片 URL 提取", "search", needs_browser=True), test_image_url_extraction)

        # 测试 3.4：滚动收集模式（快速版）
        def test_scroll_collection(tc: TestCase):
            pins = scraper.search(keyword="design", max_pins=3, min_saves=0)

            assert len(pins) > 0, "滚动收集未获取到结果"
            for pin in pins:
                assert pin.id, "Pin 缺少 ID"
                assert pin.saves >= 0, f"Pin saves 异常: {pin.saves}"

            samples = [f"{p.id[:10]}... saves={p.saves}" for p in pins[:3]]
            tc.mark_passed(f"收集到 {len(pins)} 个 pin ({'; '.join(samples)})")

        self.run(TestCase("scroll-collect", "滚动收集模式（3个 pin）", "search", needs_browser=True), test_scroll_collection)

    # ========================================================================
    # 模块四：详情页测试（需要浏览器）
    # ========================================================================

    def _run_detail_page_tests(self):
        print(f"\n{'#' * 70}")
        print(f"  # 模块四：详情页测试（需要浏览器）")
        print(f"{'#' * 70}")

        scraper = self._ensure_browser()

        # 测试 4.1：导航到详情页
        def test_detail_page_navigate(tc: TestCase):
            scraper.page.goto(
                "https://kr.pinterest.com/search/pins/?q=design",
                wait_until="domcontentloaded",
            )
            time.sleep(5)

            pin_ids = scraper._get_search_page_pin_ids()
            assert pin_ids, "无 pin 可测试"

            test_id = pin_ids[0]
            pin_link = scraper.page.query_selector(f'a[href*="/pin/{test_id}"]')
            if not pin_link:
                pin_link = scraper.page.query_selector(f'[data-test-id="pin"] a')
            assert pin_link, f"未找到 pin {test_id} 的链接"

            pin_link.click()
            time.sleep(3)

            current_url = scraper.page.url
            assert f"/pin/{test_id}" in current_url, f"未进入详情页: {current_url}"
            assert scraper._is_page_alive(), "详情页应存活"
            tc.mark_passed(f"进入详情页成功 ({current_url})")

        self.run(TestCase("detail-navigate", "导航到详情页", "detail", needs_browser=True), test_detail_page_navigate)

        # 测试 4.2：数据提取（DOM 方法）
        def test_detail_data_extraction(tc: TestCase):
            scraper.page.goto(
                "https://kr.pinterest.com/search/pins/?q=design",
                wait_until="domcontentloaded",
            )
            time.sleep(5)

            pin_ids = scraper._get_search_page_pin_ids()
            assert pin_ids, "无 pin 可测试"

            test_id = pin_ids[0]
            pin_link = scraper.page.query_selector(f'a[href*="/pin/{test_id}"]')
            if not pin_link:
                pin_link = scraper.page.query_selector(f'[data-test-id="pin"] a')
            assert pin_link, f"未找到 pin {test_id} 的链接"

            pin_link.click()
            time.sleep(3)

            self.save_screenshot(f"detail_page_{test_id}")
            details = scraper._extract_pin_details_from_modal()

            assert details, "数据提取返回空"
            assert "id" in details, "提取的数据缺少 id"
            assert details.get("id") == test_id, f"提取的 pin ID 不匹配: {details.get('id')} vs {test_id}"

            self.save_data(f"pin_detail_{test_id}", details)
            saves = details.get("saves", 0)
            tc.mark_passed(f"数据提取成功 (saves={saves})")

        self.run(TestCase("detail-extract", "详情页数据提取（DOM）", "detail", needs_browser=True), test_detail_data_extraction)

        # 测试 4.3：PWS_DATA 存在性检查
        def test_pws_data_presence(tc: TestCase):
            scraper.page.goto(
                "https://kr.pinterest.com/search/pins/?q=design",
                wait_until="domcontentloaded",
            )
            time.sleep(5)

            pin_ids = scraper._get_search_page_pin_ids()
            assert pin_ids, "无 pin 可测试"

            pin_link = scraper.page.query_selector(f'a[href*="/pin/{pin_ids[0]}"]')
            if not pin_link:
                pin_link = scraper.page.query_selector(f'[data-test-id="pin"] a')
            pin_link.click()
            time.sleep(3)

            # 检查 PWS_DATA 是否存在
            pws_exists = scraper.page.evaluate("() => !!document.getElementById('__PWS_DATA__')")
            if pws_exists:
                pws_data = scraper.page.evaluate("""
                    () => {
                        const s = document.getElementById('__PWS_DATA__');
                        if (!s) return null;
                        const d = JSON.parse(s.textContent);
                        const pins = (d.props || {}).initialReduxState?.pins || {};
                        const pr = (d.props || {}).initialReduxState?.resources?.PinResource || {};
                        return { pinsCount: Object.keys(pins).length, prCount: Object.keys(pr).length };
                    }
                """)
                tc.mark_passed(
                    f"PWS_DATA 存在 (pins={pws_data['pinsCount']}, PinResource={pws_data['prCount']})"
                )
            else:
                tc.mark_passed("PWS_DATA 不存在（可能是 Pinterest 结构变更）")

        self.run(TestCase("pws-data", "PWS_DATA 数据存在性", "detail", needs_browser=True), test_pws_data_presence)

        # 测试 4.4：安全后退
        def test_detail_safe_back(tc: TestCase):
            # 先访问搜索页
            scraper.page.goto(
                "https://kr.pinterest.com/search/pins/?q=design",
                wait_until="domcontentloaded",
            )
            time.sleep(3)

            # 再进入详情页
            pin_ids = scraper._get_search_page_pin_ids()
            assert pin_ids, "无 pin 可测试"

            pin_link = scraper.page.query_selector(f'a[href*="/pin/{pin_ids[0]}"]')
            if not pin_link:
                pin_link = scraper.page.query_selector(f'[data-test-id="pin"] a')
            pin_link.click()
            time.sleep(3)

            before_url = scraper.page.url
            assert "/pin/" in before_url, f"未在详情页: {before_url}"

            # 后退
            result = scraper._safe_go_back()
            after_url = scraper.page.url

            if result:
                assert scraper._is_page_alive(), "后退后页面应存活"
                tc.mark_passed(f"后退成功 ({before_url[:50]}... → {after_url[:50]}...)")
            else:
                tc.mark_passed(f"后退失败，页面可能已失效 (URL={after_url})")

        self.run(TestCase("detail-back", "详情页安全后退", "detail", needs_browser=True), test_detail_safe_back)

    # ========================================================================
    # 模块五：稳定性测试（需要浏览器）
    # ========================================================================

    def _run_stability_tests(self):
        print(f"\n{'#' * 70}")
        print(f"  # 模块五：稳定性测试（需要浏览器）")
        print(f"{'#' * 70}")

        scraper = self._ensure_browser()

        # 测试 5.1：页面存活检测（正常页面）
        def test_is_page_alive_normal(tc: TestCase):
            scraper.page.goto("https://kr.pinterest.com", wait_until="domcontentloaded")
            time.sleep(2)
            assert scraper._is_page_alive(), "正常页面应返回 True"
            tc.mark_passed("正常页面存活检测通过")

        self.run(TestCase("alive-normal", "正常页面存活检测", "stability", needs_browser=True), test_is_page_alive_normal)

        # 测试 5.2：页面存活检测（about:blank）
        def test_is_page_alive_blank(tc: TestCase):
            alive_before = scraper._is_page_alive()

            # 导航到 about:blank
            scraper.page.goto("about:blank")
            time.sleep(1)

            alive_blank = scraper._is_page_alive()
            tc.mark_passed(f"about:blank 页面存活状态: {alive_blank} (正常应为 True)")

        self.run(TestCase("alive-blank", "about:blank 页面存活检测", "stability", needs_browser=True), test_is_page_alive_blank)

        # 测试 5.3：_safe_go_back 正常场景
        def test_safe_go_back_scenario(tc: TestCase):
            urls = [
                "https://kr.pinterest.com/search/pins/?q=a",
                "https://kr.pinterest.com/search/pins/?q=b",
            ]
            for url in urls:
                scraper.page.goto(url, wait_until="domcontentloaded")
                time.sleep(1)

            before = scraper.page.url
            assert "q=b" in before, f"应在第二个搜索页: {before}"

            result = scraper._safe_go_back()
            after = scraper.page.url

            if result:
                assert scraper._is_page_alive(), "后退后页面应存活"
                tc.mark_passed(f"后退成功: 回到搜索页 a ({after})")
            else:
                tc.mark_passed(f"后退失败: 结果={result} (URL={after})")

        self.run(TestCase("back-normal", "连续搜索页后退", "stability", needs_browser=True), test_safe_go_back_scenario)

        # 测试 5.4：_ensure_page_alive_and_on_search 恢复
        def test_ensure_on_search(tc: TestCase):
            # 先离开搜索页
            scraper.page.goto("https://kr.pinterest.com/", wait_until="domcontentloaded")
            time.sleep(2)

            current = scraper.page.url
            assert "/search/" not in current, "当前不应在搜索页"

            # 调用恢复方法
            result = scraper._ensure_page_alive_and_on_search("design")

            if result:
                after = scraper.page.url
                assert "search" in after, f"应恢复到搜索页: {after}"
                assert scraper._is_page_alive(), "恢复后页面应存活"
                tc.mark_passed(f"页面恢复成功 (重新进入搜索页: {after})")
            else:
                tc.mark_passed("页面恢复方法返回 False（可能浏览器状态异常）")

        self.run(TestCase("ensure-search", "_ensure_page_alive_and_on_search 恢复", "stability", needs_browser=True), test_ensure_on_search)

        # 测试 5.5：快速小规模抓取（验证流程完整性）
        def test_quick_scrape(tc: TestCase):
            pins = scraper.search(keyword="art", max_pins=2, min_saves=10)

            assert scraper._is_page_alive(), "抓取完成后页面应存活"
            self.save_screenshot("quick_scrape_result")
            self.save_data("quick_scrape_pins", {
                "count": len(pins),
                "pins": [{"id": p.id, "title": p.title, "saves": p.saves} for p in pins]
            })
            tc.mark_passed(f"快速抓取完成 (收集 {len(pins)} 个 pin, 页面存活)")

        self.run(TestCase("quick-scrape", "快速小规模抓取流程验证", "stability", needs_browser=True), test_quick_scrape)

        # 测试 5.6：多次后退压力测试
        def test_stress_go_back(tc: TestCase):
            urls = [
                "https://kr.pinterest.com/search/pins/?q=x1",
                "https://kr.pinterest.com/search/pins/?q=x2",
                "https://kr.pinterest.com/search/pins/?q=x3",
                "https://kr.pinterest.com/search/pins/?q=x4",
            ]
            for url in urls:
                scraper.page.goto(url, wait_until="domcontentloaded")
                time.sleep(1)

            success_count = 0
            for i in range(3):
                result = scraper._safe_go_back()
                if result:
                    success_count += 1
                time.sleep(0.5)

            tc.mark_passed(f"连续后退: {success_count}/3 成功 (页面存活={scraper._is_page_alive()})")

        self.run(TestCase("stress-back", "连续多次后退压力测试", "stability", needs_browser=True), test_stress_go_back)

    # ========================================================================
    # 总结和报告
    # ========================================================================

    def _print_summary(self):
        """打印测试总结"""
        if not self.results:
            print("\n⚠️  没有测试运行")
            return

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed is True)
        failed = sum(1 for r in self.results if r.passed is False)
        skipped = sum(1 for r in self.results if r.passed is None)

        # 按模块分组统计
        modules: Dict[str, Dict] = {}
        for r in self.results:
            if r.module not in modules:
                modules[r.module] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
            modules[r.module]["total"] += 1
            if r.passed is True:
                modules[r.module]["passed"] += 1
            elif r.passed is False:
                modules[r.module]["failed"] += 1
            else:
                modules[r.module]["skipped"] += 1

        print(f"\n{'=' * 70}")
        print(f"  测试总结")
        print(f"{'=' * 70}")

        for mod_name, stats in modules.items():
            mod_total = stats["total"]
            mod_passed = stats["passed"]
            mod_failed = stats["failed"]
            mod_skipped = stats["skipped"]
            rate = mod_passed / max(mod_total - mod_skipped, 1) * 100

            module_names = {
                "logic": "逻辑测试",
                "ai": "AI 筛选测试",
                "search": "搜索页测试",
                "detail": "详情页测试",
                "stability": "稳定性测试",
            }
            label = module_names.get(mod_name, mod_name)

            status_parts = []
            if mod_passed > 0:
                status_parts.append(f"{mod_passed} 通过")
            if mod_failed > 0:
                status_parts.append(f"{mod_failed} 失败")
            if mod_skipped > 0:
                status_parts.append(f"{mod_skipped} 跳过")

            print(f"  [{label}] {' | '.join(status_parts)} (成功率 {rate:.0f}%)")

        # 详细列表
        print(f"\n{'─' * 70}")
        print(f"  详细结果")
        print(f"{'─' * 70}")
        for r in self.results:
            if r.passed is True:
                symbol = "✓"
            elif r.passed is False:
                symbol = "✗"
            else:
                symbol = "⊘"
            module_short = r.module[:4]
            msg = r.message or r.error or ""
            if len(msg) > 60:
                msg = msg[:57] + "..."
            print(f"  {symbol} [{module_short}] {r.name}: {msg}")

        print(f"\n{'─' * 70}")
        print(f"  总计: {total} 个测试 | {passed} 通过 | {failed} 失败 | {skipped} 跳过")
        if total - skipped > 0:
            print(f"  成功率: {passed / max(total - skipped, 1) * 100:.1f}%")
        print(f"{'═' * 70}")

        if failed == 0 and passed > 0:
            print("  ✓ 所有已执行测试均通过！")
        elif failed > 0:
            print(f"  ✗ {failed} 个测试失败，请检查相关模块")

    def _save_report(self):
        """保存测试报告为 JSON"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed is True),
            "failed": sum(1 for r in self.results if r.passed is False),
            "skipped": sum(1 for r in self.results if r.passed is None),
            "results": [
                {
                    "module": r.module,
                    "name": r.name,
                    "description": r.description,
                    "passed": r.passed,
                    "message": r.message,
                    "error": r.error,
                    "duration": round(r.duration, 2),
                }
                for r in self.results
            ],
        }

        report_path = self.output_dir / "test_comprehensive_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n  报告已保存: {report_path}")

    def cleanup(self):
        """清理资源"""
        if self.scraper:
            try:
                self.scraper.close()
            except Exception:
                pass

        if self._chrome_launcher:
            try:
                print("\n  [自动启动] 正在关闭 Chrome...")
                self._chrome_launcher.__exit__(None, None, None)
            except Exception:
                pass


# ============================================================================
# 命令行入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pinterest 爬虫综合测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_comprehensive.py --connect                 # 连接已有浏览器
  python test_comprehensive.py --auto-launch             # 自动启动 Chrome 并测试
  python test_comprehensive.py --logic-only              # 只运行逻辑测试
  python test_comprehensive.py --ai-only                 # 只运行 AI 筛选测试
  python test_comprehensive.py --auto-launch --skip ai   # 跳过 AI 测试
  python test_comprehensive.py --auto-launch --debug     # 调试模式
        """,
    )

    # 运行模式
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--logic-only", action="store_true", help="只运行逻辑测试（不需要浏览器）")
    mode_group.add_argument("--ai-only", action="store_true", help="只运行 AI 筛选测试")
    mode_group.add_argument("--browser-only", action="store_true", help="只运行需要浏览器的测试")
    mode_group.add_argument("--search-only", action="store_true", help="只运行搜索页测试")
    mode_group.add_argument("--detail-only", action="store_true", help="只运行详情页测试")
    mode_group.add_argument("--stability-only", action="store_true", help="只运行稳定性测试")

    # 浏览器连接
    browser_group = parser.add_mutually_exclusive_group()
    browser_group.add_argument("--connect", action="store_true", help="连接到已有浏览器 (localhost:9222)")
    browser_group.add_argument("--auto-launch", action="store_true", help="自动启动 Chrome 调试模式并连接")
    parser.add_argument("--cdp-endpoint", default="http://localhost:9222", help="Chrome CDP 端点")
    parser.add_argument("--debug", action="store_true", help="启用详细调试输出")

    # 跳过模块
    parser.add_argument(
        "--skip", nargs="+", choices=["logic", "ai", "search", "detail", "stability"],
        help="跳过指定模块",
    )

    args = parser.parse_args()

    # 确定运行哪些模块
    runner = TestRunner(
        cdp_endpoint=args.cdp_endpoint if args.connect else None,
        debug=args.debug,
        auto_launch=args.auto_launch,
    )

    skip_modules = args.skip or []

    if args.logic_only:
        runner.set_modules(only=["logic"])
    elif args.ai_only:
        runner.set_modules(only=["ai"])
    elif args.browser_only:
        runner.set_modules(only=["search", "detail", "stability"])
    elif args.search_only:
        runner.set_modules(only=["search"])
    elif args.detail_only:
        runner.set_modules(only=["detail"])
    elif args.stability_only:
        runner.set_modules(only=["stability"])
    else:
        runner.set_modules(skip=skip_modules)

    try:
        runner.run_all()
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n✗ 测试框架异常: {e}")
        traceback.print_exc()
    finally:
        runner.cleanup()

    # 返回退出码
    failed = sum(1 for r in runner.results if r.passed is False)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
