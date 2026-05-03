"""3vjia 户型图爬虫 - 纯模拟人工访问版（已移除API直接请求）

第三阶段：用宣传名在3vjia搜索户型图并下载

目标URL: https://www.3vjia.com/hx/search?cityCode=120100
城市代码: 120100 = 天津

架构变更（2026-04-27）：
- [已移除] 策略一：requests直接请求JSON API（太容易风控）
- [已移除] 策略二：Playwright拦截网络请求获取API数据
- [当前] 策略三：纯模拟人工访问（搜索→点击→提取）
- [新增] 支持滑块验证码自动处理（captcha-recognizer）

反爬策略：
1. 随机延迟（3-8秒）
2. 随机User-Agent
3. 模拟人工滚动和点击
4. 滑块验证码自动识别
"""

import os
import re
import sys
import time
import random
import json
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from playwright.sync_api import sync_playwright, Page, Locator


@dataclass
class FloorPlan:
    project_name: str
    plan_name: str
    room_type: str
    area: str
    image_url: str
    page_url: str
    source: str = "3vjia"

    def to_dict(self) -> dict:
        return asdict(self)


class CaptchaSolver:
    """验证码解决器 - 滑块验证码自动识别
    
    使用captcha-recognizer进行滑块缺口位置识别，配合Playwright模拟拖动
    安装依赖：pip install captcha-recognizer opencv-python numpy
    
    备用方案：人工模拟拖动（无需额外依赖）
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.slider_recognizer = None
        
        # 尝试导入captcha-recognizer
        try:
            from captcha_recognizer.slider import Slider
            self.slider_recognizer = Slider()
            if self.debug:
                print("[验证码] captcha-recognizer加载成功")
        except ImportError:
            print("[验证码] captcha-recognizer未安装，滑块识别功能受限。安装命令：pip install captcha-recognizer opencv-python numpy")
    
    def detect_slider_captcha(self, page: Page) -> bool:
        """检测是否存在滑块验证码"""
        slider_selectors = [
            ".geetest_slider_knob",
            ".geetest_slider_button",
            ".nc_iconfont.btn_slide",
            ".nc-lang-cnt",
            ".slider",
            "[class*='slider']",
            "[class*='captcha']",
            "[id*='captcha']",
        ]
        
        for selector in slider_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=1000):
                    if self.debug:
                        print(f"[验证码] 检测到滑块验证码: {selector}")
                    return True
            except:
                continue
        
        # 检查页面文本
        try:
            page_text = page.locator("body").inner_text(timeout=2000)
            captcha_keywords = ["拖动滑块", "滑动验证", "验证码", "captcha", "slider"]
            for keyword in captcha_keywords:
                if keyword in page_text:
                    if self.debug:
                        print(f"[验证码] 通过文本检测到验证码: {keyword}")
                    return True
        except:
            pass
        
        return False
    
    def solve_slider_captcha(self, page: Page, max_retries: int = 3) -> bool:
        """解决滑块验证码"""
        for attempt in range(max_retries):
            try:
                if self.debug:
                    print(f"[验证码] 第 {attempt + 1} 次尝试解决滑块验证码...")
                
                # 尝试使用captcha-recognizer识别缺口位置
                if self.slider_recognizer:
                    result = self._solve_with_captcha_recognizer(page)
                    if result:
                        return True
                
                # 如果captcha-recognizer失败，尝试人工模拟拖动
                result = self._simulate_human_drag(page)
                if result:
                    return True
                
                time.sleep(random.uniform(2, 4))
                
            except Exception as e:
                if self.debug:
                    print(f"[验证码] 解决滑块失败: {e}")
                time.sleep(random.uniform(1, 3))
        
        return False
    
    def _solve_with_captcha_recognizer(self, page: Page) -> bool:
        """使用captcha-recognizer识别滑块位置"""
        try:
            # 找到滑块和背景图
            slider = None
            bg_image = None
            
            slider_selectors = [
                ".geetest_slider_knob",
                ".geetest_slider_button",
                ".nc_iconfont.btn_slide",
            ]
            
            bg_selectors = [
                ".geetest_canvas_bg",
                ".geetest_bg",
                ".nc-container",
            ]
            
            # 找到滑块元素
            for selector in slider_selectors:
                try:
                    element = page.locator(selector).first
                    if element.is_visible(timeout=1000):
                        slider = element
                        break
                except:
                    continue
            
            if not slider:
                return False
            
            # 尝试找到背景图元素
            for selector in bg_selectors:
                try:
                    element = page.locator(selector).first
                    if element.is_visible(timeout=1000):
                        bg_image = element
                        break
                except:
                    continue
            
            # 获取滑块位置
            slider_box = slider.bounding_box()
            if not slider_box:
                return False
            
            # 截取背景图
            if bg_image:
                bg_screenshot = bg_image.screenshot()
            else:
                # 如果没有找到背景图元素，截取整个页面
                bg_screenshot = page.screenshot()
            
            # 使用captcha-recognizer识别缺口位置
            box, confidence = self.slider_recognizer.identify(source=bg_screenshot)
            
            if self.debug:
                print(f"[验证码] 识别结果: box={box}, confidence={confidence}")
            
            if box and confidence > 0.5:
                # 计算缺口位置
                # box格式: [x1, y1, x2, y2]
                gap_x = box[0]  # 缺口左上角x坐标
                
                # 计算拖动距离
                start_x = slider_box["x"] + slider_box["width"] / 2
                start_y = slider_box["y"] + slider_box["height"] / 2
                
                # 考虑偏移量
                offset = slider_box["x"]
                drag_distance = gap_x - offset
                
                if self.debug:
                    print(f"[验证码] 拖动距离: {drag_distance}")
                
                # 执行拖动
                slider.hover()
                page.mouse.down()
                
                # 生成随机轨迹
                steps = random.randint(20, 40)
                trajectory = self._generate_trajectory(start_x, start_x + drag_distance, steps)
                
                for x in trajectory:
                    y_offset = random.uniform(-2, 2)
                    page.mouse.move(x, start_y + y_offset)
                    time.sleep(random.uniform(0.01, 0.05))
                
                page.mouse.up()
                
                # 等待验证结果
                time.sleep(2)
                
                # 检查是否通过
                if not self.detect_slider_captcha(page):
                    print("[验证码] 滑块验证码已通过")
                    return True
            
            return False
            
        except Exception as e:
            if self.debug:
                print(f"[验证码] captcha-recognizer识别失败: {e}")
            return False
    
    def _simulate_human_drag(self, page: Page) -> bool:
        """模拟人工拖动滑块"""
        try:
            # 找到滑块元素
            slider = None
            slider_selectors = [
                ".geetest_slider_knob",
                ".geetest_slider_button",
                ".nc_iconfont.btn_slide",
                ".slider",
            ]
            
            for selector in slider_selectors:
                try:
                    element = page.locator(selector).first
                    if element.is_visible(timeout=1000):
                        slider = element
                        break
                except:
                    continue
            
            if not slider:
                return False
            
            # 获取滑块位置
            slider_box = slider.bounding_box()
            if not slider_box:
                return False
            
            start_x = slider_box["x"] + slider_box["width"] / 2
            start_y = slider_box["y"] + slider_box["height"] / 2
            
            # 随机目标位置
            viewport = page.viewport_size
            target_x = start_x + random.randint(200, 300)
            if viewport:
                target_x = min(target_x, viewport["width"] - 50)
            
            # 生成随机轨迹
            steps = random.randint(20, 40)
            trajectory = self._generate_trajectory(start_x, target_x, steps)
            
            # 执行拖动
            slider.hover()
            page.mouse.down()
            
            for x in trajectory:
                y_offset = random.uniform(-2, 2)
                page.mouse.move(x, start_y + y_offset)
                time.sleep(random.uniform(0.01, 0.05))
            
            page.mouse.up()
            
            # 等待验证结果
            time.sleep(2)
            
            # 检查是否通过
            if not self.detect_slider_captcha(page):
                print("[验证码] 滑块验证码已通过")
                return True
            
            return False
            
        except Exception as e:
            if self.debug:
                print(f"[验证码] 模拟拖动失败: {e}")
            return False
    
    def _generate_trajectory(self, start: float, end: float, steps: int) -> List[float]:
        """生成模拟人类拖动的轨迹点"""
        trajectory = []
        distance = end - start
        
        for i in range(steps):
            progress = i / steps
            eased = 0.5 - 0.5 * (3.14159 * (progress - 0.5))
            x = start + distance * (progress + random.uniform(-0.02, 0.02))
            trajectory.append(x)
        
        trajectory.append(end)
        return trajectory


class SanvjiaScraper:
    """3vjia户型图爬虫 - 纯模拟人工访问版"""
    
    CITY_CODE = "120100"
    BASE_HOST = "https://www.3vjia.com"
    SEARCH_URL = "https://www.3vjia.com/hx/search"
    
    def __init__(self, headless: bool = True, debug: bool = False,
                 cdp_endpoint: str = None, output_dir: str = "./output",
                 page=None):
        self.headless = headless
        self.debug = debug
        self.cdp_endpoint = cdp_endpoint
        self.output_dir = Path(output_dir)
        self._external_page = page
        self.browser = None
        self.context = None
        self.page = page
        self._playwright = None
        self._own_browser = False
        
        # 验证码解决器
        self.captcha_solver = CaptchaSolver(debug=debug)
    
    def start(self):
        if self._external_page and not self.page:
            self.page = self._external_page
        if self.page:
            return
        
        self._playwright = sync_playwright().start()
        if self.cdp_endpoint:
            self.browser = self._playwright.chromium.connect_over_cdp(self.cdp_endpoint)
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        else:
            self.browser = self._playwright.chromium.launch(headless=self.headless)
            self.context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=self._random_ua()
            )
            self.page = self.context.new_page()
        
        self._own_browser = not self.cdp_endpoint
        
        # 反检测脚本
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)
    
    def close(self):
        if self._own_browser and self.browser:
            self.browser.close()
        if self._playwright:
            self._playwright.stop()
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    @staticmethod
    def _random_ua() -> str:
        versions = [
            "Chrome/120.0.0.0 Safari/537.36",
            "Chrome/121.0.0.0 Safari/537.36",
            "Chrome/122.0.0.0 Safari/537.36",
            "Chrome/123.0.0.0 Safari/537.36",
            "Chrome/124.0.0.0 Safari/537.36",
        ]
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            + random.choice(versions)
        )
    
    def search_floor_plans(self, project_names: List[str],
                           max_plans_per_project: int = 20) -> Dict[str, List[FloorPlan]]:
        """批量搜索户型图"""
        results = {}
        total = len(project_names)
        
        for i, name in enumerate(project_names):
            print(f"[3vjia] [{i + 1}/{total}] 正在搜索: {name}")
            
            try:
                plans = self._search_single_project(name, max_plans_per_project)
                if plans:
                    plans = self._filter_logo_plans(plans)
                    plans = self._deduplicate_plans(plans)
                if plans:
                    results[name] = plans
                    print(f"  ✓ 找到 {len(plans)} 个户型")
                else:
                    print(f"  ✗ 未找到户型")
            except Exception as e:
                print(f"  ✗ 搜索失败: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()
            
            if i < total - 1:
                delay = random.uniform(3, 8)
                print(f"  [延迟] 等待 {delay:.1f} 秒...")
                time.sleep(delay)
        
        return results
    
    def _filter_logo_plans(self, plans: List[FloorPlan]) -> List[FloorPlan]:
        """过滤logo和广告图片
        
        过滤规则：
        - plan_name 包含"3D云设计"、"下载"、"软件"等广告关键词
        - 图片URL 包含 logo/广告相关路径
        - 图片尺寸过小（logo通常较小）
        """
        logo_keywords = [
            '3D云设计', '云设计软件', '下载', '软件下载', 'APP',
            'logo', 'banner', '广告', '二维码', '关注', '扫码',
            '立即', '免费', '领取', '注册', '登录',
        ]
        
        logo_url_patterns = [
            '/logo/', '/banner/', '/icon/', '/ad/', '/qrcode/',
            'logo.png', 'banner.png', 'icon.png',
        ]
        
        filtered = []
        for plan in plans:
            name = plan.plan_name or ''
            url = plan.image_url or ''
            
            is_logo = False
            for kw in logo_keywords:
                if kw in name:
                    is_logo = True
                    if self.debug:
                        print(f"  [过滤] 排除logo/广告: '{name}' (关键词: {kw})")
                    break
            
            if not is_logo:
                for pattern in logo_url_patterns:
                    if pattern in url.lower():
                        is_logo = True
                        if self.debug:
                            print(f"  [过滤] 排除logo/广告: URL含'{pattern}'")
                        break
            
            if not is_logo and url.endswith('.png') and not plan.room_type:
                is_logo = True
                if self.debug:
                    print(f"  [过滤] 排除疑似logo: PNG格式且无户型信息 '{name}'")
            
            if not is_logo:
                filtered.append(plan)
        
        if len(filtered) < len(plans):
            print(f"  [过滤] 排除 {len(plans) - len(filtered)} 个logo/广告图片")
        
        return filtered
    
    def _deduplicate_plans(self, plans: List[FloorPlan]) -> List[FloorPlan]:
        """户型图去重
        
        去重规则：
        - 相同 image_url 只保留第一个
        - 相同面积+相同房型只保留第一个（可能是同一户型的不同展示）
        """
        seen_urls = set()
        seen_area_room = set()
        deduped = []
        
        for plan in plans:
            url = plan.image_url or ''
            
            if url and url in seen_urls:
                if self.debug:
                    print(f"  [去重] 跳过重复URL: {plan.plan_name} ({plan.area})")
                continue
            
            if url:
                seen_urls.add(url)
            
            area_room_key = f"{plan.area}_{plan.room_type}"
            if area_room_key in seen_area_room and area_room_key != "_":
                if self.debug:
                    print(f"  [去重] 跳过重复面积+房型: {plan.plan_name} ({plan.area} {plan.room_type})")
                continue
            
            seen_area_room.add(area_room_key)
            deduped.append(plan)
        
        if len(deduped) < len(plans):
            print(f"  [去重] 移除 {len(plans) - len(deduped)} 个重复户型")
        
        return deduped
    
    def _search_single_project(self, project_name: str, max_plans: int) -> List[FloorPlan]:
        """搜索单个小区的户型图
        
        搜索策略：
        1. 先用原始关键词精准搜索
        2. 如果精准匹配到结果，直接爬取
        3. 如果没有精准匹配，查找"你是不是想找"推荐
        4. 点击第一个推荐重新搜索，精准匹配后爬取
        """
        plans = []
        
        try:
            # 第一步：用原始关键词搜索
            search_url = f"{self.SEARCH_URL}?cityCode={self.CITY_CODE}&keyword={urllib.parse.quote(project_name)}"
            print(f"  [访问] {search_url}")
            
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(random.uniform(2, 4))
            
            if self.captcha_solver.detect_slider_captcha(self.page):
                print("  [验证码] 检测到滑块验证码，尝试自动解决...")
                if not self.captcha_solver.solve_slider_captcha(self.page):
                    print("  [验证码] 自动解决失败，等待手动处理...")
                    time.sleep(10)
            
            self.page.wait_for_load_state("networkidle", timeout=10000)
            time.sleep(random.uniform(2, 3))
            
            if self.debug:
                self._save_debug_html(project_name, "step1_direct_search")
            
            # 第二步：尝试精准匹配提取
            plans = self._extract_floor_plans(project_name, max_plans)
            
            if plans:
                matched_name = plans[0].project_name
                if self._is_name_match(project_name, matched_name):
                    print(f"  ✓ 精准匹配成功: '{project_name}' → '{matched_name}'")
                    return plans
                else:
                    print(f"  ~ 模糊匹配结果: '{project_name}' ≠ '{matched_name}'，尝试精准筛选")
                    exact_plans = [p for p in plans if self._is_name_match(project_name, p.project_name)]
                    if exact_plans:
                        print(f"  ✓ 从模糊结果中筛选到 {len(exact_plans)} 个精准匹配户型")
                        return exact_plans
            
            # 第三步：没有精准匹配，查找"你是不是想找"推荐
            print(f"  → 无精准匹配，尝试查找相似推荐...")
            suggestion = self._find_suggestion(project_name)
            
            if suggestion:
                print(f"  → 找到相似推荐: '{suggestion}'，重新搜索...")
                time.sleep(random.uniform(1, 2))
                
                suggestion_url = f"{self.SEARCH_URL}?cityCode={self.CITY_CODE}&keyword={urllib.parse.quote(suggestion)}"
                print(f"  [访问] {suggestion_url}")
                
                self.page.goto(suggestion_url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(random.uniform(2, 4))
                
                if self.captcha_solver.detect_slider_captcha(self.page):
                    print("  [验证码] 检测到滑块验证码，尝试自动解决...")
                    if not self.captcha_solver.solve_slider_captcha(self.page):
                        print("  [验证码] 自动解决失败，等待手动处理...")
                        time.sleep(10)
                
                self.page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(random.uniform(2, 3))
                
                if self.debug:
                    self._save_debug_html(project_name, "step3_suggestion_search")
                
                plans = self._extract_floor_plans(suggestion, max_plans)
                
                if plans:
                    print(f"  ✓ 通过相似推荐找到 {len(plans)} 个户型")
                    for p in plans:
                        p.project_name = project_name
                    return plans
            
            # 第四步：尝试去掉特殊字符后重新搜索
            clean_name = re.sub(r'[·\-—\s]', '', project_name)
            if clean_name != project_name:
                print(f"  → 尝试简化名称搜索: '{clean_name}'")
                clean_url = f"{self.SEARCH_URL}?cityCode={self.CITY_CODE}&keyword={urllib.parse.quote(clean_name)}"
                print(f"  [访问] {clean_url}")
                
                self.page.goto(clean_url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(random.uniform(2, 4))
                
                if self.captcha_solver.detect_slider_captcha(self.page):
                    print("  [验证码] 检测到滑块验证码，尝试自动解决...")
                    if not self.captcha_solver.solve_slider_captcha(self.page):
                        print("  [验证码] 自动解决失败，等待手动处理...")
                        time.sleep(10)
                
                self.page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(random.uniform(2, 3))
                
                plans = self._extract_floor_plans(clean_name, max_plans)
                
                if plans:
                    matched_name = plans[0].project_name
                    if self._is_name_match(clean_name, matched_name):
                        print(f"  ✓ 简化名称精准匹配: '{clean_name}' → '{matched_name}'")
                        for p in plans:
                            p.project_name = project_name
                        return plans
                    else:
                        exact_plans = [p for p in plans if self._is_name_match(clean_name, p.project_name)]
                        if exact_plans:
                            print(f"  ✓ 从简化搜索中筛选到 {len(exact_plans)} 个精准匹配户型")
                            for p in exact_plans:
                                p.project_name = project_name
                            return exact_plans
            
            print(f"  ✗ 所有搜索策略均未找到户型")
            
        except Exception as e:
            print(f"  [错误] 搜索过程中出现异常: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
        
        return plans
    
    def _is_name_match(self, query_name: str, result_name: str) -> bool:
        """判断查询名与结果名是否匹配
        
        匹配规则：
        - 去除特殊字符（·、-、—、空格）后比较
        - 查询名是结果名的子串也算匹配（如"格调初晴"匹配"格调初晴墅"）
        - 结果名是查询名的子串也算匹配
        """
        def normalize(name):
            return re.sub(r'[·\-—\s\u00b7]', '', name).lower()
        
        q = normalize(query_name)
        r = normalize(result_name)
        
        if q == r:
            return True
        if q in r or r in q:
            return True
        
        q_core = re.sub(r'(墅|园|苑|府|院|城|里|居|庭|台|阁|轩|筑|湾|郡|都|镇|庄|村)$', '', q)
        r_core = re.sub(r'(墅|园|苑|府|院|城|里|居|庭|台|阁|轩|筑|湾|郡|都|镇|庄|村)$', '', r)
        if q_core and r_core and (q_core in r_core or r_core in q_core):
            return True
        
        return False
    
    def _find_suggestion(self, project_name: str) -> Optional[str]:
        """查找搜索页面的"你是不是想找"推荐
        
        Returns:
            推荐的项目名称，如果没有则返回None
        """
        try:
            suggestion_selectors = [
                "[class*='suggest'] a",
                "[class*='recommend'] a",
                "[class*='guess'] a",
                "[class*='did-you-mean'] a",
                "[class*='related'] a",
                "[class*='similar'] a",
                "[class*='search-tip'] a",
                "[class*='tip'] a",
                "[class*='fuzzy'] a",
                "[class*='correction'] a",
            ]
            
            for selector in suggestion_selectors:
                try:
                    elements = self.page.locator(selector).all()
                    for elem in elements:
                        text = elem.inner_text(timeout=500).strip()
                        if text and len(text) > 1 and len(text) < 30:
                            print(f"  [推荐] 找到相似推荐: '{text}' (选择器: {selector})")
                            return text
                except:
                    continue
            
            suggestion = self.page.evaluate("""(queryName) => {
                const allElements = document.querySelectorAll('a, span, div, p, li');
                const keywords = ['你想找', '是不是想', '为您推荐', '相似', '相关', '推荐', '搜索建议', '您是不是要找'];
                
                for (const el of allElements) {
                    const text = el.textContent || '';
                    for (const kw of keywords) {
                        if (text.includes(kw)) {
                            const links = el.querySelectorAll('a, span[class*="name"], span[class*="title"]');
                            for (const link of links) {
                                const linkText = link.textContent.trim();
                                if (linkText && linkText.length > 1 && linkText.length < 30 && linkText !== kw) {
                                    return linkText;
                                }
                            }
                            const parent = el.parentElement;
                            if (parent) {
                                const siblingLinks = parent.querySelectorAll('a');
                                for (const sl of siblingLinks) {
                                    const slText = sl.textContent.trim();
                                    if (slText && slText.length > 1 && slText.length < 30 && slText !== text.trim()) {
                                        return slText;
                                    }
                                }
                            }
                        }
                    }
                }
                
                const searchInput = document.querySelector('input[type="text"], input[type="search"], input[placeholder*="搜索"], input[placeholder*="输入"]');
                if (searchInput) {
                    const dropdown = document.querySelector('.search-suggest, .autocomplete, .suggestions, [class*="dropdown"], [class*="suggest"]');
                    if (dropdown) {
                        const firstItem = dropdown.querySelector('li, a, div');
                        if (firstItem) {
                            const itemText = firstItem.textContent.trim();
                            if (itemText && itemText.length > 1 && itemText.length < 30) {
                                return itemText;
                            }
                        }
                    }
                }
                
                return null;
            }""", project_name)
            
            if suggestion:
                print(f"  [推荐] JS扫描找到相似推荐: '{suggestion}'")
                return suggestion
            
            if self.debug:
                print(f"  [DEBUG] 未找到'你是不是想找'推荐")
            
        except Exception as e:
            if self.debug:
                print(f"  [DEBUG] 查找推荐失败: {e}")
        
        return None
    
    def _save_debug_html(self, project_name: str, step: str):
        if not self.debug:
            return
        try:
            debug_dir = Path("logs/debug/3vjia")
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', project_name)
            step_dir = debug_dir / safe_name
            step_dir.mkdir(parents=True, exist_ok=True)
            
            with open(step_dir / f"{step}.html", "w", encoding="utf-8") as f:
                f.write(self.page.content())
            
            try:
                self.page.screenshot(path=str(step_dir / f"{step}.png"), full_page=True, timeout=5000)
            except:
                pass
            
            print(f"  [DEBUG] 调试文件已保存: {step_dir / step}")
        except:
            pass
    
    def _extract_floor_plans(self, project_name: str, max_plans: int) -> List[FloorPlan]:
        """从页面提取户型数据
        
        三维家搜索结果页结构：
        - 搜索结果列表中的每个户型条目包含：项目名、户型信息、面积、图片
        - 页面可能使用Vue/React动态渲染，class名可能包含hash
        """
        plans = []
        
        try:
            plans = self._extract_via_js(project_name, max_plans)
            
            if plans:
                return plans
            
            card_selectors = [
                "[class*='room-item']",
                "[class*='floor-plan']",
                "[class*='huxing']",
                ".room-item",
                ".floor-item",
                "[class*='plan-card']",
                "[class*='plan-item']",
                "[class*='search-result'] [class*='item']",
                "[class*='result-list'] [class*='item']",
                "[class*='card']",
            ]
            
            cards = []
            for selector in card_selectors:
                try:
                    elements = self.page.locator(selector).all()
                    if elements and len(elements) > 0:
                        cards = elements
                        if self.debug:
                            print(f"  [DEBUG] 使用选择器 '{selector}' 找到 {len(cards)} 个户型卡片")
                        break
                except:
                    continue
            
            if not cards:
                cards = self._find_cards_by_structure(project_name)
            
            for i, card in enumerate(cards[:max_plans]):
                try:
                    plan = self._parse_floor_plan_card(card, project_name)
                    if plan:
                        plans.append(plan)
                except Exception as e:
                    if self.debug:
                        print(f"  [DEBUG] 解析第 {i+1} 个户型卡片失败: {e}")
                    continue
            
            if self.debug:
                print(f"  [DEBUG] 成功提取 {len(plans)} 个户型")
                
        except Exception as e:
            print(f"  [错误] 提取户型数据失败: {e}")
        
        return plans
    
    def _extract_via_js(self, project_name: str, max_plans: int) -> List[FloorPlan]:
        """通过JavaScript直接从页面提取户型数据
        
        三维家页面是SPA，数据可能直接在DOM中但class名含hash
        使用JS扫描所有包含户型信息的元素
        """
        plans = []
        
        try:
            raw_plans = self.page.evaluate("""(maxPlans) => {
                const results = [];
                
                // 策略1：查找所有包含"室"和"厅"的文本块（户型特征）
                const allElements = document.querySelectorAll('div, li, article, section');
                for (const el of allElements) {
                    const text = el.textContent || '';
                    const hasRoomInfo = /\\d+室\\d*厅|\\d+室\\d*卫/.test(text);
                    const hasArea = /\\d+(?:\\.\\d+)?\\s*(?:m²|㎡|平米)/.test(text);
                    
                    if (hasRoomInfo && hasArea) {
                        const img = el.querySelector('img');
                        const link = el.querySelector('a');
                        
                        let planName = '';
                        const nameEl = el.querySelector('h3, h4, h5, [class*="name"], [class*="title"], [class*="model"]');
                        if (nameEl) {
                            planName = nameEl.textContent.trim();
                        }
                        
                        let roomType = '';
                        const roomMatch = text.match(/(\\d+室\\d*厅\\d*卫\\d*厨)/);
                        if (roomMatch) roomType = roomMatch[1];
                        
                        let area = '';
                        const areaMatch = text.match(/(\\d+(?:\\.\\d+)?)\\s*(?:m²|㎡|平米|平方米)/);
                        if (areaMatch) area = areaMatch[1] + 'm²';
                        
                        let projectName = '';
                        const projNameEl = el.querySelector('[class*="project"], [class*="community"], [class*="building"]');
                        if (projNameEl) {
                            projectName = projNameEl.textContent.trim();
                        }
                        
                        let imageUrl = '';
                        if (img) {
                            imageUrl = img.src || img.dataset.src || '';
                        }
                        
                        let pageUrl = '';
                        if (link) {
                            pageUrl = link.href || '';
                        }
                        
                        if (hasRoomInfo) {
                            results.push({
                                project_name: projectName,
                                plan_name: planName || roomType || '未知户型',
                                room_type: roomType,
                                area: area,
                                image_url: imageUrl,
                                page_url: pageUrl,
                                text_preview: text.substring(0, 200)
                            });
                        }
                        
                        if (results.length >= maxPlans) break;
                    }
                }
                
                return results;
            }""", max_plans)
            
            if raw_plans:
                for rp in raw_plans:
                    plan = FloorPlan(
                        project_name=rp.get('project_name') or project_name,
                        plan_name=rp.get('plan_name', '未知户型'),
                        room_type=rp.get('room_type', ''),
                        area=rp.get('area', ''),
                        image_url=rp.get('image_url', ''),
                        page_url=rp.get('page_url', ''),
                        source="3vjia"
                    )
                    if plan.room_type or plan.image_url:
                        plans.append(plan)
                
                if self.debug:
                    print(f"  [DEBUG] JS提取到 {len(plans)} 个户型")
                    if raw_plans:
                        print(f"  [DEBUG] 首条预览: {raw_plans[0].get('text_preview', '')[:100]}")
        
        except Exception as e:
            if self.debug:
                print(f"  [DEBUG] JS提取失败: {e}")
        
        return plans
    
    def _find_cards_by_structure(self, project_name: str) -> list:
        """通过页面结构特征查找户型卡片
        
        当CSS选择器无法匹配时，使用结构化方法查找
        """
        try:
            card_locators = self.page.evaluate("""() => {
                const candidates = [];
                
                // 查找所有包含图片和文本的块级元素
                const blocks = document.querySelectorAll('div, li, article');
                for (const block of blocks) {
                    const imgs = block.querySelectorAll('img');
                    const text = block.textContent || '';
                    const hasRoom = /\\d+室/.test(text);
                    const hasImg = imgs.length > 0;
                    
                    // 排除过大的容器（通常是整页容器）
                    const childCount = block.children.length;
                    if (hasRoom && hasImg && childCount < 20) {
                        const rect = block.getBoundingClientRect();
                        if (rect.width > 100 && rect.height > 50 && rect.height < 800) {
                            candidates.push({
                                index: Array.from(block.parentNode.children).indexOf(block),
                                text: text.substring(0, 100),
                                imgCount: imgs.length,
                                width: rect.width,
                                height: rect.height
                            });
                        }
                    }
                }
                
                return candidates;
            }""")
            
            if self.debug and card_locators:
                print(f"  [DEBUG] 结构化查找发现 {len(card_locators)} 个候选卡片")
                for c in card_locators[:3]:
                    print(f"    - 文本: {c['text'][:50]}... 图片: {c['imgCount']} 尺寸: {c['width']}x{c['height']}")
            
        except Exception as e:
            if self.debug:
                print(f"  [DEBUG] 结构化查找失败: {e}")
        
        return []
    
    def _parse_floor_plan_card(self, card, project_name: str) -> Optional[FloorPlan]:
        """解析单个户型卡片"""
        try:
            # 提取户型名称
            name_selectors = [
                "[class*='model-name']",
                "[class*='room-name']",
                ".model-name",
                ".room-name",
                "h3", "h4", "h5",
            ]
            plan_name = ""
            for selector in name_selectors:
                try:
                    text = card.locator(selector).first.inner_text(timeout=500)
                    if text:
                        plan_name = text.strip()
                        break
                except:
                    continue
            
            # 提取房型
            room_type = ""
            room_type_pattern = r'(\d+)\s*室\s*(\d+)\s*厅'
            if plan_name:
                match = re.search(room_type_pattern, plan_name)
                if match:
                    room_type = f"{match.group(1)}室{match.group(2)}厅"
            
            # 提取面积
            area_selectors = [
                "[class*='area']",
                "[class*='size']",
            ]
            area = ""
            for selector in area_selectors:
                try:
                    text = card.locator(selector).first.inner_text(timeout=500)
                    if text:
                        area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:m²|平米|平方米)', text)
                        if area_match:
                            area = f"{area_match.group(1)}m²"
                            break
                except:
                    continue
            
            # 提取图片URL
            img_selectors = [
                "img",
                "[class*='img'] img",
            ]
            image_url = ""
            for selector in img_selectors:
                try:
                    img = card.locator(selector).first
                    src = img.get_attribute("src")
                    if src:
                        image_url = src
                        break
                except:
                    continue
            
            # 提取详情页URL
            page_url = ""
            try:
                link = card.locator("a").first
                href = link.get_attribute("href")
                if href:
                    page_url = href if href.startswith("http") else f"{self.BASE_HOST}{href}"
            except:
                pass
            
            if not image_url:
                return None
            
            return FloorPlan(
                project_name=project_name,
                plan_name=plan_name or "未知户型",
                room_type=room_type,
                area=area,
                image_url=image_url,
                page_url=page_url,
                source="3vjia"
            )
            
        except Exception as e:
            if self.debug:
                print(f"  [DEBUG] 解析户型卡片失败: {e}")
            return None
    
    def download_floor_plans(self, results: Dict[str, List[FloorPlan]]) -> Dict[str, int]:
        """下载户型图片"""
        download_counts = {}
        
        for project_name, plans in results.items():
            if not plans:
                continue
            
            safe_name = re.sub(r"[^\w\u4e00-\u9fff]", "_", project_name)
            project_dir = self.output_dir / safe_name
            project_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"[3vjia] 下载 {project_name} 的户型图 ({len(plans)} 张)...")
            
            downloaded = 0
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_map = {}
                for i, plan in enumerate(plans):
                    if not plan.image_url:
                        continue
                    future = executor.submit(
                        self._download_single, plan, i, safe_name, project_dir
                    )
                    future_map[future] = plan
                
                for future in as_completed(future_map):
                    plan = future_map[future]
                    try:
                        ok = future.result()
                        if ok:
                            downloaded += 1
                    except Exception as e:
                        print(f"    ✗ 下载失败 {plan.plan_name}: {e}")
            
            download_counts[project_name] = downloaded
            print(f"  完成: {downloaded}/{len(plans)} 张")
        
        return download_counts
    
    def _download_single(self, plan: FloorPlan, index: int, 
                         safe_name: str, project_dir: Path) -> bool:
        """下载单个户型图片"""
        try:
            ext = Path(plan.image_url).suffix or ".jpg"
            area_part = plan.area.replace("m²", "平米") if plan.area else ""
            plan_part = plan.plan_name if plan.plan_name and plan.plan_name != "未知户型" else f"户型{index + 1}"
            filename = f"{safe_name}_{plan_part}_{area_part}{ext}"
            filename = re.sub(r"[\\/:*?\"<>|]", "_", filename)
            filename = re.sub(r"_+", "_", filename).strip("_")
            filepath = project_dir / filename
            
            headers = {
                "User-Agent": self._random_ua(),
                "Referer": "https://www.3vjia.com/",
            }
            resp = requests.get(plan.image_url, headers=headers, timeout=30)
            resp.raise_for_status()
            
            with open(filepath, "wb") as f:
                f.write(resp.content)
            
            print(f"    ✓ {filename}")
            return True
            
        except Exception as e:
            if self.debug:
                print(f"    ✗ 下载失败: {e}")
            return False
    
    def save_results(self, results: Dict[str, List[FloorPlan]], output_path: str):
        """保存结果到JSON文件"""
        data = {
            "source": "3vjia",
            "city_code": self.CITY_CODE,
            "total_projects": len(results),
            "projects": {
                name: [p.to_dict() for p in plans]
                for name, plans in results.items()
            },
        }
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[3vjia] 结果已保存: {output_path}")


def main():
    """独立测试入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="3vjia户型图爬虫（纯模拟人工版）")
    parser.add_argument("--input", required=True, help="房天下映射JSON输入文件")
    parser.add_argument("--output-dir", default="output/3vjia", help="图片输出目录")
    parser.add_argument("--output-json", default="output/3vjia_results.json", help="JSON输出路径")
    parser.add_argument("--max-plans", type=int, default=20, help="每小区最大户型数")
    parser.add_argument("--connect", action="store_true")
    parser.add_argument("--cdp-endpoint", default="http://localhost:9222")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    promo_names = [
        m["promo_name"] for m in data.get("mappings", [])
        if m.get("promo_name")
    ]
    print(f"[3vjia] 读取到 {len(promo_names)} 个小区名称")
    
    with SanvjiaScraper(
        headless=not args.debug,
        debug=args.debug,
        cdp_endpoint=args.cdp_endpoint if args.connect else None,
        output_dir=args.output_dir,
    ) as scraper:
        results = scraper.search_floor_plans(promo_names, max_plans_per_project=args.max_plans)
        scraper.save_results(results, args.output_json)
        download_counts = scraper.download_floor_plans(results)
        
        total_plans = sum(len(v) for v in results.values())
        total_downloaded = sum(download_counts.values())
        print(f"\n=== 汇总 ===")
        print(f"小区数: {len(results)}")
        print(f"户型图总数: {total_plans}")
        print(f"下载成功: {total_downloaded}")


if __name__ == "__main__":
    main()
