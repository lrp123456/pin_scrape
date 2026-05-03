"""房天下爬虫 - 备案名转宣传名 (Playwright 版)

第二阶段：将天津住建委的备案名转换为房天下的宣传名

关键发现：
1. 房天下对纯 HTTP 请求返回滑块验证码，必须用浏览器访问
2. 房天下的搜索引擎已做"备案名 → 宣传名"的隐式映射
3. 搜索结果列表页（#newhouse_loupan_list 容器内）的第一个 .nlcd_name 就是最佳匹配
4. 无需进入详情页做别名校验
"""

import re
import sys
import time
import random
import json
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright, Page


@dataclass
class NameMapping:
    record_name: str
    promo_name: str
    fang_url: str
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


class FangScraper:
    SEARCH_BASE = "https://tj.newhouse.fang.com/house/s/a9"

    def __init__(self, page: Page = None, headless: bool = True,
                 debug: bool = False, cdp_endpoint: str = None,
                 delay: float = 3.0):
        self.external_page = page
        self.headless = headless
        self.debug = debug
        self.cdp_endpoint = cdp_endpoint
        self.delay = delay

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def start(self):
        if self.external_page:
            self._page = self.external_page
            return

        self._playwright = sync_playwright().start()
        if self.cdp_endpoint:
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_endpoint)
            self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        else:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context(viewport={"width": 1920, "height": 1080})
            self._page = self._context.new_page()
        self._page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

    def close(self):
        if not self.external_page:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        self._page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def convert_names(self, record_names: List[str]) -> List[NameMapping]:
        results = []
        total = len(record_names)

        invalid_keywords = ["公司名称", "许可证号", "项目坐落", "项目名称", "用途", "销售面积", "操作"]
        filtered_names = []
        for name in record_names:
            if not name or name.isdigit():
                continue
            is_invalid = False
            for keyword in invalid_keywords:
                if keyword in name:
                    is_invalid = True
                    break
            if not is_invalid:
                filtered_names.append(name)

        if len(filtered_names) != len(record_names):
            print(f"[房天下] 过滤后: {len(filtered_names)}/{len(record_names)} 个有效备案名")

        for i, name in enumerate(filtered_names):
            print(f"[房天下] [{i+1}/{len(filtered_names)}] 正在转换: {name}")

            try:
                mapping = self._search_and_extract(name)
                if mapping:
                    results.append(mapping)
                    print(f"  ✓ 宣传名: {mapping.promo_name} (置信度: {mapping.confidence:.0%})")
                else:
                    print(f"  ✗ 未找到匹配")
                    results.append(NameMapping(
                        record_name=name,
                        promo_name="",
                        fang_url="",
                        confidence=0.0,
                    ))
            except Exception as e:
                print(f"  ✗ 转换失败: {e}")
                results.append(NameMapping(
                    record_name=name,
                    promo_name="",
                    fang_url="",
                    confidence=0.0,
                ))

            if i < total - 1:
                time.sleep(random.uniform(self.delay, self.delay + 2))

        return results

    def _search_and_extract(self, record_name: str) -> Optional[NameMapping]:
        # 先用原始名称搜索
        mapping = self._do_search(record_name)
        if mapping:
            return mapping

        # 原始名称搜索失败，尝试简化名称
        simplified = self._simplify_name(record_name)
        if simplified and simplified != record_name:
            print(f"  → 尝试简化名称: '{record_name}' → '{simplified}'")
            mapping = self._do_search(simplified)
            if mapping:
                mapping.record_name = record_name
                return mapping

        # 简化名称也失败，尝试去掉常见后缀
        core = self._extract_core_name(record_name)
        if core and core != record_name and core != simplified:
            print(f"  → 尝试核心名称: '{record_name}' → '{core}'")
            mapping = self._do_search(core)
            if mapping:
                mapping.record_name = record_name
                return mapping

        print(f"  [DEBUG] 未找到匹配的楼盘")
        return None

    def _do_search(self, search_name: str, max_attempts: int = 3) -> Optional[NameMapping]:
        """执行单次搜索并提取结果"""
        encoded = self._url_encode(search_name)
        search_url = f"{self.SEARCH_BASE}{encoded}/?xf_source={encoded}"
        print(f"  [DEBUG] 搜索URL: {search_url}")

        for attempt in range(max_attempts):
            if attempt > 0:
                print(f"  [DEBUG] 第 {attempt + 1} 次重试...")
                time.sleep(random.uniform(3, 5))

            try:
                self._page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                self._page.wait_for_selector("#newhouse_loupan_list", timeout=10000)
            except Exception as e:
                print(f"  [DEBUG] 页面加载失败: {e}")
                if self.debug:
                    self._save_debug_screenshot(search_name, attempt)
                continue

            if self.debug:
                self._save_debug_html(search_name, attempt)

            candidates = self._page.evaluate("""() => {
                const container = document.getElementById('newhouse_loupan_list');
                if (!container) return [];
                const elems = container.querySelectorAll('.nlcd_name a');
                return Array.from(elems).map(a => ({
                    href: a.href,
                    text: a.textContent.trim()
                })).filter(item => item.text && item.href);
            }""")

            print(f"  [DEBUG] 找到 {len(candidates)} 个候选楼盘")

            if candidates and len(candidates) > 0:
                best = candidates[0]
                promo_name = best["text"]
                link = best.get("href", "")

                confidence = self._calc_confidence(search_name, promo_name)
                confidence = max(confidence, 0.8)
                print(f"  [DEBUG] 匹配成功: {search_name} -> {promo_name} (置信度: {confidence:.0%})")
                return NameMapping(
                    record_name=search_name,
                    promo_name=promo_name,
                    fang_url=link,
                    confidence=confidence,
                )

            # 检查是否遇到验证码
            body_text = self._page.content()
            if "验证码" in body_text or "访问受限" in body_text or "slider" in body_text:
                print(f"  [DEBUG] 检测到反爬限制，等待后重试...")
                time.sleep(random.uniform(5, 10))
                continue

            # 没有候选且无验证码，说明确实搜不到，直接跳出
            break

        return None

    def _simplify_name(self, name: str) -> str:
        """简化备案名，去除配建、楼号等后缀

        例如：
        - "潼锦苑1、2及配建一、3及配建二、4及配建三" → "潼锦苑"
        - "映荷苑1号楼" → "映荷苑"
        - "春风雅筑3号楼、4号楼" → "春风雅筑"
        """
        if not name:
            return name

        cleaned = name

        # 删除"X及配建X"模式
        cleaned = re.sub(r'[\d、]*\d+及配建[一二三四五六七八九十]+', '', cleaned).strip()

        # 删除"号楼"及其前面的数字和分隔符
        if '号楼' in cleaned:
            prefix = cleaned.split('号楼')[0]
            cleaned = re.sub(r'[\d、,，\-]+$', '', prefix).strip()

        # 删除尾部纯数字
        cleaned = re.sub(r'\d+$', '', cleaned).strip()

        # 删除末尾标点
        cleaned = re.sub(r'[、,，\s]+$', '', cleaned).strip()

        return cleaned if cleaned else name

    def _extract_core_name(self, name: str) -> str:
        """提取核心名称，去掉常见后缀

        例如：
        - "嘉丰花苑" → "嘉丰"
        - "格调林泉西苑" → "格调林泉"
        - "枫丹上苑" → "枫丹"
        """
        if not name:
            return name

        core = name

        # 去掉常见后缀（从长到短匹配）
        suffixes = [
            '花苑', '家园', '名邸', '雅居', '华庭', '上苑', '嘉园',
            '星苑', '云园', '锦园', '兰苑', '竹苑', '梅苑', '菊苑',
            '新苑', '西苑', '东苑', '南苑', '北苑',
            '花园', '公寓', '公馆', '府邸', '华府', '学府',
            '小镇', '新城', '壹号', '壹品',
            '苑', '园', '庭', '邸', '府', '城', '居', '筑', '院',
            '里', '坊', '湾', '台', '阁', '轩', '庐', '庄',
        ]

        for suffix in suffixes:
            if core.endswith(suffix) and len(core) > len(suffix) + 1:
                core = core[:-len(suffix)]
                break

        return core if core else name

    def _calc_confidence(self, record_name: str, promo_name: str) -> float:
        if not record_name or not promo_name:
            return 0.0
        r = record_name.lower()
        p = promo_name.lower()
        if r in p or p in r:
            return 1.0
        common = set(r) & set(p)
        total = set(r) | set(p)
        if total:
            ratio = len(common) / len(total)
            return max(ratio, 0.3)
        return 0.3

    def _url_encode(self, text: str) -> str:
        try:
            return urllib.parse.quote(text.encode("utf-8"))
        except Exception:
            return urllib.parse.quote(text)

    def _save_debug_html(self, record_name: str, attempt: int):
        if not self.debug:
            return
        safe_name = re.sub(r"[\\/:*?\"<>|]", "_", record_name)[:30]
        debug_dir = Path("logs/debug/fang") / safe_name
        debug_dir.mkdir(parents=True, exist_ok=True)
        try:
            html = self._page.content()
            with open(debug_dir / f"search_{attempt}.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  [DEBUG] 已保存搜索页调试文件到 {debug_dir}/")
        except Exception:
            pass

    def _save_debug_screenshot(self, record_name: str, attempt: int):
        if not self.debug:
            return
        safe_name = re.sub(r"[\\/:*?\"<>|]", "_", record_name)[:30]
        debug_dir = Path("logs/debug/fang") / safe_name
        debug_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._page.screenshot(path=str(debug_dir / f"screenshot_{attempt}.png"))
        except Exception:
            pass

    def save_results(self, mappings: List[NameMapping], output_path: str):
        valid = [m for m in mappings if m.promo_name]
        failed = [m for m in mappings if not m.promo_name]

        data = {
            "source": "房天下",
            "total_input": len(mappings),
            "success": len(valid),
            "failed": len(failed),
            "mappings": [m.to_dict() for m in mappings],
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[房天下] 结果已保存: {output_path}")
        print(f"  成功: {len(valid)}, 失败: {len(failed)}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="房天下备案名→宣传名转换")
    parser.add_argument("--input", required=True, help="住建委JSON输入文件")
    parser.add_argument("--output", default="output/fang_name_mapping.json", help="输出文件")
    parser.add_argument("--connect", action="store_true")
    parser.add_argument("--cdp-endpoint", default="http://localhost:9222")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--delay", type=float, default=3.0, help="请求间隔(秒)")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    record_names = [p["clean_name"] for p in data.get("projects", [])]
    print(f"[房天下] 读取到 {len(record_names)} 个备案名")

    with FangScraper(
        headless=not args.debug,
        debug=args.debug,
        cdp_endpoint=args.cdp_endpoint if args.connect else None,
        delay=args.delay,
    ) as scraper:
        mappings = scraper.convert_names(record_names)
        scraper.save_results(mappings, args.output)


if __name__ == "__main__":
    main()
