"""天津住建委商品房销售许可爬虫

第一阶段：从天津住建委网站爬取住宅项目备案名

目标URL: https://zfcxjs.tj.gov.cn/ggfw_70/xxcx/spfxsxk/2025nxsxk/
筛选条件：用途 = 住宅
处理规则：删除项目名称中的"X号楼"字样
"""

import re
import sys
import time
import random
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright


@dataclass
class ProjectRecord:
    """住建委项目记录"""
    raw_name: str          # 原始项目名称（含X号楼）
    clean_name: str        # 清理后的备案名（去掉了X号楼）
    project_no: str        # 项目编号
    developer: str         # 开发企业
    location: str          # 坐落
    usage: str             # 用途
    issue_date: str        # 发证日期
    
    def to_dict(self) -> dict:
        return asdict(self)


class TJGovScraper:
    """天津住建委爬虫"""
    
    BASE_URL = "https://zfcxjs.tj.gov.cn/ggfw_70/xxcx/spfxsxk/2025nxsxk/"
    
    def __init__(self, headless: bool = True, debug: bool = False,
                 cdp_endpoint: str = None, log_file: str = None,
                 page=None, storage=None):
        self.headless = headless
        self.debug = debug
        self.cdp_endpoint = cdp_endpoint
        self.log_file = log_file
        self._external_page = page
        self.storage = storage
        self.browser = None
        self.context = None
        self.page = page
        self._playwright = None
        self._own_browser = False

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
            self.context = self.browser.new_context(viewport={"width": 1920, "height": 1080})
            self.page = self.context.new_page()
        self._own_browser = not self.cdp_endpoint
        self.page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

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
    
    def fetch_all_residential_projects(self, max_pages: int = 100, days_limit: int = 0) -> List[ProjectRecord]:
        """获取所有住宅项目

        Args:
            max_pages: 最大翻页数
            days_limit: 只保留近N天的项目（0表示默认90天）

        Returns:
            住宅项目列表
        """
        effective_days = days_limit if days_limit > 0 else 90
        print(f"[住建委] 开始爬取住宅项目，最多翻页 {max_pages} 次，只保留近 {effective_days} 天的项目...")

        for attempt in range(3):
            try:
                self.page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(random.uniform(5, 8))
                break
            except Exception as e:
                print(f"[住建委] 页面加载失败 (尝试 {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(random.uniform(3, 6))
                else:
                    print(f"[住建委] 多次加载失败，跳过此站点")
                    return []

        if not self.page.url.startswith("https://zfcxjs.tj.gov.cn"):
            print(f"[住建委] 当前页面URL异常: {self.page.url}")
            return []

        self._set_date_range_on_page(effective_days)

        all_projects = []
        page_num = 1
        stopped_by_storage = False

        while page_num <= max_pages:
            print(f"[住建委] 正在处理第 {page_num} 页...")

            projects = self._extract_page_projects()
            print(f"[住建委] 第 {page_num} 页提取到 {len(projects)} 条记录")

            residential = [p for p in projects if "非住宅" not in p.usage and "住宅" in p.usage]

            if self.storage and residential:
                new_projects_on_page = []
                for p in residential:
                    if self.storage.exists(p.clean_name):
                        print(f"[住建委] 项目 '{p.clean_name}' 已存在于 storage，停止后续爬取")
                        stopped_by_storage = True
                        break
                    new_projects_on_page.append(p)
                
                all_projects.extend(new_projects_on_page)
                
                if stopped_by_storage:
                    print(f"[住建委] 第 {page_num} 页遇到已存在项目，提前终止所有后续爬取")
                    break
            else:
                all_projects.extend(residential)

            if stopped_by_storage:
                break

            has_next = self._goto_next_page()
            if not has_next:
                print("[住建委] 已到达最后一页")
                break

            page_num += 1
            time.sleep(random.uniform(2, 4))

        filtered = [p for p in all_projects if self._is_within_days(p.issue_date, effective_days)]
        print(f"[住建委] 日期过滤: 共 {len(all_projects)} 个，近 {effective_days} 天内 {len(filtered)} 个")
        all_projects = filtered

        print(f"[住建委] 爬取完成，共 {len(all_projects)} 个住宅项目")
        return all_projects
    
    def _is_within_days(self, date_str: str, days: int) -> bool:
        """判断日期是否在N天之内"""
        if not date_str:
            return True  # 没有日期信息的默认保留
        try:
            from datetime import datetime, timedelta
            # 支持格式: YYYY-MM-DD, YYYY/MM/DD
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(date_str, fmt)
                    cutoff = datetime.now() - timedelta(days=days)
                    return dt >= cutoff
                except ValueError:
                    continue
        except Exception:
            pass
        return True

    def _set_date_range_on_page(self, days: int) -> bool:
        """在网页上设置日期范围，减少爬取量"""
        from datetime import datetime, timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        print(f"[住建委] 尝试设置日期范围: {start_str} 至 {end_str}")

        try:
            frames = self.page.frames
            for frame in frames:
                try:
                    date_inputs = frame.query_selector_all('.el-date-editor input.el-input__inner')
                    if len(date_inputs) >= 2:
                        date_inputs[0].click()
                        time.sleep(0.5)
                        date_inputs[0].fill(start_str)
                        time.sleep(0.5)

                        date_inputs[1].click()
                        time.sleep(0.5)
                        date_inputs[1].fill(end_str)
                        time.sleep(0.5)

                        search_btn = frame.query_selector('button.el-button--primary:has-text("搜索")')
                        if not search_btn:
                            search_btn = frame.query_selector('button.el-button--primary span:has-text("搜索")')
                        if not search_btn:
                            search_btn = frame.query_selector('button.el-button--primary')

                        if search_btn:
                            search_btn.click()
                            print(f"[住建委] 已设置日期范围并搜索")
                            time.sleep(random.uniform(3, 5))
                            return True
                        else:
                            print(f"[住建委] [WARNING] 未找到搜索按钮")
                            return False
                except Exception:
                    continue
        except Exception as e:
            print(f"[住建委] 设置日期范围失败: {e}")
        return False

    def _extract_page_projects(self) -> List[ProjectRecord]:
        """从当前页提取项目列表"""
        projects = []
        
        try:
            if self.debug:
                debug_dir = Path("logs/debug/tj_gov")
                debug_dir.mkdir(parents=True, exist_ok=True)
                try:
                    self.page.screenshot(path=str(debug_dir / "page.png"), full_page=True, timeout=5000)
                except Exception:
                    pass
                try:
                    with open(debug_dir / "page.html", "w", encoding="utf-8") as f:
                        f.write(self.page.content())
                except Exception:
                    pass
                print(f"[住建委] [DEBUG] 已保存调试文件到 {debug_dir}/")
            
            # 检查是否有iframe（政府网站常用iframe加载表格）
            frames = self.page.frames
            if len(frames) > 1:
                print(f"[住建委] 检测到 {len(frames)} 个frame，尝试在iframe中查找...")
                for i, frame in enumerate(frames):
                    try:
                        rows = frame.query_selector_all("table tbody tr, .table tbody tr, tr")
                        if rows and len(rows) > 0:
                            print(f"[住建委] 在frame {i} 中找到 {len(rows)} 行")
                            return self._parse_rows(rows)
                    except:
                        continue
            
            # 等待表格加载（更长的超时时间）
            try:
                self.page.wait_for_selector("table, .table, .list-table, tbody tr, .layui-table, .data-list", timeout=15000)
            except Exception as e:
                print(f"[住建委] 等待表格超时，尝试直接提取... 错误: {e}")
            
            # 尝试多种可能的选择器（政府网站常见表格结构）
            selectors = [
                "table tbody tr",
                ".table tbody tr", 
                ".layui-table tbody tr",
                ".data-list .item",
                ".list-item",
                "tr",
            ]
            
            rows = []
            for selector in selectors:
                rows = self.page.query_selector_all(selector)
                if rows and len(rows) > 0:
                    print(f"[住建委] 使用选择器 '{selector}' 找到 {len(rows)} 行")
                    break
            
            if not rows:
                print("[住建委] 未找到任何数据行，尝试提取所有文本...")
                # 最后的fallback：提取页面所有文本
                text = self.page.inner_text("body")
                print(f"[住建委] [DEBUG] 页面文本前500字: {text[:500]}")
                return []
            
            return self._parse_rows(rows)
                    
        except Exception as e:
            print(f"[住建委] 提取页面失败: {e}")
            import traceback
            traceback.print_exc()
        
        return projects
    
    def _parse_rows(self, rows) -> List[ProjectRecord]:
        """解析表格行数据"""
        projects = []
        
        for row in rows:
            try:
                cells = row.query_selector_all("td.el-table__cell")
                if len(cells) < 3:
                    continue
                
                # 调试：打印第一行的所有单元格内容，帮助确定列顺序
                if len(projects) == 0 and self.debug:
                    print("[住建委] [DEBUG] 第一行单元格内容:")
                    for i, cell in enumerate(cells):
                        print(f"  [{i}] {cell.inner_text().strip()[:50]}")
                
                # 检测是否是表头行（跳过）
                # 检查所有单元格，如果包含表头关键字则跳过整行
                is_header = False
                header_keywords = ["许可证号", "项目名称", "公司名称", "项目坐落", "用途", "销售面积"]
                for cell in cells[:10]:  # 只检查前10个单元格
                    text = cell.inner_text().strip()
                    for keyword in header_keywords:
                        if keyword in text and len(text) < 20:
                            is_header = True
                            break
                    if is_header:
                        break
                
                if is_header:
                    print(f"[住建委] 跳过表头行")
                    continue
                
                # 根据实际页面结构提取列（Element UI el-table）
                # 列顺序：[0]许可证号 [1]公司名称 [2]项目坐落 [3]项目名称 [4]用途 [5]销售面积 [6]监管开户银行 [7]监管帐号 [8]发证时间 [9]操作
                raw_name = ""
                project_no = ""
                developer = ""
                location = ""
                usage = ""
                issue_date = ""

                def get_col_text(idx: int) -> str:
                    if idx < len(cells):
                        return cells[idx].inner_text().strip()
                    return ""

                project_no = get_col_text(0)
                developer = get_col_text(1)
                location = get_col_text(2)
                raw_name = get_col_text(3)
                usage = get_col_text(4)
                issue_date = get_col_text(8)
                
                # 如果没有找到项目名称，尝试备用列
                if not raw_name:
                    for i in [1, 3, 5, 7]:
                        text = get_col_text(i)
                        if len(text) > 3 and not text.isdigit():
                            raw_name = text
                            break
                
                if not raw_name:
                    continue
                
                # 清理项目名称（删除X号楼和尾部数字）
                clean_name = self._clean_project_name(raw_name)
                
                proj = ProjectRecord(
                    raw_name=raw_name,
                    clean_name=clean_name,
                    project_no=project_no,
                    developer=developer,
                    location=location,
                    usage=usage,
                    issue_date=issue_date,
                )
                projects.append(proj)
                
            except Exception as e:
                if self.debug:
                    print(f"[住建委] 解析行失败: {e}")
                continue
        
        print(f"[住建委] 成功解析 {len(projects)} 条记录")
        return projects
    
    def _get_cell_text(self, cells, index: int) -> str:
        """安全获取单元格文本"""
        try:
            if index < len(cells):
                return cells[index].inner_text().strip()
        except:
            pass
        return ""
    
    def _clean_project_name(self, name: str) -> str:
        """清理项目名称，删除X号楼字样和尾部数字

        规则：
        - 删除"号楼"及其前面的数字和分隔符
        - 删除"X及配建X"模式（如"1、2及配建一、3及配建二、4及配建三"）
        - 删除尾部数字（备案名不能以数字结尾）
        - 删除末尾标点

        例如：
        - "映荷苑1号楼" → "映荷苑"
        - "春风雅筑3号楼、4号楼" → "春风雅筑"
        - "紫棠星苑8、10、18号楼" → "紫棠星苑"
        - "格调林泉西苑1、4、5、8号楼" → "格调林泉西苑"
        - "潼锦苑1、2及配建一、3及配建二、4及配建三" → "潼锦苑"
        - "龙韵花园9" → "龙韵花园"
        - "海棠园" → "海棠园"
        """
        if not name:
            return name

        cleaned = name

        # 步骤1：删除"号楼"及其前面的数字和分隔符
        if '号楼' in cleaned:
            prefix = cleaned.split('号楼')[0]
            cleaned = re.sub(r'[\d、,，\-]+$', '', prefix).strip()

        # 步骤2：删除"X及配建X"模式
        # 匹配：数字+及配建+中文数字，前面可能有数字和顿号
        cleaned = re.sub(r'[\d、]*\d+及配建[一二三四五六七八九十]+', '', cleaned).strip()

        # 步骤3：删除尾部纯数字（备案名不能以数字结尾）
        cleaned = re.sub(r'\d+$', '', cleaned).strip()

        # 步骤4：删除末尾的标点
        cleaned = re.sub(r'[、,，\s]+$', '', cleaned).strip()

        if not cleaned:
            cleaned = name

        return cleaned
    
    def _goto_next_page(self) -> bool:
        """跳转到下一页，支持主页面和iframe内查找

        核心策略：针对 Element UI 分页组件的 button.btn-next 按钮
        该按钮位于数据iframe内，类名为 'btn-next'，disabled属性表示是否可用

        Returns:
            True-成功，False-无下一页
        """
        # 先保存当前页指纹，用于验证翻页是否成功
        fingerprint = self._get_page_fingerprint()
        if self.debug:
            print(f"[住建委] [DEBUG] 当前页指纹: {fingerprint[:80]}...")

        try:
            frames = self.page.frames

            for i, frame in enumerate(frames):
                try:
                    next_btn = frame.query_selector('button.btn-next')
                    if next_btn:
                        disabled_attr = next_btn.get_attribute('disabled')
                        cls = next_btn.get_attribute('class') or ''
                        is_disabled = disabled_attr is not None or 'disabled' in cls

                        if self.debug:
                            print(f"[住建委] [DEBUG] frame {i} 找到btn-next, disabled={is_disabled}, class={cls}")

                        if is_disabled:
                            print(f"[住建委] frame {i} 下一页已禁用，到达最后一页")
                            return False

                        next_btn.click()
                        print(f"[住建委] frame {i} 点击Element UI下一页按钮")
                        if self._wait_for_page_change(fingerprint):
                            return True
                        else:
                            print(f"[住建委] [WARNING] frame {i} 点击后内容未变化，可能翻页失败")
                except Exception as e:
                    if self.debug:
                        print(f"[住建委] [DEBUG] frame {i} CSS点击失败: {e}")
                    continue

            for i, frame in enumerate(frames):
                try:
                    result = frame.evaluate("""() => {
                        const btn = document.querySelector('button.btn-next');
                        if (!btn) return {status: 'not_found'};
                        if (btn.disabled || btn.classList.contains('disabled')) {
                            return {status: 'disabled'};
                        }
                        btn.click();
                        return {status: 'clicked'};
                    }""")
                    if result and result.get('status') == 'clicked':
                        print(f"[住建委] frame {i} JS点击Element UI下一页")
                        if self._wait_for_page_change(fingerprint):
                            return True
                    elif result and result.get('status') == 'disabled':
                        print(f"[住建委] frame {i} 下一页已禁用")
                        return False
                except Exception as e:
                    if self.debug:
                        print(f"[住建委] [DEBUG] frame {i} JS点击失败: {e}")
                    continue

            for i, frame in enumerate(frames):
                try:
                    result = frame.evaluate("""() => {
                        const allElements = document.querySelectorAll('button, a, span, li');
                        for (const el of allElements) {
                            const text = el.textContent.trim();
                            if (text === '下一页' || text === '»' || text === '›') {
                                if (el.disabled || el.classList.contains('disabled')) {
                                    return {status: 'disabled', text: text};
                                }
                                el.click();
                                return {status: 'clicked', text: text};
                            }
                        }
                        return {status: 'not_found'};
                    }""")
                    if result and result.get('status') == 'clicked':
                        print(f"[住建委] frame {i} 通过文本查找点击下一页: {result.get('text')}")
                        if self._wait_for_page_change(fingerprint):
                            return True
                    elif result and result.get('status') == 'disabled':
                        print(f"[住建委] frame {i} 下一页已禁用")
                        return False
                except Exception:
                    continue

            if self.debug:
                print("[住建委] [DEBUG] 所有翻页方式均失败，可能已到达最后一页")
            return False

        except Exception as e:
            print(f"[住建委] 翻页失败: {e}")
            return False
    
    def _get_page_fingerprint(self) -> str:
        """获取当前页面指纹（用于验证翻页是否成功）

        优先使用第一行的许可证号作为指纹，因为它具有唯一性且稳定。
        """
        try:
            frames = self.page.frames
            for frame in frames:
                try:
                    fingerprint = frame.evaluate("""() => {
                        const firstRow = document.querySelector('.el-table__body tbody tr.el-table__row');
                        if (!firstRow) return '';
                        const cells = firstRow.querySelectorAll('td.el-table__cell');
                        if (cells.length > 0) {
                            return cells[0].textContent.trim();
                        }
                        return firstRow.textContent.trim().substring(0, 100);
                    }""")
                    if fingerprint:
                        return fingerprint
                except Exception:
                    continue
            return self.page.evaluate("""() => {
                const firstRow = document.querySelector('.el-table__body tbody tr.el-table__row');
                if (!firstRow) return '';
                const cells = firstRow.querySelectorAll('td.el-table__cell');
                if (cells.length > 0) {
                    return cells[0].textContent.trim();
                }
                return firstRow.textContent.trim().substring(0, 100);
            }""")
        except Exception:
            return ""
    
    def _wait_for_page_change(self, old_fingerprint: str, max_wait: float = 10.0) -> bool:
        """等待页面内容变化，验证翻页是否成功

        iframe 内表格更新可能有延迟，增加等待时间到10秒。

        Args:
            old_fingerprint: 翻页前的页面指纹
            max_wait: 最大等待时间（秒）

        Returns:
            True-内容已变化，False-内容未变化
        """
        start = time.time()
        while time.time() - start < max_wait:
            time.sleep(2.0)
            new_fingerprint = self._get_page_fingerprint()
            if new_fingerprint and new_fingerprint != old_fingerprint:
                if self.debug:
                    print(f"[住建委] [DEBUG] 翻页成功，新指纹: {new_fingerprint[:80]}")
                return True
        if self.debug:
            print(f"[住建委] [DEBUG] 翻页后内容未变化")
        return False
    
    def deduplicate_projects(self, projects: List[ProjectRecord]) -> List[ProjectRecord]:
        """对清理后的备案名去重
        
        同一个小区的多栋楼（如映荷苑1号楼、映荷苑3号楼）
        清理后都会变成"映荷苑"，需要去重只保留一条。
        
        保留规则：
        - 按 clean_name 去重
        - 保留发证日期最新的记录
        - 合并原始名称列表（便于追溯）
        """
        from collections import defaultdict
        
        grouped = defaultdict(list)
        for p in projects:
            grouped[p.clean_name].append(p)
        
        deduped = []
        for clean_name, group in grouped.items():
            if len(group) == 1:
                deduped.append(group[0])
                continue
            
            # 同一小区多栋楼：保留发证日期最新的
            # 日期格式通常是 YYYY-MM-DD 或 YYYY/MM/DD
            latest = max(group, key=lambda p: self._parse_date(p.issue_date))
            
            # 合并所有原始名称
            all_raw_names = [g.raw_name for g in group]
            latest.raw_name = "、".join(all_raw_names)
            
            deduped.append(latest)
        
        print(f"[住建委] 去重前: {len(projects)} 条，去重后: {len(deduped)} 条")
        return deduped
    
    def _parse_date(self, date_str: str) -> str:
        """解析日期字符串，用于比较"""
        if not date_str:
            return ""
        # 统一格式：删除非数字字符
        return re.sub(r'[^\d]', '', date_str)
    
    def save_results(self, projects: List[ProjectRecord], output_path: str):
        """保存结果到JSON（自动去重）"""
        # 先对 clean_name 去重
        deduped = self.deduplicate_projects(projects)
        
        data = {
            "source": "天津住建委",
            "url": self.BASE_URL,
            "total_raw": len(projects),
            "total_deduped": len(deduped),
            "projects": [p.to_dict() for p in deduped],
        }
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[住建委] 结果已保存: {output_path}")
        print(f"  原始记录: {len(projects)}，去重后: {len(deduped)}")


def main():
    """独立测试入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="天津住建委住宅项目爬虫")
    parser.add_argument("--output", default="output/tj_gov_projects.json", help="输出文件路径")
    parser.add_argument("--max-pages", type=int, default=100, help="最大翻页数")
    parser.add_argument("--connect", action="store_true", help="连接已有浏览器")
    parser.add_argument("--cdp-endpoint", default="http://localhost:9222")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    
    with TJGovScraper(
        headless=not args.debug,
        debug=args.debug,
        cdp_endpoint=args.cdp_endpoint if args.connect else None,
    ) as scraper:
        projects = scraper.fetch_all_residential_projects(max_pages=args.max_pages)
        scraper.save_results(projects, args.output)
        
        # 打印前10个示例
        print("\n=== 前10个住宅项目 ===")
        for p in projects[:10]:
            print(f"  备案名: {p.clean_name} (原始: {p.raw_name})")
            print(f"    开发企业: {p.developer}")
            print(f"    坐落: {p.location}")
            print(f"    发证日期: {p.issue_date}")
            print()


if __name__ == "__main__":
    main()
