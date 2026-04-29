"""
天津住建委分页机制诊断脚本

用法：
1. 先运行此脚本，它会打开浏览器并访问住建委网站
2. 在打开的浏览器中，手动点击"下一页"按钮
3. 观察控制台输出，看脚本能否捕获到分页事件
4. 同时可以打开浏览器开发者工具(F12)，查看分页元素的HTML结构

这个脚本会：
- 监听所有网络请求（看是否有Ajax分页API）
- 在iframe内搜索所有可点击元素
- 打印iframe的完整HTML（用于分析）
"""

import time
import json
from playwright.sync_api import sync_playwright

URL = "https://zfcxjs.tj.gov.cn/ggfw_70/xxcx/spfxsxk/2025nxsxk/"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        
        # 拦截所有请求，寻找分页API
        def handle_route(route, request):
            url = request.url
            if "page" in url.lower() or "list" in url.lower() or "api" in url.lower():
                print(f"[网络请求] {request.method} {url[:120]}")
            route.continue_()
        
        page.route("**/*", handle_route)
        
        print("="*60)
        print("正在打开住建委网站...")
        print("="*60)
        
        page.goto(URL, wait_until="networkidle", timeout=60000)
        time.sleep(5)
        
        # 分析所有iframe
        frames = page.frames
        print(f"\n检测到 {len(frames)} 个frame")
        
        for i, frame in enumerate(frames):
            print(f"\n--- Frame {i} ---")
            print(f"URL: {frame.url}")
            
            # 在iframe内查找所有可能的分页相关元素
            elements = frame.evaluate("""() => {
                const results = [];
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    const text = el.textContent ? el.textContent.trim() : '';
                    const cls = el.className || '';
                    const id = el.id || '';
                    
                    // 查找可能的分页相关元素
                    if (text === '下一页' || text === '›' || text === '»' || 
                        text === '上一页' || text === '首页' || text === '末页' ||
                        /^\\d+$/.test(text) ||  // 纯数字页码
                        cls.includes('page') || cls.includes('laypage') || 
                        cls.includes('pagination') || cls.includes('pager') ||
                        id.includes('page') || id.includes('pagination')) {
                        results.push({
                            tag: el.tagName,
                            text: text,
                            className: cls,
                            id: id,
                            href: el.href || '',
                            onclick: el.getAttribute('onclick') || '',
                            dataPage: el.getAttribute('data-page') || el.getAttribute('page') || ''
                        });
                    }
                }
                return results;
            }""")
            
            if elements:
                print(f"找到 {len(elements)} 个分页相关元素:")
                for j, el in enumerate(elements[:20]):  # 只显示前20个
                    print(f"  [{j}] <{el['tag']}> text='{el['text']}' class='{el['className']}' id='{el['id']}'")
                    if el['href']:
                        print(f"      href={el['href']}")
                    if el['onclick']:
                        print(f"      onclick={el['onclick']}")
                    if el['dataPage']:
                        print(f"      data-page={el['dataPage']}")
            else:
                print("未找到分页相关元素")
            
            # 保存iframe的HTML用于分析
            try:
                html = frame.content()
                with open(f"debug_frame_{i}.html", "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"Frame {i} 的HTML已保存到 debug_frame_{i}.html")
            except Exception as e:
                print(f"保存HTML失败: {e}")
        
        print("\n" + "="*60)
        print("诊断完成！")
        print("请检查：")
        print("1. 上面的输出中是否有分页按钮信息")
        print("2. debug_frame_*.html 文件中的HTML结构")
        print("3. 浏览器开发者工具(F12)中的Elements面板")
        print("="*60)
        print("\n按 Enter 键关闭浏览器...")
        input()
        
        browser.close()

if __name__ == "__main__":
    main()
