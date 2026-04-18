"""Pinterest 搜索爬虫"""

import json
import random
import time
import urllib.parse
from pathlib import Path
from typing import Callable, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from shared.models import Pin


def apply_stealth(page: Page):
    """应用 stealth 模式隐藏自动化特征"""
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'permissions', {
            get: () => ({
                query: () => Promise.resolve({ state: 'granted' })
            })
        });
    """)


class PinterestScraper:
    """Pinterest 搜索爬虫"""

    BASE_URL = "https://kr.pinterest.com/search/pins/"

    def __init__(
        self,
        headless: bool = True,
        debug: bool = False,
        cdp_endpoint: str = None,
        progress_callback: Callable[[str, int, int, str], None] = None,
        media_type: str = "all",  # all, images, videos
    ):
        """
        初始化爬虫

        Args:
            headless: 是否无头模式
            debug: 是否调试模式
            cdp_endpoint: Chrome DevTools Protocol 端点，用于连接到已有浏览器
                         例如: http://localhost:9222
            progress_callback: 进度回调函数 (stage, current, total, message)
            media_type: 媒体类型筛选 all/images/videos
        """
        self.headless = headless
        self.debug = debug
        self.cdp_endpoint = cdp_endpoint
        self.progress_callback = progress_callback
        self.media_type = media_type  # 媒体类型筛选
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None
        self._own_browser = True  # 是否是自己启动的浏览器

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        """启动浏览器"""
        self._playwright = sync_playwright().start()

        if self.cdp_endpoint:
            # 连接到已有的 Chrome 浏览器
            print(f"正在连接到已有浏览器: {self.cdp_endpoint}")
            try:
                self.browser = self._playwright.chromium.connect_over_cdp(
                    self.cdp_endpoint
                )
                self._own_browser = False
                print("成功连接到已有浏览器")

                # 获取现有的上下文和页面
                contexts = self.browser.contexts
                if contexts:
                    self.context = contexts[0]
                    pages = self.context.pages
                    if pages:
                        self.page = pages[0]
                        print(f"使用现有页面: {self.page.url}")
                    else:
                        self.page = self.context.new_page()
                else:
                    self.context = self.browser.new_context()
                    self.page = self.context.new_page()

                # 连接模式下也应用 stealth 模式
                apply_stealth(self.page)
                print("已启用 stealth 模式 (连接模式)")

            except Exception as e:
                print(f"连接失败: {e}")
                print("请确保 Chrome 已以调试模式启动:")
                print("  chrome.exe --remote-debugging-port=9222")
                raise
        else:
            # 启动新的浏览器
            self._own_browser = True
            self.browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self.context = self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            self.page = self.context.new_page()

            # 应用 stealth 模式隐藏自动化特征
            apply_stealth(self.page)
            print("已启用 stealth 模式")

        self.page.set_default_timeout(60000)  # 60秒超时

    def close(self):
        """关闭浏览器"""
        if self._own_browser:
            # 只关闭自己启动的浏览器
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
        else:
            # 连接的浏览器，只关闭页面，不关闭浏览器
            print("保持浏览器运行（连接模式）")

        if self._playwright:
            self._playwright.stop()

    def search(
        self,
        keyword: str,
        max_pins: int = 100,
        min_saves: int = 0,
        progress_callback: Callable[[str, int, int, str], None] = None,
        climb_mode: bool = False,
        media_type: str = "all",  # all, images, videos
    ) -> List[Pin]:
        if not self.page:
            raise RuntimeError("浏览器未启动，请先调用 start() 或使用 with 语句")

        if progress_callback is not None:
            self.progress_callback = progress_callback

        self.media_type = media_type

        # 进度回调：开始搜索
        if self.progress_callback:
            self.progress_callback("searching", 0, max_pins, f"开始搜索: {keyword}")

        self._current_keyword = keyword
        encoded_keyword = urllib.parse.quote(keyword)
        url = f"{self.BASE_URL}?q={encoded_keyword}"

        # 检查当前页面是否已经是搜索结果页
        current_url = self.page.url
        if keyword in current_url and "/search/" in current_url:
            print(f"当前页面已是搜索结果页，直接开始收集数据")
        else:
            print(f"正在访问: {url}")
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"页面加载警告: {e}")
                # 尝试继续，页面可能已经部分加载

        # 模拟真实用户浏览行为，等待页面完全加载
        wait_time = random.uniform(5, 8)
        print(f"等待页面加载 ({wait_time:.1f}秒)...")
        time.sleep(wait_time)

        # 检测是否需要登录
        self._check_login_required()

        # 进度回调：开始收集
        if self.progress_callback:
            self.progress_callback("collecting", 0, max_pins, "开始收集数据")

        # 根据min_saves和climb_mode决定使用哪种收集方式：
        # - 有 min_saves 过滤或爬坡模式 → 探索模式（逐个点击pin获取详情）
        # - 纯数量收集（min_saves=0, climb_mode=False） → 滚动模式（更快）
        if min_saves > 0 or climb_mode:
            mode_str = (
                "纯爬坡模式"
                if climb_mode
                else f"相似推荐探索模式 (min_saves={min_saves})"
            )
            print(f"使用{mode_str}")
            return self._explore_similar_pins(
                max_pins, min_saves, climb_mode=climb_mode
            )
        else:
            print(f"使用滚动收集模式")
            return self._scroll_and_collect(max_pins)

    def _check_login_required(self):
        """检测是否需要登录，如果需要则等待用户登录"""
        try:
            # 检测登录墙或登录按钮
            login_required = self.page.evaluate("""
                () => {
                    // 检测登录模态框
                    const loginModal = document.querySelector('[data-test-id="login-modal"]');
                    const signupButton = document.querySelector('[data-test-id="signup-button"]');
                    const loginButton = document.querySelector('[data-test-id="login-button"]');

                    // 检测是否重定向到登录页
                    const isLoginPage = window.location.pathname.includes('/login');

                    // 检测是否有大量登录提示
                    const loginPrompts = document.querySelectorAll('[data-test-id*="login"], [data-test-id*="signup"]');

                    return {
                        hasModal: !!loginModal,
                        hasButtons: !!(signupButton || loginButton),
                        isLoginPage: isLoginPage,
                        promptCount: loginPrompts.length,
                        requiresLogin: !!(loginModal || signupButton || loginButton || isLoginPage)
                    };
                }
            """)

            if login_required["requiresLogin"]:
                print("\n" + "=" * 60)
                print("⚠️  检测到需要 Pinterest 登录")
                print("=" * 60)
                print("\n请在打开的浏览器窗口中手动登录 Pinterest")
                print("登录完成后，程序将自动继续...")
                print("\n提示：")
                print("  1. 使用邮箱/密码登录")
                print("  2. 或使用Google/Facebook账号登录")
                print("  3. 登录成功后会自动保存登录状态")
                print("=" * 60 + "\n")

                # 等待用户登录（最长等待5分钟）
                print("等待登录中...")
                max_wait = 300  # 5分钟
                wait_interval = 5
                waited = 0

                while waited < max_wait:
                    time.sleep(wait_interval)
                    waited += wait_interval

                    # 再次检查是否还需要登录
                    try:
                        still_requires_login = self.page.evaluate("""
                            () => {
                                const loginModal = document.querySelector('[data-test-id="login-modal"]');
                                const signupButton = document.querySelector('[data-test-id="signup-button"]');
                                const loginButton = document.querySelector('[data-test-id="login-button"]');
                                const isLoginPage = window.location.pathname.includes('/login');
                                return !!(loginModal || signupButton || loginButton || isLoginPage);
                            }
                        """)

                        if not still_requires_login:
                            print("\n✓ 登录成功！继续执行爬取任务...")
                            print("登录状态已保存，下次运行将自动使用。")
                            return

                        # 每30秒提示一次
                        if waited % 30 == 0:
                            print(f"  仍在等待登录... ({waited}秒)")

                    except Exception as e:
                        if self.debug:
                            print(f"检查登录状态出错: {e}")

                # 超时
                raise RuntimeError(
                    f"登录等待超时（{max_wait}秒）。请重新运行程序并完成登录。"
                )

        except RuntimeError:
            raise
        except Exception as e:
            if self.debug:
                print(f"登录检测出错: {e}")

    def _ensure_and_click_pin(self, clicked_pins, keyword):
        visible_pins = self._get_visible_pin_elements()
        if not visible_pins:
            return False
        unclicked = [p for p in visible_pins if p["id"] not in clicked_pins]
        if not unclicked:
            return False
        selected = random.choice(unclicked)
        pin_id = selected["id"]
        clicked_pins.add(pin_id)
        self._interact_with_pin(pin_id, 0, {}, keyword)
        return True

    def _scroll_and_collect(self, max_pins: int) -> List[Pin]:
        """滚动页面并收集数据（拟人化浏览模式）"""
        collected_pins = {}
        main_pin_count = 0  # 主 pin 计数
        scroll_count = 0
        max_scrolls = 50  # 最大滚动次数限制
        no_new_pins_count = 0  # 连续没有新数据的次数
        clicked_pins = set()  # 已点击查看的 pin ID

        # 先滚动1-2次加载数据，模拟用户浏览（根据需求调整）
        init_scrolls = 1 if max_pins <= 10 else 2
        print(f"正在加载页面内容...")
        for i in range(init_scrolls):
            try:
                self._scroll_page()
            except Exception as e:
                print(f"滚动时出错: {e}")
            wait_time = random.uniform(2, 4)
            print(f"等待 {wait_time:.1f}秒...")
            time.sleep(wait_time)

        while main_pin_count < max_pins and scroll_count < max_scrolls:
            try:
                # 提取当前页面的 Pin 数据（基本信息）
                pins = self._extract_pins_from_page()

                new_pins_found = False
                for pin in pins:
                    # Redis查重：跳过已收集的pin
                    if Pin.is_collected(pin.id):
                        continue

                    collected_pins[pin.id] = pin
                    Pin.mark_as_collected(pin.id)
                    new_pins_found = True
                    main_pin_count += 1  # 计数主 pin
                    print(
                        f"已收集 {main_pin_count}/{max_pins} 个主 Pin，总计 {len(collected_pins)} 个..."
                    )

                    # 进度回调：更新收集进度
                    if self.progress_callback:
                        self.progress_callback(
                            "collecting",
                            main_pin_count,
                            max_pins,
                            f"已收集 {main_pin_count}/{max_pins} 个Pin",
                        )

                    if main_pin_count >= max_pins:
                        break

                if main_pin_count >= max_pins:
                    break

                # 如果没有新数据，计数
                if not new_pins_found:
                    no_new_pins_count += 1
                    if no_new_pins_count >= 5:
                        print("连续多次没有新数据，停止爬取")
                        break
                else:
                    no_new_pins_count = 0

                # 随机滚动策略：模拟真实用户行为
                # 30%概率：滚动一次后选择
                # 30%概率：滚动多次后选择
                # 40%概率：不滚动直接选择
                scroll_strategy = random.random()
                if scroll_strategy < 0.3:
                    # 滚动一次
                    self._scroll_page()
                    time.sleep(random.uniform(1, 2))
                elif scroll_strategy < 0.6:
                    # 滚动多次（2-4次）
                    scroll_times = random.randint(2, 4)
                    for _ in range(scroll_times):
                        self._scroll_page()
                        time.sleep(random.uniform(1, 2))
                # else: 40%概率不额外滚动

                # 强制点击一个可见 pin，确保每次循环都有采集
                if not self._ensure_and_click_pin(clicked_pins, keyword):
                    try:
                        self._scroll_page()
                        time.sleep(random.uniform(2, 3))
                        self._ensure_and_click_pin(clicked_pins, keyword)
                    except Exception:
                        pass

                # 根据滚动策略做可选额外滚动
                scroll_strategy = random.random()
                if scroll_strategy < 0.4:
                    self._scroll_page()
                    time.sleep(random.uniform(1, 2))
                elif scroll_strategy < 0.7:
                    scroll_times = random.randint(2, 4)
                    for _ in range(scroll_times):
                        self._scroll_page()
                        time.sleep(random.uniform(1, 2))

                # 统一等待
                time.sleep(random.uniform(2, 4))

                # 每爬取 20 个主 pin，额外休息
                if main_pin_count > 0 and main_pin_count % 20 == 0:
                    time.sleep(random.uniform(15, 30))

            except Exception as e:
                print(f"收集数据时出错: {e}")
                scroll_count += 1
                time.sleep(3)
                continue

        print(f"搜索页面收集完成")
        print(f"主 Pin: {main_pin_count} 个")
        print(f"相似推荐: {len(collected_pins) - main_pin_count} 个")
        print(f"总计: {len(collected_pins)} 个")

        # 返回所有收集的 pins（包括主 pin 和相似推荐）
        # 注意：不再需要 enrich_pins_with_details，因为详情已在交互过程中收集
        return list(collected_pins.values())

    def _explore_similar_pins(
        self, target_count: int, min_saves: int, climb_mode: bool = False
    ) -> List[Pin]:
        """通过相似推荐链进行贪心爬山探索

        逻辑：
        1. 搜索关键词 → 在搜索页随机点击一个pin（当前主体）
        2. 提取当前主体的saves等数据
        3. 如果saves >= min_saves → 找到达标pin，在当前详情页爬取所有相似推荐数据
        4. 如果saves < min_saves → 查看相似推荐：
           - 点击一个相似推荐，提取其saves
           - 如果相似推荐的saves > 当前主体的saves → 更换主体为该相似推荐
           - 如果不大于 → 保持当前主体，继续看下一个相似推荐
        5. 返回搜索页，选下一个起始pin，重复直到收集足够多的达标pin

        Args:
            target_count: 目标收集数量
            min_saves: 最小保存数阈值
            climb_mode: 纯爬坡模式，不检查min_saves，持续找更优直到收集够数量
        """
        collected_pins = {}  # 存所有收集到的 pin（含相似推荐）
        qualified_count = 0  # 只统计真正达标且符合媒体类型的 pin 数量
        visited_ids = set()
        max_attempts = max(target_count * 10, 50)  # 给足够的尝试次数
        max_depth = 15
        attempt = 0

        try:
            # 滚动几次搜索页，加载更多 pin，避免搜索页 pin 不够
            search_pin_ids = self._get_search_page_pin_ids()
            if not search_pin_ids:
                print("搜索页面没有找到任何pin，尝试滚动加载...")
                for _ in range(3):
                    self._scroll_page_with_pgdn()
                search_pin_ids = self._get_search_page_pin_ids()

            if not search_pin_ids:
                print("搜索页面没有找到任何pin，无法开始探索")
                return []

            # 若搜索页 pin 数量不足目标的 3 倍，继续滚动补充（最多5次PGDN点击）
            scroll_clicks = 0
            while len(search_pin_ids) < target_count * 3 and scroll_clicks < 5:
                self._scroll_page_with_pgdn()  # 单次点击PGDN
                scroll_clicks += 1
                search_pin_ids = self._get_search_page_pin_ids()

            print(
                f"搜索页发现 {len(search_pin_ids)} 个pin，开始贪心探索模式 (min_saves={min_saves})"
            )
            random.shuffle(search_pin_ids)

            while qualified_count < target_count and attempt < max_attempts:
                attempt += 1

                # 从搜索页选一个未访问的起始pin
                entry_pin_id = None
                for pid in search_pin_ids:
                    if pid not in visited_ids:
                        entry_pin_id = pid
                        break

                if entry_pin_id is None:
                    print("搜索页上所有pin都已探索过，探索结束")
                    break

                print(f"\n{'=' * 50}")
                print(
                    f"[已收集:{len(collected_pins)}/{target_count}] 从搜索页进入 pin: {entry_pin_id}"
                )
                print(f"{'=' * 50}")

                # 点击搜索页上的pin，进入详情页
                try:
                    pin_link = self.page.query_selector(
                        f'a[href*="/pin/{entry_pin_id}"]'
                    )
                    if not pin_link:
                        print(f"  未找到pin {entry_pin_id} 的链接，跳过")
                        visited_ids.add(entry_pin_id)
                        continue

                    # 滚动到元素可见
                    try:
                        pin_link.scroll_into_view_if_needed()
                        time.sleep(random.uniform(0.5, 1))
                    except Exception:
                        pass

                    # 记录点击前的URL
                    before_url = self.page.url
                    pin_link.click()

                    # 等待URL变化，确认进入详情页
                    try:
                        self.page.wait_for_function(
                            f'() => window.location.href.includes("/pin/{entry_pin_id}")',
                            timeout=8000
                        )
                    except Exception as e:
                        print(f"  点击后未进入详情页，URL未变化: {e}")
                        visited_ids.add(entry_pin_id)
                        continue

                    time.sleep(random.uniform(2, 3))
                except Exception as e:
                    print(f"  点击pin {entry_pin_id} 失败: {e}")
                    visited_ids.add(entry_pin_id)
                    continue

                # 当前主体：从搜索页进入的pin
                current_pin_id = entry_pin_id
                current_saves = 0
                depth = 0
                found_qualified = False

                while depth < max_depth and qualified_count < target_count:
                    depth += 1

                    if current_pin_id in visited_ids and not found_qualified:
                        print(f"  [深度{depth}] pin {current_pin_id} 已访问过，跳过")
                        break
                    visited_ids.add(current_pin_id)

                    # 1. 提取当前所在详情页的数据
                    print(f"  [深度{depth}] 提取 pin {current_pin_id} 的数据...")
                    details = self._extract_pin_details_from_modal()

                    if not details or not details.get("id"):
                        print(f"  [深度{depth}] 无法提取详情，中断当前深度")
                        break

                    saves = details.get("saves", 0) or 0
                    title = details.get("title", "无标题")[:40]
                    is_video = details.get("is_video", False)
                    print(f"  [深度{depth}] '{title}...' Saves: {saves}")

                    current_saves = saves  # 记录当前节点的 saves，作为后续爬坡的对比基准

                    # 2. 判断是否收集当前节点：只要 saves >= min_saves 且媒体类型匹配，就无脑收集
                    if saves >= min_saves:
                        media_match = True
                        if self.media_type == "images" and is_video: media_match = False
                        if self.media_type == "video" and not is_video: media_match = False

                        if media_match and current_pin_id not in collected_pins:
                            # 构建并保存 Pin
                            images = details.get("images", {})
                            pin = Pin(
                                id=str(current_pin_id),
                                title=details.get("title", ""),
                                description=details.get("description", ""),
                                image_url=(images.get("orig", {}).get("url", "") if isinstance(images, dict) else ""),
                                image_url_736x=(images.get("736x", {}).get("url", "") if isinstance(images, dict) else ""),
                                saves=saves,
                                likes=details.get("likes", 0) or 0,
                                comments=details.get("comments", 0) or 0,
                                link=f"https://kr.pinterest.com/pin/{current_pin_id}/",
                                pinner=details.get("pinner", ""),
                                source="explore_mode",
                                is_video=is_video,
                                video_url=details.get("video_url", "")
                            )
                            collected_pins[current_pin_id] = pin
                            qualified_count += 1
                            found_qualified = True
                            print(f"  [深度{depth}] ✓ 成功收集！(Saves={saves}) 进度: {qualified_count}/{target_count}")

                            # 如果收集够了，直接结束全部流程
                            if qualified_count >= target_count:
                                print(f"  [深度{depth}] 已收集{target_count}个，停止任务")
                                self._navigate_back_to_search(self._current_keyword)
                                break

                    # 3. 核心爬坡寻路逻辑：寻找下一个跳板 (决定是否要在下一个 pin 的详情页继续)
                    # 规则：点进相似推荐，提取 saves，只有 saves > current_saves 才留下，否则后退。
                    print(f"  [深度{depth}] 开始寻找更优跳板 (目标 Saves > {current_saves})...")
                    
                    similar_pins = self._find_similar_pins_in_modal(scroll_times=1)
                    unvisited = [sp for sp in similar_pins if sp["id"] not in visited_ids]
                    
                    upgraded = False
                    
                    # 遍历未访问的相似推荐，最多检查 5 个防止陷入死循环
                    for sp in unvisited[:5]:
                        sp_id = sp["id"]
                        print(f"    尝试点击推荐: {sp_id}")
                        try:
                            similar_link = self.page.query_selector(f'a[href*="/pin/{sp_id}"]')
                            if not similar_link:
                                continue
                                
                            similar_link.scroll_into_view_if_needed()
                            time.sleep(random.uniform(0.5, 1))
                            similar_link.click()
                            time.sleep(random.uniform(3, 5))  # 等待新详情页加载
                            
                            sp_details = self._extract_pin_details_from_modal()
                            if not sp_details or not sp_details.get("id"):
                                print("      提取失败，后退")
                                visited_ids.add(sp_id)
                                self.page.go_back()
                                time.sleep(random.uniform(1.5, 2.5))
                                continue
                                
                            sp_saves = sp_details.get("saves", 0) or 0
                            
                            # 核心对比逻辑：决定是否停留
                            if sp_saves > current_saves:
                                print(f"      → 发现更优跳板! {sp_saves} > {current_saves}")
                                current_pin_id = sp_id  # 替换主体
                                upgraded = True
                                break  # 打破 for 循环，停留在新页面，由外层 while 继续深度探索
                            else:
                                print(f"      → 不够优 ({sp_saves} <= {current_saves})，后退查看下一个")
                                visited_ids.add(sp_id)
                                self.page.go_back()  # 不够优，用 go_back 退回 current_pin_id 的页面
                                time.sleep(random.uniform(2, 3))
                                
                        except Exception as e:
                            print(f"      检查跳板时出错: {e}，尝试后退")
                            visited_ids.add(sp_id)
                            try: self.page.go_back() 
                            except: pass
                            continue

                    # 如果检查了推荐都没有更优的，说明到了局部最优，必须退回搜索页重新选起点了
                    if not upgraded:
                        print(f"  [深度{depth}] 当前节点已是局部最优，无更好推荐。返回搜索页更换起点。")
                        self._navigate_back_to_search(self._current_keyword)
                        break
                if not found_qualified:
                    try:
                        self._close_pin_modal()
                        time.sleep(random.uniform(1, 2))
                        self._navigate_back_to_search(self._current_keyword)
                        time.sleep(random.uniform(2, 4))
                    except Exception:
                        pass

                time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f"\n探索过程出错: {e}")
            import traceback

            traceback.print_exc()

        print(f"\n探索完成: 共收集 {len(collected_pins)} 个pin (尝试 {attempt} 次)")
        return list(collected_pins.values())

    def _scrape_similar_from_current_page(
        self, source_pin_id: str, collected_pins: dict, visited_ids: set
    ):
        """在当前达标pin的详情页爬取所有可见的相似推荐数据

        点击每个相似推荐 → 提取数据 → go_back → 继续下一个
        """
        similar_pins = self._find_similar_pins_in_modal()
        if not similar_pins:
            print("  当前详情页无相似推荐")
            return

        print(f"  发现 {len(similar_pins)} 个相似推荐，开始逐个提取数据...")

        for i, sp in enumerate(similar_pins):
            sp_id = sp["id"]
            if sp_id in collected_pins:
                print(f"    [{i + 1}/{len(similar_pins)}] pin {sp_id} 已收集，跳过")
                continue

            try:
                # 尝试多种选择器匹配详情链接
                similar_link = None
                selectors = [
                    f'a[href*="/pin/{sp_id}"]',
                    f'a[href*="pin/{sp_id}"]',
                    f'[href*="/pin/{sp_id}"]',
                ]
                for selector in selectors:
                    try:
                        el = self.page.query_selector(selector)
                        if el and el.is_visible():
                            similar_link = el
                            break
                    except:
                        continue

                if not similar_link:
                    print(f"      未找到 pin {sp_id} 的链接")
                    continue

                print(f"      点击相似推荐: {sp_id}")
                # 滚动到元素可见
                similar_link.scroll_into_view_if_needed()
                time.sleep(random.uniform(0.5, 1))
                similar_link.click()
                time.sleep(random.uniform(2, 4))

                sp_details = self._extract_pin_details_from_modal()
                if sp_details and sp_details.get("id"):
                    saves = sp_details.get("saves", 0) or 0
                    likes = sp_details.get("likes", 0) or 0
                    comments = sp_details.get("comments", 0) or 0
                    sp_is_video = sp_details.get("is_video", False)
                    video_url = sp_details.get("video_url", "")

                similar_pin = Pin(
                    id=str(sp_id),
                    title=sp_details.get("title", ""),
                    description=sp_details.get("description", ""),
                    image_url=sp_image_url,
                    image_url_736x=sp_image_736x,
                    saves=sp_saves,
                    likes=sp_likes,
                    comments=sp_comments,
                    link=f"https://kr.pinterest.com/pin/{sp_id}/",
                    pinner=sp_details.get("pinner", ""),
                    source=f"similar_from_{source_pin_id}",
                    is_video=is_video,
                    video_url=video_url,
                )
                collected_pins[sp_id] = similar_pin
                visited_ids.add(sp_id)
                print(f"      Saved: {sp_saves} | Likes: {sp_likes}")

            except Exception as e:
                print(f"    [{i + 1}/{len(similar_pins)}] 提取失败: {e}")
                try:
                    self.page.go_back()
                    time.sleep(random.uniform(2, 3))
                except Exception:
                    pass

    def _collect_similar_pins_from_qualified(
        self,
        qualified_pin_id: str,
        collected_pins: dict,
        visited_ids: set,
        target_count: int,
        min_saves: int = 0,
        qualified_count: int = 0,
    ) -> int:
        """在达标的详情页中收集相似推荐数据，返回更新后的 qualified_count"""
        print(f"    在达标详情页 {qualified_pin_id} 中收集相似推荐...")

        processed_in_this_page = set()
        batch_size = 8
        max_batches = 5

        for batch in range(max_batches):
            similar_pins = self._find_similar_pins_in_modal(scroll_times=1)
            if not similar_pins:
                print(f"    第{batch + 1}批: 没有更多推荐")
                break

            new_pins = [
                sp for sp in similar_pins if sp["id"] not in processed_in_this_page
            ]
            if not new_pins:
                print(f"    第{batch + 1}批: 本页已处理完")
                break

            batch_pins = new_pins[:batch_size]
            print(
                f"    第{batch + 1}批: 处理{len(batch_pins)}个，当前达标({qualified_count}/{target_count})"
            )

            for sp in batch_pins:
                sp_id = sp["id"]

                if sp_id in processed_in_this_page or sp_id in visited_ids:
                    continue
                processed_in_this_page.add(sp_id)

                # 用达标计数判断是否已完成
                if qualified_count >= target_count:
                    print(f"    已达标{qualified_count}个，停止")
                    return qualified_count

                try:
                    similar_link = self.page.query_selector(f'a[href*="/pin/{sp_id}"]')
                    if not similar_link:
                        continue

                    print(f"      点击相似推荐: {sp_id}")
                    similar_link.click()
                    time.sleep(random.uniform(2, 4))

                    sp_details = self._extract_pin_details_from_modal()
                    if sp_details and sp_details.get("id"):
                        saves = sp_details.get("saves", 0) or 0
                        likes = sp_details.get("likes", 0) or 0
                        comments = sp_details.get("comments", 0) or 0
                        sp_is_video = sp_details.get("is_video", False)

                        # 媒体类型筛选
                        if self.media_type != "all":
                            if self.media_type == "images" and sp_is_video:
                                print(f"        是视频，跳过")
                                self._back_to_parent_pin()
                                continue
                            if self.media_type == "video" and not sp_is_video:
                                print(f"        是图片，跳过")
                                self._back_to_parent_pin()
                                continue

                        # min_saves 筛选：不达标的不计入 qualified_count
                        if saves < min_saves:
                            print(
                                f"        saves={saves} < min_saves={min_saves}，跳过"
                            )
                            self._back_to_parent_pin()
                            continue

                        images = sp_details.get("images", {})
                        image_url = (
                            images.get("orig", {}).get("url", "")
                            if isinstance(images, dict)
                            else ""
                        )
                        image_736x = (
                            images.get("736x", {}).get("url", "")
                            if isinstance(images, dict)
                            else ""
                        )

                        if sp_id not in collected_pins:
                            pin = Pin(
                                id=str(sp_id),
                                title=sp_details.get("title", ""),
                                description=sp_details.get("description", ""),
                                image_url=image_url,
                                image_url_736x=image_736x,
                                saves=saves,
                                likes=likes,
                                comments=comments,
                                link=f"https://kr.pinterest.com/pin/{sp_id}/",
                                pinner=sp_details.get("pinner", ""),
                                source=f"similar_from_{qualified_pin_id}",
                                is_video=sp_is_video,
                                video_url=sp_details.get("video_url", ""),
                            )
                            collected_pins[sp_id] = pin
                            visited_ids.add(sp_id)
                            qualified_count += 1
                            print(
                                f"        已收集({qualified_count}/{target_count}): saves={saves} is_video={sp_is_video}"
                            )

                            if self.progress_callback:
                                self.progress_callback(
                                    "enriching",
                                    qualified_count,
                                    target_count,
                                    f"达标页收集: {qualified_count}/{target_count}个",
                                )

                            if qualified_count >= target_count:
                                self._back_to_parent_pin()
                                return qualified_count

                    self._back_to_parent_pin()

                except Exception as e:
                    print(f"      收集失败: {e}")
                    self._back_to_parent_pin()

            print(f"    第{batch + 1}批完成")

            if not new_pins:
                break

            if batch < max_batches - 1:
                print(f"    滚动加载第{batch + 2}批...")
                try:
                    viewport = self.page.viewport_size
                    if viewport:
                        self.page.mouse.move(
                            viewport["width"] // 2, viewport["height"] // 2
                        )
                        self.page.mouse.wheel(0, 800)
                    time.sleep(random.uniform(2, 3))
                except Exception as e:
                    print(f"    滚动失败: {e}")
                    break

        print(f"    达标详情页收集完成，qualified_count={qualified_count}")
        return qualified_count

    def _back_to_parent_pin(self):
        """返回到原详情页（支持多种方式）"""
        print("      返回原详情页...")

        # 首先尝试浏览器后退（最可靠的方式回到上一页）
        try:
            self.page.go_back()
            time.sleep(1.5)
            print("      ✓ 已返回")
            return
        except Exception as e:
            print(f"      浏览器后退失败: {e}")

        # 备用方式1: 按Escape关闭当前modal
        try:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)
        except:
            pass

        # 备用方式2: 点击关闭按钮
        try:
            close_btn = self.page.query_selector('[data-test-id="close-button"]')
            if close_btn:
                close_btn.click()
                time.sleep(0.5)
        except:
            pass

        # 等待页面稳定
        time.sleep(random.uniform(1, 2))

    def _get_search_page_pin_ids(self) -> list:
        """获取搜索页面上所有pin的ID列表（不滚动，只取当前可见的）

        Returns:
            pin ID列表
        """
        try:
            # 简单等待页面稳定，不强制等待所有图片加载（Pinterest是懒加载）
            time.sleep(random.uniform(1, 2))

            pin_ids = self.page.evaluate("""
                () => {
                    const ids = [];
                    const seen = new Set();
                    const links = document.querySelectorAll('a[href*="/pin/"]');
                    links.forEach(link => {
                        const match = link.href.match(/\\/pin\\/([0-9]+)/);
                        if (match && !seen.has(match[1])) {
                            seen.add(match[1]);
                            ids.push(match[1]);
                        }
                    });
                    return ids;
                }
            """)
            print(f"  提取到 {len(pin_ids) if pin_ids else 0} 个pin ID")
            return pin_ids if pin_ids else []
        except Exception as e:
            print(f"获取搜索页pin ID失败: {e}")
            return []

    def _scroll_page_with_pgdn(self):
        """使用PageDown键滚动页面 - 单次点击，确保一次调用只滚动一次"""
        try:
            # 点击PGDN键滚动一次
            self.page.keyboard.press("PageDown")
            print(f"  页面滚动: 1次 (PGDN)")
            # 滚动后等待页面加载
            time.sleep(random.uniform(2, 3))

        except Exception as e:
            print(f"页面滚动出错: {e}")
            try:
                # 备用方式：JavaScript 滚动（如果键盘滚动失败）
                self.page.evaluate("window.scrollBy(0, window.innerHeight);")
                time.sleep(random.uniform(2, 3))
            except Exception:
                pass
            except:
                pass

        # 最终等待确保所有内容加载完成
        time.sleep(random.uniform(2, 4))

    def _get_visible_pin_elements(self) -> list:
        """获取当前视口内可见的 pin 元素"""
        try:
            # 使用 JavaScript 查找视口内的 pin 链接
            visible_pins = self.page.evaluate("""
                () => {
                    const pins = [];
                    const processedIds = new Set();

                    // 查找所有 pin 链接
                    const pinLinks = document.querySelectorAll('a[href*="/pin/"]');

                    pinLinks.forEach(link => {
                        try {
                            // 提取 pin ID
                            const match = link.href.match(/\\/pin\\/([0-9]+)/);
                            if (!match) return;

                            const pinId = match[1];
                            if (processedIds.has(pinId)) return;

                            // 检查是否在视口内
                            const rect = link.getBoundingClientRect();
                            const inViewport = (
                                rect.top >= 0 &&
                                rect.left >= 0 &&
                                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                                rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                            );

                            if (inViewport) {
                                processedIds.add(pinId);
                                pins.push({
                                    id: pinId,
                                    element: link
                                });
                            }
                        } catch (e) {
                            // 跳过解析失败的元素
                        }
                    });

                    return pins;
                }
            """)

            if self.debug:
                print(f"发现 {len(visible_pins)} 个可见 pin")

            return visible_pins

        except Exception as e:
            if self.debug:
                print(f"获取可见 pin 失败: {e}")
            return []

    def _close_pin_modal(self):
        """关闭 pin 详情模态框"""
        try:
            # 尝试按 Escape 键关闭
            self.page.keyboard.press("Escape")
            time.sleep(1)

            # 检查模态框是否已关闭
            modal_closed = self.page.evaluate("""
                () => {
                    const modal = document.querySelector('[data-test-id="close-button"]');
                    return !modal;
                }
            """)

            if not modal_closed:
                # 如果 Escape 键无效，尝试点击关闭按钮
                try:
                    close_button = self.page.query_selector(
                        '[data-test-id="close-button"]'
                    )
                    if close_button:
                        close_button.click()
                        time.sleep(1)
                except:
                    pass

        except Exception as e:
            if self.debug:
                print(f"关闭模态框时出错: {e}")

    def _find_similar_pins_in_modal(
        self, scroll_times: int = 1, exclude_ids: set = None
    ) -> list:
        """在 pin 详情模态框中查找相似推荐

        Args:
            scroll_times: 滚动次数，1表示只获取当前可见，>1会滚动加载更多
            exclude_ids: 要排除的pin ID集合（如已访问的）

        Returns:
            相似推荐列表（不包含exclude_ids中的）
        """
        if exclude_ids is None:
            exclude_ids = set()

        try:
            all_pins = []
            seen_ids = set()

            # 获取当前页面的 pin ID，避免把自身加入相似推荐列表
            current_page_pin_id = ""
            try:
                url_match = self.page.evaluate("""
                    () => {
                        const m = window.location.pathname.match(/\\/pin\\/([0-9]+)/);
                        return m ? m[1] : '';
                    }
                """)
                current_page_pin_id = url_match or ""
            except Exception:
                pass

            for scroll in range(scroll_times):
                # 查找当前可见的所有 pin
                similar_pins = self.page.evaluate("""
                    () => {
                        const pins = [];
                        const processedIds = new Set();

                        // 查找所有 pin 链接（在模态框内）
                        const pinLinks = document.querySelectorAll('a[href*="/pin/"]');

                        pinLinks.forEach(link => {
                            try {
                                const match = link.href.match(/\\/pin\\/([0-9]+)/);
                                if (!match) return;

                                const pinId = match[1];
                                if (processedIds.has(pinId)) return;

                                processedIds.add(pinId);
                                pins.push({
                                    id: pinId,
                                    href: link.href
                                });
                            } catch (e) {
                                // 跳过
                            }
                        });

                        return pins;
                    }
                """)

                # 记录新发现的 pins（排除已访问的、已记录的、当前页面自身）
                new_found = 0
                for pin in similar_pins:
                    pin_id = pin["id"]
                    if pin_id in seen_ids or pin_id in exclude_ids:
                        continue
                    if pin_id == current_page_pin_id:
                        continue
                    seen_ids.add(pin_id)
                    all_pins.append(pin)
                    new_found += 1

                if self.debug and scroll_times > 1:
                    print(
                        f"  滚动 {scroll + 1}/{scroll_times}: 发现 {new_found} 个新推荐，累计 {len(all_pins)} 个"
                    )

                # 如果不是最后一次滚动，尝试滚动加载更多
                if scroll < scroll_times - 1:
                    try:
                        viewport = self.page.viewport_size
                        if viewport:
                            center_x = viewport["width"] // 2
                            center_y = viewport["height"] // 2
                            self.page.mouse.move(center_x, center_y)
                            self.page.mouse.wheel(0, 800)
                        else:
                            self.page.keyboard.press("PageDown")
                    except Exception as e:
                        if self.debug:
                            print(f"    滚动失败: {e}")
                        try:
                            self.page.keyboard.press("PageDown")
                        except:
                            pass

                    time.sleep(random.uniform(2, 3))

            # 返回所有找到的相似推荐
            return all_pins

        except Exception as e:
            if self.debug:
                print(f"查找相似推荐失败: {e}")
            return []

    def _extract_pin_details_from_modal(self) -> dict:
        try:
            pin_data = self.page.evaluate("""
                () => {
                    function extractFromPWSData() {
                        const script = document.getElementById('__PWS_DATA__');
                        if (!script) return null;
                        try {
                            const data = JSON.parse(script.textContent);
                            const props = data.props || {};
                            const initialState = props.initialReduxState || {};
                            const pins = initialState.pins || {};
                            const resources = initialState.resources || {};
                            const pinResource = resources.PinResource || {};
                            for (const [id, pin] of Object.entries(pins)) {
                                const aggData = pin.aggregated_pin_data || {};
                                const stats = aggData.aggregated_stats || {};
                                let likes = 0;
                                if (pin.reaction_counts && pin.reaction_counts["1"]) {
                                    likes = parseInt(pin.reaction_counts["1"]) || 0;
                                }
                                const result = {
                                    id: id,
                                    title: pin.grid_title || pin.title || '',
                                    description: pin.description || '',
                                    saves: parseInt(stats.saves) || 0,
                                    likes: likes,
                                    comments: parseInt(aggData.comment_count) || 0,
                                    pinner: (pin.pinner || {}).username || '',
                                    images: pin.images || {}
                                };
                                if (result.saves > 0 || result.likes > 0 || result.comments > 0) {
                                    return result;
                                }
                            }
                            for (const [key, resource] of Object.entries(pinResource)) {
                                if (resource && resource.data) {
                                    const pin = resource.data;
                                    const aggData = pin.aggregated_pin_data || {};
                                    const stats = aggData.aggregated_stats || {};
                                    let likes = 0;
                                    if (pin.reaction_counts && pin.reaction_counts["1"]) {
                                        likes = parseInt(pin.reaction_counts["1"]) || 0;
                                    }
                                    const result = {
                                        id: String(pin.id || key),
                                        title: pin.grid_title || pin.title || '',
                                        description: pin.description || '',
                                        saves: parseInt(stats.saves) || 0,
                                        likes: likes,
                                        comments: parseInt(aggData.comment_count) || 0,
                                        pinner: (pin.pinner || {}).username || '',
                                        images: pin.images || {}
                                    };
                                    if (result.saves > 0 || result.likes > 0) {
                                        return result;
                                    }
                                }
                            }
                            return null;
                        } catch (e) {
                            return null;
                        }
                    }
                    function extractFromDOM() {
                        let saves = 0, likes = 0, comments = 0, title = '', description = '', pinId = '';
                        const urlMatch = window.location.pathname.match(/\\/pin\\/([0-9]+)/);
                        if (urlMatch) pinId = urlMatch[1];
                        const allText = document.body.innerText || '';
                        const savePatterns = [
                            /(\\d[\\d,]*)\\s*(saves?|saved|保存|收藏)/i,
                            /(saves?|saved|保存|收藏)\\s*(\\d[\\d,]*)/i,
                        ];
                        for (const pat of savePatterns) {
                            const m = allText.match(pat);
                            if (m) { saves = parseInt((m[1] || m[2]).replace(/,/g, '')) || 0; break; }
                        }
                        const likePatterns = [
                            /(\\d[\\d,]*)\\s*(likes?|liked|赞)/i,
                            /(likes?|liked|赞)\\s*(\\d[\\d,]*)/i,
                        ];
                        for (const pat of likePatterns) {
                            const m = allText.match(pat);
                            if (m) { likes = parseInt((m[1] || m[2]).replace(/,/g, '')) || 0; break; }
                        }
                        const commentPatterns = [
                            /(\\d[\\d,]*)\\s*(comments?|评论)/i,
                            /(comments?|评论)\\s*(\\d[\\d,]*)/i,
                        ];
                        for (const pat of commentPatterns) {
                            const m = allText.match(pat);
                            if (m) { comments = parseInt((m[1] || m[2]).replace(/,/g, '')) || 0; break; }
                        }
                        const titleEl = document.querySelector('[data-test-id="pin-title"]')
                            || document.querySelector('h1');
                        if (titleEl) title = titleEl.textContent.trim();
                        const imgEl = document.querySelector('img[src*="pinimg"]');
                        let imageUrl = '';
                        if (imgEl) imageUrl = imgEl.src || '';
                        if (saves > 0 || likes > 0 || comments > 0 || title) {
                            return {
                                id: pinId,
                                title: title,
                                description: description,
                                saves: saves,
                                likes: likes,
                                comments: comments,
                                pinner: '',
                                images: imageUrl ? { orig: { url: imageUrl } } : {}
                            };
                        }
                        return null;
                    }
                    return extractFromPWSData() || extractFromDOM();
                }
            """)

            if pin_data:
                images = pin_data.get("images", {})
                image_url = (
                    images.get("orig", {}).get("url", "")
                    if isinstance(images, dict)
                    else ""
                )
                image_url_736x = (
                    images.get("736x", {}).get("url", "")
                    if isinstance(images, dict)
                    else ""
                )
                pin_data["image_url"] = image_url
                pin_data["image_url_736x"] = image_url_736x

            return pin_data if pin_data else {}

        except Exception as e:
            if self.debug:
                print(f"从模态框提取详情失败: {e}")
            return {}

    def _navigate_back_to_search(self, keyword: str):
        """安全返回搜索页，绝不使用 goto 刷新页面，保护 SPA 状态"""
        current_url = self.page.url
        if "/search/" in current_url:
            return
            
        print(f"  返回搜索结果页...")
        try:
            # 优先尝试关闭模态框 (Pinterest 最常见的交互，不会破坏瀑布流)
            self._close_pin_modal()
            time.sleep(random.uniform(1.5, 2.5))
            
            # 再次检查，如果关闭弹窗后 URL 还没变回 search，说明发生了真正的路由跳转
            if "/search/" not in self.page.url:
                print("  弹窗关闭无效，尝试使用浏览器后退...")
                self.page.go_back()
                time.sleep(random.uniform(2, 4))
                
        except Exception as e:
            print(f"  返回搜索页出错: {e}")
            time.sleep(2)

    def _interact_with_pin(self, pin_id: str, main_pin_count: int, collected_pins: dict, keyword: str = ""):
        try:
            pin_link = self.page.query_selector(f'a[href*= "/pin/{pin_id}"]')
            if not pin_link:
                if self.debug:
                    print(f"未找到 pin {pin_id} 的元素")
                return

            print(f"  点击查看 pin {pin_id}")
            pin_link.click()
            time.sleep(random.uniform(2, 4))

            details = self._extract_pin_details_from_modal()
            if details and details.get("id"):
                if pin_id in collected_pins:
                    pin = collected_pins[pin_id]
                    pin.title = details.get("title", pin.title)
                    pin.description = details.get("description", pin.description)
                    pin.saves = details.get("saves", 0)
                    pin.likes = details.get("likes", 0)
                    pin.comments = details.get("comments", 0)
                    pin.pinner = details.get("pinner", " ")

            # 根据主pin数量动态调整相似推荐采集数量
            if main_pin_count <= 20:
                max_similar = random.randint(3, 5)
            else:
                max_similar = random.randint(1, 2)

            similar_pins = self._find_similar_pins_in_modal()
            if similar_pins and len(similar_pins) > 0:
                selected_similar = random.sample(
                    similar_pins, min(max_similar, len(similar_pins))
                )
                print(f"  发现 {len(similar_pins)} 个相似推荐，选择 {len(selected_similar)} 个")

                for similar_pin_info in selected_similar:
                    similar_id = similar_pin_info["id"]
                    if similar_id in collected_pins:
                        continue

                    try:
                        similar_link = self.page.query_selector(f'a[href*= "/pin/{similar_id}"]')
                        if similar_link:
                            print(f"    点击相似推荐 {similar_id}")
                            similar_link.click()
                            time.sleep(random.uniform(2, 5))

                            similar_details = self._extract_pin_details_from_modal()
                            if similar_details and similar_details.get("id"):
                                from shared.models import Pin
                                is_video = similar_details.get("is_video", False)
                                video_url = similar_details.get("video_url", " ")

                                # 媒体类型过滤
                                if self.media_type == "images" and is_video:
                                    self.page.go_back()
                                    time.sleep(random.uniform(2, 4))
                                    continue
                                if self.media_type == "video" and not is_video:
                                    self.page.go_back()
                                    time.sleep(random.uniform(2, 4))
                                    continue

                                similar_pin = Pin(
                                    id=str(similar_details.get("id", " ")),
                                    title=similar_details.get("title", " "),
                                    description=similar_details.get("description", " "),
                                    image_url=similar_details.get("image_url", " "),
                                    image_url_736x=similar_details.get("image_url_736x", " "),
                                    saves=similar_details.get("saves", 0),
                                    likes=similar_details.get("likes", 0),
                                    comments=similar_details.get("comments", 0),
                                    link=f"https://kr.pinterest.com/pin/{similar_id}/",
                                    pinner=similar_details.get("pinner", " "),
                                    source=f"similar_from_{pin_id}",
                                    is_video=is_video,
                                    video_url=video_url,
                                )
                                collected_pins[similar_id] = similar_pin
                                print(f"    已收集相似 pin {similar_id}")

                            self.page.go_back()
                            time.sleep(random.uniform(2, 4))
                    except Exception as e:
                        if self.debug:
                            print(f"    点击相似推荐失败: {e}")
                        continue

            reading_time = random.uniform(3, 15)
            print(f"  模拟阅读 {reading_time:.1f} 秒...")
            time.sleep(reading_time)

            # ✅ 修复：仅关闭模态框，绝不强制返回搜索页，保持瀑布流滚动状态
            self._close_pin_modal()
            time.sleep(random.uniform(1, 3))
            
        except Exception as e:
            print(f"与 pin {pin_id} 交互时出错: {e}")
            try:
                self._close_pin_modal()
            except:
                pass

    def _extract_pins_from_page(self) -> List[Pin]:
        """从页面提取 Pin 数据"""
        try:
            # 检查是否有登录墙
            has_login_wall = self.page.evaluate("""
                () => {
                    const loginModal = document.querySelector('[data-test-id="login-modal"]');
                    const signupButton = document.querySelector('[data-test-id="signup-button"]');
                    const loginButton = document.querySelector('[data-test-id="login-button"]');
                    return !!(loginModal || signupButton || loginButton);
                }
            """)

            if has_login_wall:
                print("检测到登录墙，尝试关闭...")

            # 调试：保存截图
            if self.debug:
                self.page.screenshot(path="debug_screenshot.png")
                print("已保存调试截图: debug_screenshot.png")

            # 方式1：尝试从 __PWS_DATA__ JSON 提取
            pins = self._extract_from_json()

            # 方式2：如果 JSON 方式失败，尝试从 DOM 元素提取
            if not pins:
                if self.debug:
                    print("JSON 提取失败，尝试从 DOM 提取...")
                pins = self._extract_from_dom()

            return pins

        except Exception as e:
            print(f"提取数据时出错: {e}")
            return []

    def _extract_from_json(self) -> List[Pin]:
        """从 __PWS_DATA__ JSON 提取 Pin 数据"""
        try:
            # 执行 JavaScript 提取 __PWS_DATA__
            pws_data = self.page.evaluate("""
                () => {
                    const script = document.getElementById('__PWS_DATA__');
                    return script ? script.textContent : null;
                }
            """)

            if not pws_data:
                return []

            data = json.loads(pws_data)

            # 调试：保存JSON
            if self.debug:
                with open("debug_data.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print("已保存调试JSON: debug_data.json")

            # 检查是否被识别为机器人
            is_bad_bot = data.get("context", {}).get("is_bad_bot", False)
            if is_bad_bot:
                print("警告: Pinterest 检测到机器人访问")

            return self._parse_pins_data(data)

        except json.JSONDecodeError as e:
            if self.debug:
                print(f"JSON 解析错误: {e}")
            return []
        except Exception as e:
            if self.debug:
                print(f"JSON 提取错误: {e}")
            return []

    def _extract_from_dom(self) -> List[Pin]:
        """从 DOM 元素直接提取 Pin 数据（基本信息）"""
        try:
            # 使用 JavaScript 从页面提取 Pin 链接
            pins_data = self.page.evaluate("""
                () => {
                    const pins = [];
                    const processedIds = new Set();

                    // 查找所有 pin 链接
                    const pinLinks = document.querySelectorAll('a[href*="/pin/"]');

                    pinLinks.forEach(link => {
                        try {
                            // 从 href 中提取 pin ID
                            const match = link.href.match(/\\/pin\\/([0-9]+)/);
                            if (!match) return;

                            const pinId = match[1];
                            if (processedIds.has(pinId)) return;
                            processedIds.add(pinId);

                            // 获取图片 URL - 从父元素中查找
                            let container = link;
                            for (let i = 0; i < 5; i++) {
                                container = container.parentElement;
                                if (!container) return;
                            }

                            const img = container.querySelector('img[src*="pinimg"]');
                            const imageUrl = img ? img.src : '';
                            const title = img?.alt || '';

                            // 获取 saves/likes/comments 从文本
                            let saves = 0, likes = 0, comments = 0;
                            if (container.textContent) {
                                const text = container.textContent;
                                const saveMatch = text.match(/(\d+(?:,\d+)*)\s*(?:saves?|saved|保存|收藏)/i);
                                if (saveMatch) saves = parseInt(saveMatch[1].replace(/,/g, '')) || 0;
                                const likeMatch = text.match(/(\d+(?:,\d+)*)\s*(?:likes?|liked|赞)/i);
                                if (likeMatch) likes = parseInt(likeMatch[1].replace(/,/g, '')) || 0;
                                const commentMatch = text.match(/(\d+(?:,\d+)*)\s*(?:comments?|评论)/i);
                                if (commentMatch) comments = parseInt(commentMatch[1].replace(/,/g, '')) || 0;
                            }

                            if (pinId && imageUrl) {
                                pins.push({
                                    id: pinId,
                                    title: title,
                                    description: '',
                                    image_url: imageUrl.replace('/236x/', '/originals/').replace('/564x/', '/originals/'),
                                    image_url_736x: imageUrl.replace('/236x/', '/736x/').replace('/564x/', '/736x/'),
                                    saves: saves,
                                    likes: likes,
                                    comments: comments,
                                    link: link.href,
                                    pinner: ''
                                });
                            }
                        } catch (e) {
                            // 跳过解析失败的元素
                        }
                    });

                    return pins;
                }
            """)

            if self.debug:
                print(f"从 DOM 提取到 {len(pins_data)} 个 Pin")

            pins = []
            for pin_data in pins_data:
                try:
                    pin = Pin(
                        id=str(pin_data["id"]),
                        title=pin_data.get("title", ""),
                        description=pin_data.get("description", ""),
                        image_url=pin_data.get("image_url", ""),
                        image_url_736x=pin_data.get("image_url_736x", ""),
                        saves=pin_data.get("saves", 0),
                        likes=pin_data.get("likes", 0),
                        comments=pin_data.get("comments", 0),
                        link=pin_data.get("link", ""),
                        pinner=pin_data.get("pinner", ""),
                        is_video=pin_data.get("is_video", False),
                        video_url=pin_data.get("video_url", ""),
                    )
                    pins.append(pin)
                except Exception as e:
                    if self.debug:
                        print(f"解析 Pin 时出错: {e}")
                    continue

            return pins

        except Exception as e:
            if self.debug:
                print(f"DOM 提取错误: {e}")
            return []

    def fetch_pin_details(self, pin_id: str) -> dict:
        """访问 pin 详情页获取完整数据（saves, comments 等）"""
        try:
            url = f"https://kr.pinterest.com/pin/{pin_id}/"
            if self.debug:
                print(f"  正在获取详情: {url}")

            # 在新标签页打开
            new_page = self.context.new_page()
            new_page.set_default_timeout(30000)

            try:
                new_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(3, 5))

                pin_data = new_page.evaluate("""
                    () => {
                        function fromPWS() {
                            const script = document.getElementById('__PWS_DATA__');
                            if (!script) return null;
                            try {
                                const data = JSON.parse(script.textContent);
                                const pins = (data.props || {}).initialReduxState || {};
                                const pinMap = pins.pins || {};
                                for (const [id, pin] of Object.entries(pinMap)) {
                                    const aggData = pin.aggregated_pin_data || {};
                                    const stats = aggData.aggregated_stats || {};
                                    let likes = 0;
                                    if (pin.reaction_counts && pin.reaction_counts["1"]) {
                                        likes = parseInt(pin.reaction_counts["1"]) || 0;
                                    }
                                    return {
                                        title: pin.grid_title || pin.title || '',
                                        description: pin.description || '',
                                        saves: parseInt(stats.saves) || 0,
                                        likes: likes,
                                        comments: parseInt(aggData.comment_count) || 0,
                                        pinner: (pin.pinner || {}).username || ''
                                    };
                                }
                                return null;
                            } catch (e) { return null; }
                        }
                        function fromDOM() {
                            let saves = 0, likes = 0, comments = 0, title = '';
                            const allText = document.body.innerText || '';
                            let m;
                            m = allText.match(/(\\d[\\d,]*)\\s*(saves?|saved|保存|收藏)/i);
                            if (m) saves = parseInt(m[1].replace(/,/g, '')) || 0;
                            if (!m) { m = allText.match(/(saves?|saved|保存|收藏)\\s*(\\d[\\d,]*)/i); if (m) saves = parseInt(m[2].replace(/,/g, '')) || 0; }
                            m = allText.match(/(\\d[\\d,]*)\\s*(likes?|liked|赞)/i);
                            if (m) likes = parseInt(m[1].replace(/,/g, '')) || 0;
                            if (!m) { m = allText.match(/(likes?|liked|赞)\\s*(\\d[\\d,]*)/i); if (m) likes = parseInt(m[2].replace(/,/g, '')) || 0; }
                            m = allText.match(/(\\d[\\d,]*)\\s*(comments?|评论)/i);
                            if (m) comments = parseInt(m[1].replace(/,/g, '')) || 0;
                            if (!m) { m = allText.match(/(comments?|评论)\\s*(\\d[\\d,]*)/i); if (m) comments = parseInt(m[2].replace(/,/g, '')) || 0; }
                            const titleEl = document.querySelector('[data-test-id="pin-title"]') || document.querySelector('h1');
                            if (titleEl) title = titleEl.textContent.trim();
                            return (saves > 0 || likes > 0 || comments > 0) ? { title, saves, likes, comments, pinner: '', description: '' } : null;
                        }
                        return fromPWS() || fromDOM();
                    }
                """)

                if pin_data:
                    return pin_data

            finally:
                new_page.close()

            return {}

        except Exception as e:
            if self.debug:
                print(f"  获取详情失败: {e}")
            return {}

    def enrich_pins_with_details(
        self, pins: List[Pin], max_pins: int = 100
    ) -> List[Pin]:
        """为 pins 添加详细信息（saves, comments）"""
        enriched_pins = []
        to_fetch = pins[:max_pins]
        total = len(to_fetch)

        print(f"\n正在获取 {total} 个 Pin 的详细信息...")

        # 通知进度：开始获取详情
        if self.progress_callback:
            self.progress_callback(
                "enriching", 0, total, f"开始获取 {total} 个 Pin 的详情"
            )

        for i, pin in enumerate(to_fetch):
            if pin.link:
                details = self.fetch_pin_details(pin.id)

                if details:
                    pin.title = details.get("title", pin.title)
                    pin.description = details.get("description", pin.description)
                    pin.saves = details.get("saves", 0)
                    pin.likes = details.get("likes", 0)
                    pin.comments = details.get("comments", 0)
                    pin.pinner = details.get("pinner", "")

                enriched_pins.append(pin)

                # 显示进度
                saves_str = f"{pin.saves:,}" if pin.saves else "0"
                likes_str = f"{pin.likes:,}" if pin.likes else "0"
                comments_str = f"{pin.comments:,}" if pin.comments else "0"
                title_preview = pin.title[:30] if pin.title else "无标题"
                print(
                    f"  [{i + 1}/{total}] Saves: {saves_str} | Likes: {likes_str} | Comments: {comments_str} | {title_preview}"
                )

                # 更新进度回调
                if self.progress_callback:
                    percentage = int((i + 1) / total * 100)
                    self.progress_callback(
                        "enriching",
                        i + 1,
                        total,
                        f"已获取 {i + 1}/{total} 个详情 - {title_preview}",
                    )

                # 随机延迟，保护账号
                wait_time = random.uniform(3, 6)
                time.sleep(wait_time)

                # 每获取 10 个，额外休息
                if (i + 1) % 10 == 0 and i < total - 1:
                    rest_time = random.uniform(15, 30)
                    print(f"  已获取 {i + 1} 个，休息 {rest_time:.1f}秒...")
                    time.sleep(rest_time)

        return enriched_pins

    def _parse_pins_data(self, data: dict) -> List[Pin]:
        """解析 JSON 数据为 Pin 对象列表"""
        pins = []

        try:
            # 检查数据结构
            props = data.get("props", {})
            if not props:
                if self.debug:
                    print("警告: 没有 props 字段")
                    # 打印顶层键
                    print(f"顶层键: {list(data.keys())}")
                return pins

            initial_state = props.get("initialReduxState", {})
            if not initial_state:
                if self.debug:
                    print("警告: 没有 initialReduxState 字段")
                    print(f"props 键: {list(props.keys())}")
                return pins

            # 方式1：从 pins 对象提取
            pins_data = initial_state.get("pins", {})

            if self.debug:
                print(f"发现 {len(pins_data)} 个 pins")
                # 打印 initialReduxState 的键
                print(f"initialReduxState 键: {list(initial_state.keys())[:10]}")

            # 方式2：从 feeds 提取（搜索结果通常在这里）
            feeds = initial_state.get("feeds", {})

            # 如果 pins 为空，尝试从 feeds 获取 pin IDs
            if not pins_data and feeds:
                for feed_key, feed_data in feeds.items():
                    if isinstance(feed_data, dict) and "items" in feed_data:
                        items = feed_data.get("items", [])
                        if self.debug:
                            print(f"Feed {feed_key}: {len(items)} items")

                        # 从 items 获取 pin 数据
                        for item in items:
                            if isinstance(item, dict):
                                pin_id = item.get("id") or item.get("pin_id")
                                if pin_id and pin_id not in pins_data:
                                    pins_data[str(pin_id)] = item

            for pin_id, pin_data in pins_data.items():
                try:
                    # 提取图片 URL
                    images = pin_data.get("images", {})
                    image_url = images.get("orig", {}).get("url", "")
                    image_url_736x = images.get("736x", {}).get("url", "")

                    # 如果没有 images，尝试其他字段
                    if not image_url and not image_url_736x:
                        # 尝试 image_spec 或其他字段
                        image_spec = pin_data.get("image_spec", {})
                        if image_spec:
                            image_url = image_spec.get("url", "")

                    # 提取 save 数和评论数
                    aggregated_data = pin_data.get("aggregated_pin_data", {})
                    aggregated_stats = aggregated_data.get("aggregated_stats", {})
                    saves = aggregated_stats.get("saves", 0)
                    comments = aggregated_data.get("comment_count", 0)

                    # 提取点赞数 (reaction_counts["1"])
                    likes = 0
                    reaction_counts = pin_data.get("reaction_counts", {})
                    if reaction_counts and "1" in reaction_counts:
                        likes = reaction_counts["1"]

                    # 提取发布者信息
                    pinner = pin_data.get("pinner", {})
                    pinner_name = pinner.get("username", "") if pinner else ""

                    # 检测是否为视频
                    is_video = False
                    video_url = ""
                    if "videos" in pin_data and pin_data["videos"]:
                        is_video = True
                        video_data = pin_data["videos"]
                        if isinstance(video_data, dict) and "video_list" in video_data:
                            # 获取最佳质量的视频URL
                            video_list = video_data["video_list"]
                            for quality in ["V_720P", "V_480P", "V_360P"]:
                                if quality in video_list:
                                    video_url = video_list[quality].get("url", "")
                                    if video_url:
                                        break

                    pin = Pin(
                        id=str(pin_id),
                        title=pin_data.get("grid_title") or pin_data.get("title", ""),
                        description=pin_data.get("description", ""),
                        image_url=image_url,
                        image_url_736x=image_url_736x,
                        saves=saves,
                        likes=likes,
                        comments=comments,
                        link=pin_data.get("link", ""),
                        pinner=pinner_name,
                        is_video=is_video,
                        video_url=video_url,
                    )
                    pins.append(pin)

                except Exception as e:
                    if self.debug:
                        print(f"解析 Pin {pin_id} 时出错: {e}")
                    continue

        except Exception as e:
            print(f"解析 pins 数据时出错: {e}")

        return pins
