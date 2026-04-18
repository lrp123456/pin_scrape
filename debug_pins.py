"""调试脚本：分析 Pinterest 页面上的 pin 元素结构"""

from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://localhost:9222')
        contexts = browser.contexts
        if not contexts:
            print("没有找到浏览器上下文")
            return

        page = contexts[0].pages[0]
        print(f"当前页面: {page.url}")

        # 调试：全面分析页面结构
        debug_info = page.evaluate('''
            () => {
                const info = {};

                // 1. 查找所有 pin 链接
                const pinLinks = document.querySelectorAll('a[href*="/pin/"]');
                info.pinLinksCount = pinLinks.length;
                info.pinLinks = [];
                pinLinks.forEach((link, i) => {
                    if (i < 5) {
                        info.pinLinks.push({
                            href: link.href,
                            text: link.textContent.trim().substring(0, 100)
                        });
                    }
                });

                // 2. 查找所有图片
                const images = document.querySelectorAll('img[src*="pinimg"]');
                info.imagesCount = images.length;
                info.sampleImages = [];
                images.forEach((img, i) => {
                    if (i < 3) {
                        info.sampleImages.push({
                            src: img.src,
                            alt: (img.alt || '').substring(0, 50)
                        });
                    }
                });

                // 3. 查找所有按钮
                const buttons = document.querySelectorAll('button');
                info.buttonsCount = buttons.length;
                info.sampleButtons = [];
                buttons.forEach((btn, i) => {
                    if (i < 10) {
                        const text = btn.textContent.trim().substring(0, 30);
                        const aria = btn.getAttribute('aria-label') || '';
                        if (text || aria) {
                            info.sampleButtons.push({ text, aria });
                        }
                    }
                });

                // 4. 查找 data-test-id 元素
                const testElements = document.querySelectorAll('[data-test-id]');
                info.testIds = [];
                testElements.forEach((el, i) => {
                    if (i < 20) {
                        info.testIds.push(el.getAttribute('data-test-id'));
                    }
                });

                // 5. 查找包含数字的 span（可能是 saves/comments）
                const spans = document.querySelectorAll('span');
                info.numericSpans = [];
                spans.forEach(sp => {
                    const text = sp.textContent.trim();
                    if (/^[0-9,]+k?$/.test(text) && text.length < 10) {
                        info.numericSpans.push(text);
                    }
                });

                // 6. 检查 __PWS_DATA__ 中是否有 pins
                const pwsScript = document.getElementById('__PWS_DATA__');
                if (pwsScript) {
                    try {
                        const data = JSON.parse(pwsScript.textContent);
                        info.hasPwsData = true;
                        info.pwsKeys = Object.keys(data);

                        if (data.props && data.props.initialReduxState) {
                            const state = data.props.initialReduxState;
                            info.stateKeys = Object.keys(state);

                            // 检查 pins
                            if (state.pins) {
                                info.pinsCount = Object.keys(state.pins).length;
                                // 获取第一个 pin 的 saves
                                const firstPinId = Object.keys(state.pins)[0];
                                const firstPin = state.pins[firstPinId];
                                info.firstPinKeys = Object.keys(firstPin);

                                // 提取 saves
                                if (firstPin.aggregated_pin_data) {
                                    info.firstPinAggregated = firstPin.aggregated_pin_data;
                                }
                            }
                        }
                    } catch (e) {
                        info.pwsError = e.message;
                    }
                }

                return info;
            }
        ''')

        print("\n" + "=" * 60)
        print("Pinterest 页面分析")
        print("=" * 60)

        print(f"\nPin 链接数量: {debug_info.get('pinLinksCount', 0)}")
        print(f"Pin 链接示例: {debug_info.get('pinLinks', [])}")

        print(f"\n图片数量: {debug_info.get('imagesCount', 0)}")
        print(f"图片示例: {debug_info.get('sampleImages', [])}")

        print(f"\n按钮数量: {debug_info.get('buttonsCount', 0)}")
        print(f"按钮示例: {debug_info.get('sampleButtons', [])}")

        print(f"\ndata-test-id 列表: {debug_info.get('testIds', [])}")

        print(f"\n数字 span (可能是 saves): {debug_info.get('numericSpans', [])[:10]}")

        print(f"\n__PWS_DATA__: {debug_info.get('hasPwsData', False)}")
        print(f"顶层键: {debug_info.get('pwsKeys', [])}")
        print(f"state 键: {debug_info.get('stateKeys', [])}")
        print(f"pins 数量: {debug_info.get('pinsCount', 0)}")
        print(f"第一个 pin 的键: {debug_info.get('firstPinKeys', [])}")
        print(f"第一个 pin 的 aggregated_pin_data: {debug_info.get('firstPinAggregated', {})}")

        browser.close()

if __name__ == '__main__':
    main()
