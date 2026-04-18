"""输出处理"""

import json
from datetime import datetime
from pathlib import Path
from typing import List

from shared.models import Pin


def save_json(
    pins: List[Pin], filepath: str, query: str = "", filtered_count: int = 0
) -> None:
    """
    保存 Pin 数据为 JSON 文件

    Args:
        pins: Pin 列表
        filepath: 输出文件路径
        query: 搜索关键词
        filtered_count: 筛选后的数量
    """
    output_path = Path(filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 统计主 pin 和相似推荐数量
    main_pins = sum(1 for pin in pins if pin.source == "main")
    similar_pins = len(pins) - main_pins

    data = {
        "query": query,
        "total_pins": len(pins),
        "main_pins": main_pins,
        "similar_pins": similar_pins,
        "filtered_pins": filtered_count,
        "timestamp": datetime.now().isoformat(),
        "pins": [pin.to_dict() for pin in pins],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"数据已保存到: {filepath}")


def save_filtered_json(pins: List[Pin], filepath: str, query: str = ""):
    """
    保存筛选后的 Pin 数据

    Args:
        pins: 筛选后的 Pin 列表
        filepath: 输出文件路径
        query: 搜索关键词
    """
    output_path = Path(filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "query": query,
        "total_pins": len(pins),
        "timestamp": datetime.now().isoformat(),
        "pins": [pin.to_dict() for pin in pins],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"筛选数据已保存到: {filepath}")


def save_all_pins_json(
    all_pins: List[Pin], qualified_pins: List[Pin], filepath: str, query: str = ""
) -> None:
    """
    保存所有 Pin 数据，但统计显示达标数量

    Args:
        all_pins: 所有收集的 Pin 列表（包括不达标）
        qualified_pins: 达标的 Pin 列表
        filepath: 输出文件路径
        query: 搜索关键词
    """
    output_path = Path(filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 统计
    qualified_count = len(qualified_pins)
    explored_count = len(all_pins) - qualified_count

    data = {
        "query": query,
        "total_pins": qualified_count,  # 总数显示达标数量
        "qualified_pins": qualified_count,
        "explored_pins": explored_count,
        "all_pins_count": len(all_pins),
        "timestamp": datetime.now().isoformat(),
        "pins": [pin.to_dict() for pin in all_pins],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(
        f"完整数据已保存到: {filepath} (达标: {qualified_count}, 探索: {explored_count})"
    )
