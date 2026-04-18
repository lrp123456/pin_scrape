"""
Pinterest爬取逻辑模拟测试

模拟场景：
1. 搜索页有6个pin
2. 随机点击进入详情页
3. 详情页有：主pin数据 + 相似推荐
4. 贪心爬坡：点击相似推荐对比数据，更高则采用
5. 确保不重复统计
"""

import random
from typing import Dict, List, Set
from dataclasses import dataclass

@dataclass
class Pin:
    """模拟Pin数据"""
    id: str
    saves: int
    title: str
    is_main: bool = False  # 是否是主pin
    
    def __repr__(self):
        return f"Pin({self.id}, saves={self.saves})"


class PinterestSimulator:
    """Pinterest爬取模拟器"""
    
    def __init__(self):
        # 创建模拟数据
        self.all_pins: Dict[str, Pin] = {}
        self.search_page_pins: List[str] = []
        self.similar_pins_map: Dict[str, List[str]] = {}
        
        # 初始化数据
        self._init_data()
        
        # 统计
        self.collected_pins: Dict[str, Pin] = {}
        self.visited_ids: Set[str] = set()
        self.exploration_log: List[str] = []
        
    def _init_data(self):
        """初始化模拟数据"""
        # 搜索页的6个pin
        search_pins_data = [
            ("pin_001", 10, "简约客厅"),
            ("pin_002", 25, "北欧卧室"),
            ("pin_003", 5, "现代厨房"),
            ("pin_004", 40, "日式阳台"),
            ("pin_005", 15, "工业风书房"),
            ("pin_006", 8, "田园餐厅"),
        ]
        
        for pin_id, saves, title in search_pins_data:
            self.all_pins[pin_id] = Pin(pin_id, saves, title)
            self.search_page_pins.append(pin_id)
        
        # 每个pin的相似推荐（设计不同场景）
        # pin_001: 有更高的相似推荐
        self.similar_pins_map["pin_001"] = ["sim_001_a", "sim_001_b", "sim_001_c"]
        self.all_pins["sim_001_a"] = Pin("sim_001_a", 30, "简约客厅-升级版")
        self.all_pins["sim_001_b"] = Pin("sim_001_b", 8, "简约客厅-降级版")
        self.all_pins["sim_001_c"] = Pin("sim_001_c", 50, "简约客厅-超级版")
        
        # pin_002: 没有更高的相似推荐
        self.similar_pins_map["pin_002"] = ["sim_002_a", "sim_002_b"]
        self.all_pins["sim_002_a"] = Pin("sim_002_a", 15, "北欧卧室-普通版")
        self.all_pins["sim_002_b"] = Pin("sim_002_b", 20, "北欧卧室-稍好版")
        
        # pin_003: 有多个层级更高的
        self.similar_pins_map["pin_003"] = ["sim_003_a", "sim_003_b"]
        self.all_pins["sim_003_a"] = Pin("sim_003_a", 12, "现代厨房-改进版")
        self.all_pins["sim_003_b"] = Pin("sim_003_b", 35, "现代厨房-豪华版")
        
        # pin_004: 相似推荐更低
        self.similar_pins_map["pin_004"] = ["sim_004_a", "sim_004_b"]
        self.all_pins["sim_004_a"] = Pin("sim_004_a", 25, "日式阳台-普通版")
        self.all_pins["sim_004_b"] = Pin("sim_004_b", 30, "日式阳台-稍好版")
        
        # pin_005和pin_006: 没有相似推荐
        self.similar_pins_map["pin_005"] = []
        self.similar_pins_map["pin_006"] = []
    
    def get_search_page_pins(self) -> List[str]:
        """获取搜索页的pin列表"""
        return self.search_page_pins.copy()
    
    def get_pin_details(self, pin_id: str) -> Pin:
        """获取pin详情"""
        return self.all_pins.get(pin_id)
    
    def get_similar_pins(self, pin_id: str) -> List[str]:
        """获取相似推荐"""
        return self.similar_pins_map.get(pin_id, [])
    
    def log(self, message: str):
        """记录日志"""
        self.exploration_log.append(message)
        print(message)
    
    def explore_from_entry(self, entry_pin_id: str, min_saves: int = 20, max_depth: int = 5):
        """
        从一个入口pin开始探索
        
        模拟流程：
        1. 获取入口pin详情
        2. 如果不达标，探索相似推荐
        3. 相似推荐更高则采用，继续探索
        4. 确保不重复统计
        """
        self.log(f"\n{'='*60}")
        self.log(f"从搜索页点击入口pin: {entry_pin_id}")
        self.log(f"{'='*60}")
        
        current_pin_id = entry_pin_id
        current_pin = self.get_pin_details(current_pin_id)
        depth = 0
        
        # 本页面已处理的pin（防止重复）
        processed_in_chain: Set[str] = set()
        
        while depth < max_depth:
            depth += 1
            
            # 检查是否已访问过
            if current_pin_id in self.visited_ids:
                self.log(f"  [深度{depth}] pin {current_pin_id} 已访问过，跳过")
                break
            
            # 标记为已访问
            self.visited_ids.add(current_pin_id)
            processed_in_chain.add(current_pin_id)
            
            # 获取详情
            self.log(f"  [深度{depth}] 查看pin: {current_pin_id}")
            self.log(f"    数据: {current_pin}")
            
            # 检查是否达标
            if current_pin.saves >= min_saves:
                self.log(f"    ✓ 达标! saves={current_pin.saves} >= {min_saves}")
                
                # 收集达标pin（使用dict去重）
                if current_pin_id not in self.collected_pins:
                    self.collected_pins[current_pin_id] = current_pin
                    self.log(f"    ✓ 已收集 (累计: {len(self.collected_pins)}个)")
                
                # 在达标页收集相似推荐
                self._collect_similar_from_qualified(current_pin_id)
                break
            else:
                self.log(f"    ✗ 不达标 saves={current_pin.saves} < {min_saves}")
                
                # 探索相似推荐
                similar_pins = self.get_similar_pins(current_pin_id)
                
                if not similar_pins:
                    self.log(f"    没有相似推荐，返回搜索页")
                    break
                
                self.log(f"    发现 {len(similar_pins)} 个相似推荐: {similar_pins}")
                
                # 查找未访问且saves更高的推荐
                upgraded = False
                for sim_id in similar_pins:
                    if sim_id in processed_in_chain or sim_id in self.visited_ids:
                        self.log(f"    - {sim_id}: 已访问过，跳过")
                        continue
                    
                    sim_pin = self.get_pin_details(sim_id)
                    self.log(f"    - {sim_id}: saves={sim_pin.saves}")
                    
                    if sim_pin.saves > current_pin.saves:
                        self.log(f"      → 更优! {sim_pin.saves} > {current_pin.saves}，升级")
                        current_pin_id = sim_id
                        current_pin = sim_pin
                        upgraded = True
                        break
                    else:
                        self.log(f"      → 不更优，跳过")
                
                if not upgraded:
                    self.log(f"    没有找到更优的推荐，返回搜索页")
                    break
        
        self.log(f"  本次探索完成，返回搜索页")
    
    def _collect_similar_from_qualified(self, qualified_pin_id: str):
        """在达标详情页收集相似推荐"""
        self.log(f"\n    [达标页收集] 从 {qualified_pin_id} 收集相似推荐...")
        
        # 本页面已处理的pin（Set去重）
        processed_in_page: Set[str] = set()
        
        similar_pins = self.get_similar_pins(qualified_pin_id)
        self.log(f"    发现 {len(similar_pins)} 个相似推荐")
        
        for sim_id in similar_pins:
            # 双重检查去重
            if sim_id in processed_in_page:
                self.log(f"    - {sim_id}: 本页已处理，跳过")
                continue
            
            if sim_id in self.visited_ids:
                self.log(f"    - {sim_id}: 全局已访问，跳过")
                continue
            
            processed_in_page.add(sim_id)
            self.visited_ids.add(sim_id)
            
            sim_pin = self.get_pin_details(sim_id)
            self.collected_pins[sim_id] = sim_pin
            self.log(f"    ✓ 收集 {sim_id}: saves={sim_pin.saves} (累计: {len(self.collected_pins)}个)")
    
    def run_simulation(self, num_explorations: int = 3):
        """运行模拟"""
        self.log(f"\n{'#'*60}")
        self.log(f"开始Pinterest爬取模拟")
        self.log(f"目标: 收集达标pin (min_saves=20)")
        self.log(f"{'#'*60}\n")
        
        search_pins = self.get_search_page_pins()
        self.log(f"搜索页有 {len(search_pins)} 个pin: {search_pins}")
        
        # 随机选择几个入口pin进行探索
        entry_pins = random.sample(search_pins, min(num_explorations, len(search_pins)))
        self.log(f"\n将探索 {len(entry_pins)} 个入口pin: {entry_pins}\n")
        
        for entry_pin in entry_pins:
            self.explore_from_entry(entry_pin)
        
        # 输出统计
        self.log(f"\n{'='*60}")
        self.log(f"模拟完成！统计结果")
        self.log(f"{'='*60}")
        self.log(f"总共收集: {len(self.collected_pins)} 个pin")
        self.log(f"已访问: {len(self.visited_ids)} 个pin")
        self.log(f"\n收集的pins:")
        for pin_id, pin in self.collected_pins.items():
            self.log(f"  - {pin_id}: saves={pin.saves}, {pin.title}")
        
        # 验证去重
        unique_count = len(set(self.collected_pins.keys()))
        self.log(f"\n去重验证: {unique_count} 个唯一pin (与收集数一致: {unique_count == len(self.collected_pins)})")


if __name__ == "__main__":
    # 设置随机种子以便复现
    random.seed(42)
    
    # 运行模拟
    simulator = PinterestSimulator()
    simulator.run_simulation(num_explorations=3)
    
    print("\n" + "="*60)
    print("详细探索日志:")
    print("="*60)
    for log in simulator.exploration_log:
        print(log)
