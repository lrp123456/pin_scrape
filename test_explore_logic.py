"""
测试脚本：验证 Pinterest 相似推荐探索爬取逻辑的正确性

覆盖测试：
1. _extract_pin_details_from_modal() 正确提取数据（支持 PWS JSON 和 DOM 回退）
2. _explore_similar_pins() 贪心爬山逻辑：相似推荐 saves 更高时更换主体
3. _explore_similar_pins() 达标收集与回搜页逻辑
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import MagicMock, patch, PropertyMock

# 测试数据：模拟 Pinterest 页面 __PWS_DATA__
MOCK_PWS_DATA = {
    "props": {
        "initialReduxState": {
            "pins": {
                "123456": {
                    "id": 123456,
                    "grid_title": "Modern Living Room",
                    "title": "Modern Living Room",
                    "description": "A cozy modern living room with neutral tones",
                    "aggregated_pin_data": {
                        "aggregated_stats": {"saves": 123, "comments": 10}
                    },
                    "reaction_counts": {"1": 5},
                    "pinner": {"username": "design_lover"},
                    "images": {
                        "orig": {"url": "https://i.pinimg.com/originals/abc/def.jpg"},
                        "736x": {"url": "https://i.pinimg.com/736x/abc/def.jpg"},
                    },
                },
                "222222": {
                    "id": 222222,
                    "grid_title": "Bedroom Ideas",
                    "title": "Bedroom Ideas",
                    "description": "Simple and elegant bedroom designs",
                    "aggregated_pin_data": {
                        "aggregated_stats": {"saves": 5, "comments": 2}
                    },
                    "reaction_counts": {"1": 1},
                    "pinner": {"username": "home_deco"},
                    "images": {
                        "orig": {"url": "https://i.pinimg.com/originals/xyz/111.jpg"},
                        "736x": {"url": "https://i.pinimg.com/736x/xyz/111.jpg"},
                    },
                },
                "333333": {
                    "id": 333333,
                    "grid_title": "Minimal Kitchen",
                    "title": "Minimal Kitchen",
                    "description": "Clean lines and white cabinetry",
                    "aggregated_pin_data": {
                        "aggregated_stats": {"saves": 300, "comments": 45}
                    },
                    "reaction_counts": {"1": 20},
                    "pinner": {"username": "kitchen_guru"},
                    "images": {
                        "orig": {
                            "url": "https://i.pinimg.com/originals/kitchen/001.jpg"
                        },
                        "736x": {"url": "https://i.pinimg.com/736x/kitchen/001.jpg"},
                    },
                },
            },
            "resources": {
                "PinResource": {
                    "444444": {
                        "data": {
                            "id": 444444,
                            "grid_title": "Garden Inspiration",
                            "title": "Garden Inspiration",
                            "description": "Beautiful garden layouts and plant ideas",
                            "aggregated_pin_data": {
                                "aggregated_stats": {"saves": 88, "comments": 12}
                            },
                            "reaction_counts": {},
                            "pinner": {"username": "gardener"},
                            "images": {
                                "orig": {
                                    "url": "https://i.pinimg.com/originals/garden/001.jpg"
                                }
                            },
                        }
                    }
                }
            },
        }
    }
}


def test_extract_pin_details_from_pws():
    """测试从 PWS_DATA 提取 pin 详情"""
    from scraper import PinterestScraper

    scraper = PinterestScraper(headless=True)

    # 模拟 page.evaluate 返回 PWS 格式数据
    with patch.object(scraper.page, "evaluate") as mock_eval:
        mock_eval.return_value = MOCK_PWS_DATA

        details = scraper._extract_pin_details_from_modal()

        assert details is not None, "应成功提取 pin 详情"
        assert details["id"] == "123456", (
            f"期望 id=123456, 实际得到 {details.get('id')}"
        )
        assert details["saves"] == 123, (
            f"期望 saves=123, 实际得到 {details.get('saves')}"
        )
        assert details["likes"] == 5, f"期望 likes=5, 实际得到 {details.get('likes')}"
        assert details["comments"] == 10, (
            f"期望 comments=10, 实际得到 {details.get('comments')}"
        )
        assert details["title"] == "Modern Living Room", (
            f"期望 title='Modern Living Room'"
        )
        assert "image_url" in details, "应包含 image_url 字段"
        assert "image_url_736x" in details, "应包含 image_url_736x 字段"
        print("✓ _extract_pin_details_from_modal (PWS数据) 测试通过")


def test_extract_pin_details_from_dom_fallback():
    """测试从 DOM 回退提取 pin 详情"""
    from scraper import PinterestScraper

    scraper = PinterestScraper(headless=True)

    # 模拟 PWS 为空，DOM 有数据
    with patch.object(scraper.page, "evaluate") as mock_eval:
        mock_eval.return_value = None

        # 模拟 DOM 中有 title 和 save text
        dom_html = """
        <html>
          <body>
            <h1>Garden Inspiration</h1>
            <div>123 saves</div>
            <div>45 likes</div>
            <div>5 comments</div>
          </body>
        </html>
        """
        with patch.object(scraper.page, "content", return_value=dom_html):
            details = scraper._extract_pin_details_from_modal()

            assert details is not None, "DOM回退应提取到数据"
            assert details["title"] == "Garden Inspiration", (
                f"期望 title='Garden Inspiration', 实际得到 {details.get('title')}"
            )
            assert details["saves"] == 123, (
                f"期望 saves=123, 实际得到 {details.get('saves')}"
            )
            assert details["likes"] == 45, (
                f"期望 likes=45, 实际得到 {details.get('likes')}"
            )
            assert details["comments"] == 5, (
                f"期望 comments=5, 实际得到 {details.get('comments')}"
            )
            print("✓ _extract_pin_details_from_modal (DOM回退) 测试通过")


def test_explore_similar_pins_greedy_upgrade():
    """测试贪心爬山：相似推荐 saves 更高时更换主体"""
    from scraper import PinterestScraper

    scraper = PinterestScraper(headless=True)

    # 模拟场景：
    # 1. 进入 pin 123 (saves=10)
    # 2. 有两个相似推荐：pin 222(saves=5, 更差) 和 pin 333(saves=300, 更好)
    # 期望：选择 pin 333 升级，并爬取其数据

    call_log = []

    def mock_get_search_page_pin_ids():
        return ["123"]

    def mock_click_and_wait(pin_id, delay_range):
        call_log.append(f"click:{pin_id}")

    def mock_extract_current():
        # 第一次提取返回 pin 123 的数据
        if "123" not in call_log:
            return {
                "id": "123",
                "saves": 10,
                "title": "Pin 123",
                "description": "Desc1",
                "comments": 1,
            }
        # 之后提取更高saves的数据
        return {
            "id": "333",
            "saves": 300,
            "title": "Pin 333",
            "description": "Desc3",
            "comments": 45,
        }

    def mock_find_similar():
        # 首次调用（针对pin123）返回 pin222 和 pin333
        # 第二次调用（针对pin333）返回空
        if len(call_log) == 1:  # 第一次点击的是123
            return [{"id": "222", "href": "#"}, {"id": "333", "href": "#"}]
        return []

    def mock_click_similar(similar_id):
        call_log.append(f"click_similar:{similar_id}")

    def mock_go_back():
        call_log.append("go_back")

    with patch.object(
        scraper, "_get_search_page_pin_ids", mock_get_search_page_pin_ids
    ):
        with patch.object(
            scraper, "_extract_pin_details_from_modal", side_effect=mock_extract_current
        ):
            with patch.object(
                scraper, "_find_similar_pins_in_modal", side_effect=mock_find_similar
            ):
                with patch.object(scraper.page, "query_selector") as mock_selector:
                    mock_selector.return_value = MagicMock()
                    with patch.object(
                        scraper.page, "go_back", side_effect=mock_go_back
                    ):
                        with patch("time.sleep"):
                            with patch.object(scraper, "_navigate_back_to_search"):
                                with patch.object(scraper.progress_callback):
                                    collected = scraper._explore_similar_pins(
                                        target_count=1, min_saves=50
                                    )

    # 验证：应收集到 pin 333 (saves=300 >= 50) 且 pin 222 (saves=5 < 50) 被跳过
    collected_ids = [p["id"] for p in collected]
    assert "333" in collected_ids, f"应收集到达标pin 333，当前收集 {collected_ids}"
    assert "123" not in collected_ids, f"不应收集不达标pin 123"
    print(f"✓ 贪心爬山测试通过：最终收集到 {collected_ids}")


if __name__ == "__main__":
    test_extract_pin_details_from_pws()
    test_extract_pin_details_from_dom_fallback()
    test_explore_similar_pins_greedy_upgrade()
    print("\n✅ 所有测试通过！")
