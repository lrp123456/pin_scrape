"""酷家乐户型图爬虫 - 纯模拟人工访问版

第四阶段：用宣传名在酷家乐搜索户型图并下载

目标URL: https://www.kujiale.com/huxing/search
特点：
- 纯模拟人工访问，不使用API直接请求
- 支持滑块验证码自动处理（使用captcha-recognizer）
- 支持多城市切换（默认天津）

反爬策略：
1. 随机延迟（3-8秒）
2. 随机User-Agent
3. 模拟人工滚动和点击
4. 滑块验证码自动识别（使用captcha-recognizer辅助）
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
    """户型图数据类"""
    project_name: str          # 小区名称
    plan_name: str             # 户型名称（如：A户型、三室两厅）
    room_type: str             # 房型（如：3室2厅）
    area: str                  # 面积（如：120m²）
    image_url: str             # 图片URL
    page_url: str              # 详情页URL
    source: str = "kujiale"    # 数据来源

    def to_dict(self) -> dict:
        return asdict(self)


class CaptchaSolver:
    """验证码解决器 - 滑块验证码自动识别
    
    使用captcha-recognizer进行滑块缺口位置识别，配合Playwright模拟拖动
    安装依赖：pip install captcha-recognizer opencv-python numpy
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.slider_recognizer = None
        try:
            from captcha_recognizer.slider import Slider
            self.slider_recognizer = Slider()
            if self.debug:
                print("[验证码] captcha-recognizer加载成功")
        except ImportError:
            print("[验证码] captcha-recognizer未安装，滑块识别功能不可用。安装命令：pip install captcha-recognizer opencv-python numpy")
    
    def detect_slider_captcha(self, page: Page) -> bool:
        """检测是否存在滑块验证码
        
        Returns:
            True - 存在滑块验证码
            False - 不存在
        """
        # 常见滑块验证码选择器
        slider_selectors = [
            # 极验滑块
            ".geetest_slider_knob",
            ".geetest_slider_button",
            # 阿里云滑块
            ".nc_iconfont.btn_slide",
            ".nc-lang-cnt",
            # 通用滑块
            ".slider",
            "[class*='slider']",
            "[class*='captcha']",
            "[id*='captcha']",
            # 滑块提示文字
            "text='请拖动滑块'",
            "text='滑动验证'",
            "text='请按住滑块'",
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
        """解决滑块验证码
        
        Args:
            page: Playwright页面对象
            max_retries: 最大重试次数
            
        Returns:
            True - 解决成功
            False - 解决失败
        """
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
                result = self._simulate_human_drag_fallback(page)
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
    
    def _simulate_human_drag_fallback(self, page: Page) -> bool:
        """模拟人工拖动滑块（备用方案）"""
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
        """生成模拟人类拖动的轨迹点
        
        使用正弦曲线模拟加速-减速过程
        """
        trajectory = []
        distance = end - start
        
        for i in range(steps):
            # 使用正弦函数模拟先加速后减速
            progress = i / steps
            eased = 0.5 - 0.5 * (3.14159 * (progress - 0.5))
            x = start + distance * (progress + random.uniform(-0.02, 0.02))
            trajectory.append(x)
        
        # 确保最后到达目标
        trajectory.append(end)
        return trajectory


class KujialeScraper:
    """酷家乐户型图爬虫"""
    
    BASE_URL = "https://www.kujiale.com/huxing/search"
    CITY_CODE_TIANJIN = "120100"  # 天津城市代码
    
    def __init__(self, headless: bool = True, debug: bool = False,
                 cdp_endpoint: str = None, output_dir: str = "./output",
                 page=None, city_code: str = None):
        """初始化爬虫
        
        Args:
            headless: 是否无头模式
            debug: 是否调试模式
            cdp_endpoint: Chrome DevTools Protocol端点
            output_dir: 图片输出目录
            page: 外部传入的Playwright页面对象
            city_code: 城市代码（默认天津120100）
        """
        self.headless = headless
        self.debug = debug
        self.cdp_endpoint = cdp_endpoint
        self.output_dir = Path(output_dir)
        self._external_page = page
        self.city_code = city_code or self.CITY_CODE_TIANJIN
        
        self.browser = None
        self.context = None
        self.page = page
        self._playwright = None
        self._own_browser = False
        
        # 验证码解决器
        self.captcha_solver = CaptchaSolver(debug=debug)
        
        # 拦截的数据
        self._intercepted_data: List[dict] = []
    
    def start(self):
        """启动浏览器"""
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
            self.context = self._browser.new_context(
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
        """关闭浏览器"""
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
        """生成随机User-Agent"""
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
        """批量搜索户型图
        
        Args:
            project_names: 小区名称列表
            max_plans_per_project: 每个小区最大户型数
            
        Returns:
            Dict[小区名, 户型列表]
        """
        results = {}
        total = len(project_names)
        
        for i, name in enumerate(project_names):
            print(f"[酷家乐] [{i + 1}/{total}] 正在搜索: {name}")
            
            try:
                plans = self._search_single_project(name, max_plans_per_project)
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
            
            # 随机延迟，避免请求过快
            if i < total - 1:
                delay = random.uniform(3, 8)
                print(f"  [延迟] 等待 {delay:.1f} 秒...")
                time.sleep(delay)
        
        return results
    
    def _search_single_project(self, project_name: str, max_plans: int) -> List[FloorPlan]:
        """搜索单个小区的户型图
        
        策略：
        1. 访问搜索页面
        2. 设置城市（天津）
        3. 输入小区名称并搜索
        4. 处理可能出现的验证码
        5. 提取户型列表
        
        Args:
            project_name: 小区名称
            max_plans: 最大户型数
            
        Returns:
            户型列表
        """
        plans = []
        
        try:
            # 访问搜索页面
            search_url = f"{self.BASE_URL}?area_id={self.city_code}"
            print(f"  [访问] {search_url}")
            
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(random.uniform(2, 4))
            
            # 处理验证码（如果有）
            if self.captcha_solver.detect_slider_captcha(self.page):
                print("  [验证码] 检测到滑块验证码，尝试自动解决...")
                if not self.captcha_solver.solve_slider_captcha(self.page):
                    print("  [验证码] 自动解决失败，请手动处理或检查ddddocr安装")
                    # 等待手动处理
                    time.sleep(10)
            
            # 查找搜索框并输入小区名称
            if not self._input_search_keyword(project_name):
                print("  [错误] 无法找到搜索框")
                return []
            
            # 等待搜索结果加载
            time.sleep(random.uniform(3, 5))
            
            # 处理可能出现的验证码
            if self.captcha_solver.detect_slider_captcha(self.page):
                print("  [验证码] 搜索后检测到滑块验证码，尝试自动解决...")
                if not self.captcha_solver.solve_slider_captcha(self.page):
                    print("  [验证码] 自动解决失败")
                    time.sleep(10)
            
            # 提取户型数据
            plans = self._extract_floor_plans(project_name, max_plans)
            
        except Exception as e:
            print(f"  [错误] 搜索过程中出现异常: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
        
        return plans
    
    def _input_search_keyword(self, keyword: str) -> bool:
        """在搜索框中输入关键词
        
        Args:
            keyword: 搜索关键词（小区名称）
            
        Returns:
            True - 成功
            False - 失败
        """
        try:
            # 常见的搜索框选择器
            search_input_selectors = [
                "input[placeholder*='小区']",
                "input[placeholder*='搜索']",
                "input[type='text']",
                "[class*='search'] input",
                "[class*='input']",
            ]
            
            search_input = None
            for selector in search_input_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=2000):
                        search_input = element
                        if self.debug:
                            print(f"  [DEBUG] 找到搜索框: {selector}")
                        break
                except:
                    continue
            
            if not search_input:
                # 尝试通过placeholder文本查找
                try:
                    search_input = self.page.get_by_placeholder("请输入小区名称").first
                    if not search_input.is_visible(timeout=2000):
                        search_input = None
                except:
                    pass
            
            if not search_input:
                print("  [错误] 未找到搜索框")
                return False
            
            # 清除原有内容并输入新关键词
            search_input.click()
            search_input.fill("")
            time.sleep(0.5)
            
            # 模拟人工输入（逐字符输入）
            for char in keyword:
                search_input.type(char, delay=random.uniform(50, 150))
            
            time.sleep(random.uniform(0.5, 1))
            
            # 按回车键搜索
            search_input.press("Enter")
            
            if self.debug:
                print(f"  [DEBUG] 已输入关键词: {keyword}")
            
            return True
            
        except Exception as e:
            print(f"  [错误] 输入搜索关键词失败: {e}")
            return False
    
    def _extract_floor_plans(self, project_name: str, max_plans: int) -> List[FloorPlan]:
        """从页面提取户型数据
        
        Args:
            project_name: 小区名称
            max_plans: 最大提取数量
            
        Returns:
            户型列表
        """
        plans = []
        
        try:
            # 等待户型列表加载
            self.page.wait_for_load_state("networkidle", timeout=10000)
            time.sleep(random.uniform(2, 3))
            
            # 查找户型列表容器
            list_selectors = [
                "[class*='floor-plan']",
                "[class*='huxing']",
                "[class*='list']",
                ".result-list",
                "[class*='result']",
            ]
            
            # 提取户型卡片
            card_selectors = [
                "[class*='item']",
                "[class*='card']",
                ".floor-plan-item",
                ".huxing-item",
            ]
            
            cards = []
            for selector in card_selectors:
                try:
                    elements = self.page.locator(selector).all()
                    if elements:
                        cards = elements
                        if self.debug:
                            print(f"  [DEBUG] 使用选择器 '{selector}' 找到 {len(cards)} 个户型卡片")
                        break
                except:
                    continue
            
            if not cards:
                # 尝试从页面提取所有可能包含户型信息的元素
                if self.debug:
                    print("  [DEBUG] 未找到标准户型卡片，尝试备用提取方式...")
                cards = self._extract_floor_plans_fallback()
            
            # 解析每个户型卡片
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
    
    def _extract_floor_plans_fallback(self) -> List:
        """备用提取方式 - 通过JavaScript提取页面数据"""
        cards = []
        
        try:
            # 使用JavaScript提取页面中的户型数据
            js_code = """
            () => {
                const results = [];
                // 查找包含户型信息的元素
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    const text = el.innerText || '';
                    // 检查是否包含户型特征文本
                    if ((text.includes('室') && text.includes('厅')) || 
                        text.includes('m²') || 
                        text.includes('平米') ||
                        text.includes('户型')) {
                        const img = el.querySelector('img');
                        if (img && img.src) {
                            results.push({
                                element: el,
                                text: text,
                                imgSrc: img.src
                            });
                        }
                    }
                }
                return results;
            }
            """
            
            data = self.page.evaluate(js_code)
            if self.debug:
                print(f"  [DEBUG] 备用方式找到 {len(data)} 个可能的数据项")
            
        except Exception as e:
            if self.debug:
                print(f"  [DEBUG] 备用提取失败: {e}")
        
        return cards
    
    def _parse_floor_plan_card(self, card, project_name: str) -> Optional[FloorPlan]:
        """解析单个户型卡片
        
        Args:
            card: Playwright元素句柄
            project_name: 小区名称
            
        Returns:
            FloorPlan对象或None
        """
        try:
            # 提取户型名称
            name_selectors = [
                "[class*='name']",
                "[class*='title']",
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
            
            # 提取房型（如：3室2厅）
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
                        # 提取数字+m²格式
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
            link_selectors = [
                "a",
                "[class*='link']",
            ]
            page_url = ""
            for selector in link_selectors:
                try:
                    link = card.locator(selector).first
                    href = link.get_attribute("href")
                    if href:
                        page_url = href if href.startswith("http") else f"https://www.kujiale.com{href}"
                        break
                except:
                    continue
            
            if not image_url:
                return None
            
            return FloorPlan(
                project_name=project_name,
                plan_name=plan_name or "未知户型",
                room_type=room_type,
                area=area,
                image_url=image_url,
                page_url=page_url,
                source="kujiale"
            )
            
        except Exception as e:
            if self.debug:
                print(f"  [DEBUG] 解析户型卡片失败: {e}")
            return None
    
    def download_floor_plans(self, results: Dict[str, List[FloorPlan]]) -> Dict[str, int]:
        """下载户型图片
        
        Args:
            results: 搜索结果字典
            
        Returns:
            Dict[小区名, 下载数量]
        """
        download_counts = {}
        
        for project_name, plans in results.items():
            if not plans:
                continue
            
            # 创建安全的目录名
            safe_name = re.sub(r"[^\w\u4e00-\u9fff]", "_", project_name)
            project_dir = self.output_dir / safe_name
            project_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"[酷家乐] 下载 {project_name} 的户型图 ({len(plans)} 张)...")
            
            downloaded = 0
            with ThreadPoolExecutor(max_workers=3) as executor:  # 减少并发避免风控
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
        """下载单个户型图片
        
        Args:
            plan: 户型对象
            index: 索引
            safe_name: 安全的小区名
            project_dir: 项目目录
            
        Returns:
            True - 成功
            False - 失败
        """
        try:
            # 生成文件名
            ext = Path(plan.image_url).suffix or ".jpg"
            area_part = plan.area.replace("m²", "平米") if plan.area else ""
            plan_part = plan.plan_name if plan.plan_name and plan.plan_name != "未知户型" else f"户型{index + 1}"
            filename = f"{safe_name}_{plan_part}_{area_part}{ext}"
            filename = re.sub(r"[\\/:*?\"<>|]", "_", filename)
            filename = re.sub(r"_+", "_", filename).strip("_")
            filepath = project_dir / filename
            
            # 下载图片
            headers = {
                "User-Agent": self._random_ua(),
                "Referer": "https://www.kujiale.com/",
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
        """保存结果到JSON文件
        
        Args:
            results: 搜索结果
            output_path: 输出文件路径
        """
        data = {
            "source": "kujiale",
            "city_code": self.city_code,
            "total_projects": len(results),
            "projects": {
                name: [p.to_dict() for p in plans]
                for name, plans in results.items()
            },
        }
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[酷家乐] 结果已保存: {output_path}")


def main():
    """独立测试入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="酷家乐户型图爬虫")
    parser.add_argument("--input", required=True, help="房天下映射JSON输入文件")
    parser.add_argument("--output-dir", default="output/kujiale", help="图片输出目录")
    parser.add_argument("--output-json", default="output/kujiale_results.json", help="JSON输出路径")
    parser.add_argument("--max-plans", type=int, default=20, help="每小区最大户型数")
    parser.add_argument("--connect", action="store_true", help="连接已有浏览器")
    parser.add_argument("--cdp-endpoint", default="http://localhost:9222")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--city-code", default="120100", help="城市代码（默认天津120100）")
    args = parser.parse_args()
    
    # 读取输入文件
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    promo_names = [
        m["promo_name"] for m in data.get("mappings", [])
        if m.get("promo_name")
    ]
    print(f"[酷家乐] 读取到 {len(promo_names)} 个小区名称")
    
    # 运行爬虫
    with KujialeScraper(
        headless=not args.debug,
        debug=args.debug,
        cdp_endpoint=args.cdp_endpoint if args.connect else None,
        output_dir=args.output_dir,
        city_code=args.city_code,
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
