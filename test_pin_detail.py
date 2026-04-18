"""测试：从单个 pin 详情页提取 saves 和 comments"""

from playwright.sync_api import sync_playwright
import json

def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://localhost:9222')
        contexts = browser.contexts
        if not contexts:
            print("没有找到浏览器上下文")
            return

        context = contexts[0]
        page = context.new_page()

        # 测试一个具体的 pin
        test_url = "https://kr.pinterest.com/pin/140807925842921055/"
        print(f"正在访问: {test_url}")

        try:
            page.goto(test_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"加载警告: {e}")

        import time
        time.sleep(5)

        # 提取完整的 pin 数据结构
        pin_data = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script:not([src])');

                for (const script of scripts) {
                    const content = script.textContent;
                    if (content.includes('initialReduxState') && content.includes('pins')) {
                        try {
                            const data = JSON.parse(content);
                            if (data.initialReduxState && data.initialReduxState.pins) {
                                const pins = data.initialReduxState.pins;

                                for (const [pinId, pin] of Object.entries(pins)) {
                                    const aggData = pin.aggregated_pin_data || {};

                                    return {
                                        pinId: pinId,
                                        title: pin.grid_title || pin.title || '',
                                        // 所有可能的计数字段
                                        saves: aggData.aggregated_stats?.saves || 0,
                                        comment_count: aggData.comment_count || 0,
                                        repin_count: pin.repin_count,
                                        favorite_user_count: pin.favorite_user_count,
                                        reaction_counts: pin.reaction_counts,
                                        share_count: pin.share_count,
                                        // 完整的 aggregated_pin_data
                                        aggregated_pin_data: aggData
                                    };
                                }
                            }
                        } catch (e) {
                            return { error: 'JSON parse error: ' + e.message };
                        }
                    }
                }

                return { error: 'No pin data found in any script' };
            }
        """)

        print("\n" + "=" * 50)
        print("Pin 数据:")
        print("=" * 50)
        print(json.dumps(pin_data, indent=2, ensure_ascii=False))

        page.close()
        browser.close()

if __name__ == '__main__':
    main()
