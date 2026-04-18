import re

from playwright.sync_api import sync_playwright


def extract_pin_dom_structure(url):
    print("🚀 启动浏览器，准备提取 DOM 结构...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # 使用 domcontentloaded，避免上一次的超时错误
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector('[data-test-id="pin"]', timeout=15000)
            
            print("✅ 页面加载成功，正在提取前 5 个 Pin 的结构...\n")
            
            # 获取所有 Pin 卡片
            pins = page.locator('[data-test-id="pin"]').all()
            
            html_output = "<html><body>\n"
            
            # 只提取前 5 个进行观察，避免文件太大
            for i, pin in enumerate(pins[:5], 1):
                # 获取该 Pin 的内部 HTML 源码
                inner_html = pin.inner_html()
                
                # 为了方便阅读，做一点简单的格式化
                # (实际的 HTML 是一整行，我们将标签闭合处简单换行)
                formatted_html = re.sub(r'(>)(<)', r'\1\n\2', inner_html)
                
                html_output += f"<h2>--- Pin {i} 结构 ---</h2>\n"
                # 将结构包裹在 pre 和 code 中，方便在浏览器或编辑器中查看代码
                html_output += f"<pre><code>{formatted_html}</code></pre>\n"
                html_output += "<hr>\n"
                
            html_output += "</body></html>"
            
            # 将结果写入本地文件
            output_file = "pin_structures.html"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html_output)
                
            print(f"🎉 提取成功！请在当前目录下打开文件：{output_file}")
            print("💡 建议使用 VS Code 或浏览器打开此文件，使用 Ctrl+F 搜索 'video', '时长', 'svg' 或 'aria-label'。")

        except Exception as e:
            print(f"❌ 抓取过程中发生错误: {e}")
            
        finally:
            browser.close()

if __name__ == "__main__":
    test_url = "https://kr.pinterest.com/search/pins/?q=%E4%B8%AD%E5%8F%A4%E9%A3%8E%E8%A7%86%E9%A2%91"
    extract_pin_dom_structure(test_url)