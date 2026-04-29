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
    
    def _search_single_project(self, project_name: str, max_plans: int) -> List[FloorPlan]:
        """搜索单个小区的户型图 - 纯模拟人工访问"""
        plans = []
        
        try:
            # 访问搜索页面
            search_url = f"{self.SEARCH_URL}?cityCode={self.CITY_CODE}&keyword={urllib.parse.quote(project_name)}"
            print(f"  [访问] {search_url}")
            
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(random.uniform(2, 4))
            
            # 处理验证码
            if self.captcha_solver.detect_slider_captcha(self.page):
                print("  [验证码] 检测到滑块验证码，尝试自动解决...")
                if not self.captcha_solver.solve_slider_captcha(self.page):
                    print("  [验证码] 自动解决失败，等待手动处理...")
                    time.sleep(10)
            
            # 等待搜索结果加载
            self.page.wait_for_load_state("networkidle", timeout=10000)
            time.sleep(random.uniform(2, 3))
            
            # 提取户型数据
            plans = self._extract_floor_plans(project_name, max_plans)
            
        except Exception as e:
            print(f"  [错误] 搜索过程中出现异常: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
        
        return plans
    
    def _extract_floor_plans(self, project_name: str, max_plans: int) -> List[FloorPlan]:
        """从页面提取户型数据"""
        plans = []
        
        try:
            # 查找户型卡片
            card_selectors = [
                "[class*='room-item']",
                "[class*='floor-plan']",
                "[class*='huxing']",
                ".room-item",
                ".floor-item",
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
