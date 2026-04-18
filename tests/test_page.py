import time

from playwright.sync_api import sync_playwright


def scrape_pinterest_search(url, max_scrolls=3):
    """
    抓取 Pinterest 搜索结果瀑布流，并自动嗅探媒体类型。
    :param url: 搜索页 URL
    :param max_scrolls: 模拟鼠标向下滚动的次数
    """
    print(f"🚀 启动 Playwright 抓取瀑布流: {url}")
    
    results = []
    seen_ids = set() # 用于实时去重

    with sync_playwright() as p:
        # headless=False 方便你观察真实的滚动和加载过程，上到服务器可改为 True
        browser = p.chromium.launch(headless=False) 
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # 1. 访问并等待首屏加载
            # ✅ 修改后的代码
            # 1. 改为等待基础 DOM 加载完成即可 (domcontentloaded)
            # 2. 将超时时间稍微放宽到 30 秒 (30000ms)，以防本地网络波动或首次建立连接较慢
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 只要页面的第一个 Pin 卡片被成功渲染出来，我们就立刻往下走，不需要等那些追踪脚本加载完
            page.wait_for_selector('[data-test-id="pin"]', timeout=15000)

            # 2. 循环滚动，触发懒加载
            for scroll_count in range(max_scrolls):
                print(f"正在进行第 {scroll_count + 1}/{max_scrolls} 次向下滚动...")
                page.mouse.wheel(0, 2500)
                time.sleep(2.5) # 给浏览器 2.5 秒时间去请求和渲染新 DOM 节点

                # 提取当前视口内所有的 Pin 卡片
                pins = page.locator('[data-test-id="pin"]').all()
                
                for pin in pins:
                    # -- 提取 URL 与 ID 进行去重 --
                    link_loc = pin.locator('a[href^="/pin/"]')
                    if link_loc.count() == 0:
                        continue
                    
                    href = link_loc.first.get_attribute('href')
                    if not href:
                        continue
                        
                    pin_id = href.split('/')[2] if len(href.split('/')) > 2 else "unknown"
                    if pin_id in seen_ids:
                        continue # 如果这个卡片已经抓过，直接跳过
                        
                    seen_ids.add(pin_id)
                    full_url = f"https://kr.pinterest.com{href}"

                    # -- 提取封面图 --
                    img_loc = pin.locator('img')
                    img_src = img_loc.first.get_attribute('src') if img_loc.count() > 0 else "无封面"

                    # -- 核心逻辑：特征嗅探 (分类判定) --
                    pin_type = "静态图"
                    
                    # 探测视频: 寻找包含时长 ":" 的文本层 (例如 0:15)，或者有播放图标的 aria-label
                    has_duration = pin.locator('div:has-text(":")').count() > 0
                    has_video_label = pin.locator('[aria-label*="视频"], [aria-label*="Video"]').count() > 0
                    
                    if has_duration or has_video_label:
                        pin_type = "视频"
                    else:
                        # 探测组图: 寻找包含“轮播/Carousel”的 aria-label，或特定的指示器点
                        has_carousel = pin.locator('[aria-label*="轮播"], [aria-label*="Carousel"]').count() > 0
                        if has_carousel:
                            pin_type = "组图"

                    results.append({
                        "id": pin_id,
                        "url": full_url,
                        "type": pin_type,
                        "cover": img_src
                    })

            # 3. 结果汇总输出
            print(f"\n✅ 抓取完成！共收集到 {len(results)} 个不重复的 Pin。")
            
            videos = [r for r in results if r['type'] == "视频"]
            print(f"🎉 其中包含 {len(videos)} 个视频素材！")
            
            # 打印部分视频素材的链接
            for v in videos[:5]: 
                print(f" - [ID: {v['id']}] {v['url']}")
                
            return results

        except Exception as e:
            print(f"❌ 运行发生错误: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    # 测试你的中古风视频搜索链接
    test_url = "https://kr.pinterest.com/search/pins/?q=%E4%B8%AD%E5%8F%A4%E9%A3%8E%E8%A7%86%E9%A2%91"
    
    # 执行抓取，设置滚动 4 次
    scraped_data = scrape_pinterest_search(test_url, max_scrolls=4)