"""天津住宅户型图数据持久化模块

负责维护已爬取的小区数据，避免重复爬取，支持增量更新。
存储格式: JSON (程序读写) + CSV/Markdown (用户查看)

数据结构:
{
  "version": "1.0",
  "last_updated": "2026-04-24T14:00:00",
  "projects": {
    "映荷苑": {
      "record_name": "映荷苑",
      "promo_name": "映荷雅苑",
      "promo_name_confidence": 0.95,
      "fang_url": "https://...",
      "floor_plans": [
        {
          "plan_name": "A户型",
          "room_type": "3室2厅",
          "area": "120",
          "image_url": "https://...",
          "local_path": "...",
          "downloaded": true
        }
      ],
      "last_scraped_at": "2026-04-24T14:00:00",
      "status": "completed"
    }
  }
}

状态说明:
- pending: 刚发现备案名
- name_converted: 已转换宣传名
- completed: 已下载户型图
- failed: 处理失败
"""

import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class ProjectStorage:
    """小区数据存储管理器"""

    def __init__(self, json_path: str = "output/tianjin/storage.json"):
        self.json_path = Path(json_path)
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if self.json_path.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "projects" in data:
                    return data
            except Exception:
                pass
        return {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "projects": {},
        }

    def _save(self):
        self._data["last_updated"] = datetime.now().isoformat()
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _get_project(self, record_name: str) -> dict:
        key = record_name.strip()
        if key not in self._data["projects"]:
            self._data["projects"][key] = {
                "record_name": key,
                "promo_name": "",
                "promo_name_confidence": 0.0,
                "fang_url": "",
                "floor_plans": [],
                "last_scraped_at": "",
                "status": "pending",
            }
        return self._data["projects"][key]

    def is_completed(self, record_name: str) -> bool:
        proj = self._data["projects"].get(record_name.strip())
        return proj is not None and proj.get("status") == "completed"

    def exists(self, record_name: str) -> bool:
        return record_name.strip() in self._data["projects"]

    def is_pending(self, record_name: str) -> bool:
        proj = self._data["projects"].get(record_name.strip())
        return proj is None or proj.get("status") == "pending"

    def get_pending_names(self) -> List[str]:
        return [
            name for name, proj in self._data["projects"].items()
            if proj.get("status") == "pending"
        ]

    def get_names_without_promo(self) -> List[str]:
        return [
            name for name, proj in self._data["projects"].items()
            if proj.get("status") == "pending" and not proj.get("promo_name")
        ]

    def add_record_names(self, names: List[str]):
        for name in names:
            self._get_project(name)
        self._save()
        print(f"[存储] 已添加 {len(names)} 个备案名，当前共 {len(self._data['projects'])} 个项目")

    def update_promo_name(self, record_name: str, promo_name: str,
                          confidence: float = 0.0, fang_url: str = ""):
        if not promo_name:
            return
        proj = self._get_project(record_name)
        proj["promo_name"] = promo_name
        proj["promo_name_confidence"] = confidence
        proj["fang_url"] = fang_url
        if proj["status"] == "pending":
            proj["status"] = "name_converted"
        proj["last_scraped_at"] = datetime.now().isoformat()
        self._save()

    def add_floor_plans(self, record_name: str, plans: List[dict]):
        if not plans:
            return
        proj = self._get_project(record_name)
        existing_urls = {p.get("image_url") for p in proj["floor_plans"]}
        added = 0
        for plan in plans:
            url = plan.get("image_url", "")
            if url and url not in existing_urls:
                proj["floor_plans"].append(plan)
                existing_urls.add(url)
                added += 1
        if added > 0:
            proj["status"] = "completed"
            proj["last_scraped_at"] = datetime.now().isoformat()
            self._save()
            print(f"[存储] {record_name}: 新增 {added} 个户型图")

    def update_download_status(self, record_name: str, image_url: str,
                               local_path: str, downloaded: bool = True):
        proj = self._data["projects"].get(record_name.strip())
        if not proj:
            return
        for plan in proj.get("floor_plans", []):
            if plan.get("image_url") == image_url:
                plan["local_path"] = local_path
                plan["downloaded"] = downloaded
                break
        self._save()

    def export_csv(self, csv_path: str) -> str:
        path = Path(csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for name, proj in sorted(self._data["projects"].items()):
            base = {
                "备案名": proj.get("record_name", ""),
                "宣传名": proj.get("promo_name", ""),
                "转换置信度": proj.get("promo_name_confidence", 0.0),
                "房天下链接": proj.get("fang_url", ""),
                "户型图数量": len(proj.get("floor_plans", [])),
                "状态": proj.get("status", ""),
                "最后更新": proj.get("last_scraped_at", ""),
            }
            plans = proj.get("floor_plans", [])
            if plans:
                for plan in plans:
                    row = base.copy()
                    row.update({
                        "户型名称": plan.get("plan_name", ""),
                        "房型": plan.get("room_type", ""),
                        "面积": plan.get("area", ""),
                        "图片链接": plan.get("image_url", ""),
                        "本地路径": plan.get("local_path", ""),
                        "已下载": "是" if plan.get("downloaded") else "否",
                        "来源": plan.get("source", "3vjia"),
                    })
                    rows.append(row)
            else:
                rows.append(base)

        if not rows:
            print(f"[存储] 无数据可导出")
            return ""

        fieldnames = [
            "备案名", "宣传名", "转换置信度", "房天下链接",
            "户型名称", "房型", "面积", "图片链接", "本地路径", "已下载", "来源",
            "户型图数量", "状态", "最后更新",
        ]

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"[存储] CSV已导出: {path}")
        return str(path)

    def export_markdown(self, md_path: str) -> str:
        path = Path(md_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        lines.append("# 天津住宅户型图爬取结果\n")
        lines.append(f"最后更新: {self._data.get('last_updated', '')}\n")
        lines.append("---\n")

        for name, proj in sorted(self._data["projects"].items()):
            status = proj.get("status", "pending")
            status_icon = {"completed": "✅", "name_converted": "🔄", "pending": "⏳", "failed": "❌"}.get(status, "❓")

            lines.append(f"\n## {status_icon} {proj.get('record_name', name)}\n")

            promo = proj.get("promo_name", "")
            if promo:
                lines.append(f"- 宣传名: **{promo}** (置信度: {proj.get('promo_name_confidence', 0):.0%})\n")
                fang_url = proj.get("fang_url", "")
                if fang_url:
                    lines.append(f"- 房天下: [{fang_url}]({fang_url})\n")
            else:
                lines.append("- 宣传名: 未转换\n")

            plans = proj.get("floor_plans", [])
            if plans:
                lines.append(f"- 户型图: {len(plans)} 个\n")
                lines.append("\n| 户型 | 房型 | 面积 | 来源 | 链接 | 状态 |\n")
                lines.append("|------|------|------|------|------|------|\n")
                for plan in plans:
                    p_name = plan.get("plan_name", "")
                    r_type = plan.get("room_type", "")
                    area = plan.get("area", "")
                    source = plan.get("source", "3vjia")
                    url = plan.get("image_url", "")
                    downloaded = "✅ 已下载" if plan.get("downloaded") else "⬜ 未下载"
                    link = f"[查看]({url})" if url else ""
                    lines.append(f"| {p_name} | {r_type} | {area} | {source} | {link} | {downloaded} |\n")
            else:
                lines.append("- 户型图: 无\n")

            lines.append(f"- 状态: {status} | 最后更新: {proj.get('last_scraped_at', '')}\n")

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        print(f"[存储] Markdown已导出: {path}")
        return str(path)

    def get_stats(self) -> dict:
        projects = self._data["projects"]
        total = len(projects)
        completed = sum(1 for p in projects.values() if p.get("status") == "completed")
        name_converted = sum(1 for p in projects.values() if p.get("status") == "name_converted")
        pending = sum(1 for p in projects.values() if p.get("status") == "pending")
        total_plans = sum(len(p.get("floor_plans", [])) for p in projects.values())
        downloaded = sum(
            1 for p in projects.values()
            for plan in p.get("floor_plans", [])
            if plan.get("downloaded")
        )
        return {
            "total_projects": total,
            "completed": completed,
            "name_converted": name_converted,
            "pending": pending,
            "total_plans": total_plans,
            "downloaded": downloaded,
        }

    def print_stats(self):
        stats = self.get_stats()
        print("\n[存储] 当前数据状态:")
        print(f"  总项目数: {stats['total_projects']}")
        print(f"  已完成: {stats['completed']} (含户型图)")
        print(f"  已转名: {stats['name_converted']} (无户型图)")
        print(f"  待处理: {stats['pending']}")
        print(f"  户型图总数: {stats['total_plans']}")
        print(f"  已下载: {stats['downloaded']}")
