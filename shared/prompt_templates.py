"""Prompt 模板生成器"""


PROMPT_TEMPLATES = {
    "default": {
        "criteria": "室内空间或室内细节，风格与检索词匹配，无任何人物元素",
        "style_keywords": [],
        "negative_examples": "室外建筑、风景照、人物、人像、人体、剪影",
    },
    "原木风": {
        "criteria": "必须有显著木质元素（木地板、木家具、木饰面）、温暖自然色调、原木纹理清晰可见。不得出现任何人物形象。",
        "style_keywords": ["木质", "原木", "实木", "温暖", "自然", "木纹", "日式", "北欧"],
        "negative_examples": "金属质感、玻璃幕墙、冷色调、现代简约无木质元素、人物、人像、人体",
    },
    "轻奢": {
        "criteria": "必须有金属元素（黄铜、金色、不锈钢）、大理石材质、丝绒/皮质材质、精致细节、高级感。不得出现任何人物形象。",
        "style_keywords": ["金属", "大理石", "丝绒", "皮质", "黄铜", "金色", "高级感", "精致"],
        "negative_examples": "廉价塑料、布艺沙发、简约无装饰、田园风格、人物、人像、人体",
    },
    "奶油风": {
        "criteria": "必须有奶油色系（米白、奶咖、浅杏）、圆润线条、柔和光影、温馨治愈感。不得出现任何人物形象。",
        "style_keywords": ["奶油色", "米白", "奶咖", "圆润", "柔和", "温馨", "治愈"],
        "negative_examples": "深色系、硬朗线条、工业风、冷色调、人物、人像、人体",
    },
    "极简": {
        "criteria": "必须有极简线条、留白空间、黑白灰或单一色调、无多余装饰、功能性设计。不得出现任何人物形象。",
        "style_keywords": ["极简", "简约", "留白", "黑白灰", "线条感", "功能性"],
        "negative_examples": "繁复装饰、多彩图案、杂乱摆放、复古风格、人物、人像、人体",
    },
    "现代简约": {
        "criteria": "必须有简洁线条、中性色调、功能性家具、整洁空间。不得出现任何人物形象。",
        "style_keywords": ["简约", "现代", "线条", "中性色", "整洁", "功能"],
        "negative_examples": "复古、田园、繁复装饰、人物、人像、人体",
    },
    "法式": {
        "criteria": "必须有法式元素（石膏线、雕花、拱门、水晶灯）、优雅浪漫氛围、精致细节。不得出现任何人物形象。",
        "style_keywords": ["法式", "石膏线", "雕花", "拱门", "水晶灯", "优雅", "浪漫"],
        "negative_examples": "现代工业、极简、中式、人物、人像、人体",
    },
    "中式": {
        "criteria": "必须有中式元素（实木家具、屏风、字画、禅意、对称布局）、东方美学。不得出现任何人物形象。",
        "style_keywords": ["中式", "实木", "屏风", "禅意", "东方", "对称", "木质"],
        "negative_examples": "欧式、现代、玻璃金属、人物、人像、人体",
    },
    "工业风": {
        "criteria": "必须有工业元素（裸露砖墙、水泥、金属管道、复古灯具）、粗犷原始质感。不得出现任何人物形象。",
        "style_keywords": ["工业", "砖墙", "水泥", "金属", "复古", "粗犷"],
        "negative_examples": "温馨、奶油色、木质、精致、人物、人像、人体",
    },
}


BASE_PROMPT_TEMPLATE = """# Role
你是一个严格的视觉内容初筛引擎。你的任务是判断输入的图片是否符合特定的物理场景要求，并判断其与给定的检索词是否具备高度的视觉和语义一致性。

# Task
请观察输入的图片，并结合给定的检索词（Query）："{query}"，进行严格判定。

# Evaluation Criteria (判定标准)
1. 室内场景判定 (is_interior)：
   - 图片必须是明确的"室内空间"或"室内细节"（如客厅、卧室、室内光影、家居特写等）。
   - 如果图片主体是建筑外观（如航拍别墅、大楼外立面）、纯室外自然风景、或者是在室外拍摄的建筑全景，则必须判定为 false。
   - 即便室外建筑有透明玻璃能看到一点室内，只要主视角在室外，即为 false。

2. 人物排除 (no_human)：
   - 图片中绝对禁止出现任何人物形象（包括完整人体、人像、剪影、人物背影、人物局部如手/脚等）。
   - 禁止出现以人物为焦点的照片（即使人物很小）。
   - 仅允许纯室内空间/物品/装饰，无人居住痕迹或人物摆拍。
   - 如果检测到任何人物元素，is_interior 必须设为 false。

3. 检索词相关性 (matches_query)：
   - 图片的视觉风格、材质、元素必须与检索词高度契合。
   - 判定标准：{criteria}
   - 相关风格关键词：{keywords}
   - 排除项：{negative_examples}

# Output Format
请务必仅输出合法的 JSON 格式数据，不要包含任何额外的 markdown 代码块标记(如 ```json) 或解释性文字。

{{
  "is_interior": <布尔值, 是否为纯室内场景且无任何人物>,
  "matches_query": <布尔值, 画面元素与给定检索词是否高度相关>,
  "is_approved": <布尔值, 只有当 is_interior 和 matches_query 均为 true 时才为 true，否则为 false>,
  "reasoning": "<用一句话简述判断理由，例如：'该图为现代简约客厅，有金属大理石元素，无人物，符合轻奢风格。'>"
}}"""


COLLECTION_PROMPT_TEMPLATE = """# Role
你是一个严格的室内空间美学质量评估专家。你的任务是对已经通过初筛的图片进行深度质量评估，从室内场景判定、风格匹配度、人物排除、场景完整性四个维度进行判定。

# Task
请观察输入的图片，并结合给定的检索词（Query）："{query}"，进行严格评估。

# Evaluation Criteria (评估标准)
1. 室内场景判定 (is_interior) [布尔值]：
   - true：图片是明确的"室内空间"或"室内细节"（如客厅、卧室、浴室、走廊、室内家具特写等）
   - false：图片主体是建筑外观（航拍别墅、大楼外立面）、室外园景、纯自然风景、街道景观、建筑效果图、室外拍摄的建筑全景
   - 严格规则：哪怕建筑带有极简风格，只要主视角在室外（能看到天空、地面、建筑外墙），就必须判定为 false
   - 注意：半室内半室外的模糊场景（如走廊通向庭院、大量玻璃墙模糊室内外边界）也判定为 false

2. 风格匹配度 (style_match) [0-10分]：
   - 10分：图片风格与检索词高度契合，典型元素丰富且精致
   - 7-9分：风格明显匹配，有代表性元素
   - 4-6分：有一定关联但不够典型
   - 0-3分：风格不符或关联度极低
   - 当前检索词判定标准：{criteria}
   - 相关风格关键词：{keywords}
   - 常见误风格（应打低分）：{negative_examples}

3. 人物排除 (has_human) [布尔值]：
   - true：图片中出现任何人物形象（完整人体、人像、剪影、背影、局部如手/脚）
   - false：纯室内空间，无任何人物元素
   - 注意：即使是远处的小人影、人物倒影、人形模特也应判定为 true

4. 场景完整性 (scene_completeness) [0-10分]：
   - 10分：完整空间展示（如客厅全景、卧室整体、餐厅全貌），能看清空间布局和主要家具
   - 7-9分：较完整的空间展示，能看到主要区域和大部分家具
   - 4-6分：局部空间展示（如只有沙发一角、半个房间），但仍有空间语境
   - 0-3分：纯单品特写（一个花瓶、一盏灯、一个柜子），缺乏空间语境
   - 注意：我们要求的是"全景"级别的空间展示，单品特写即使很美也应打低分

# Scoring Rules (评分规则)
- is_approved = true 的条件：is_interior == true 且 style_match >= 7 且 has_human == false 且 scene_completeness >= 6
- 非室内场景（is_interior = false）一律不通过，无需再看其他维度
- 任何出现人物的图片（has_human = true）一律不通过
- 纯单品特写（scene_completeness <= 3）一律不通过
- 风格严重不符（style_match <= 3）一律不通过

# Output Format
请务必仅输出合法的 JSON 格式数据，不要包含任何额外的 markdown 代码块标记(如 ```json) 或解释性文字。

{{
  "is_interior": <布尔值, 是否为室内场景>,
  "style_match": <整数 0-10>,
  "has_human": <布尔值 true/false>,
  "scene_completeness": <整数 0-10>,
  "is_approved": <布尔值>,
  "reasoning": "<用一到两句话简述评分理由，必须具体指出室内/室外、风格和场景完整性方面的问题>"
}}"""


BATCH_COLLECTION_PROMPT_TEMPLATE = """# Role
你是一个严格的室内空间美学质量评估专家。你的任务是同时评估多张图片的质量。

# Context
你将被展示 {count} 张室内设计相关图片，编号为 0 到 {count_minus}。这些图片都标榜为检索词（Query）"{query}" 相关的室内设计内容。请逐张评估。

# Task
对每一张图片，结合检索词从以下维度进行严格判定：

1. 室内场景判定 (is_interior) [布尔值]：
   - true：图片是明确的"室内空间"或"室内细节"
   - false：图片主体是建筑外观、室外园景、纯自然风景、街道、建筑效果图
   - 严格规则：哪怕建筑风格与检索词契合，只要主视角在室外（能看到天空、建筑外墙），就判 false

2. 风格匹配度 (style_match) [0-10分]：
   - 10分：高度契合，典型元素丰富
   - 7-9分：明显匹配，有代表性元素
   - 4-6分：有关联但不典型
   - 0-3分：风格不符
   - 当前检索词判定标准：{criteria}
   - 风格关键词：{keywords}
   - 排除项（出现这些的应打低分）：{negative_examples}

3. 人物排除 (has_human) [布尔值]：
   - true：出现任何人（完整人体、人像、剪影、背影、局部手脚）
   - false：无任何人

4. 场景完整性 (scene_completeness) [0-10分]：
   - 10分：完整空间全景，看清布局和主要家具
   - 7-9分：较完整，能看到主要区域
   - 4-6分：局部空间，仍有空间语境
   - 0-3分：纯单品特写

5. 综合判定 (is_approved) [布尔值]：
   - true 条件：is_interior=true 且 style_match>=7 且 has_human=false 且 scene_completeness>=6
   - 任一不满足即 false

# Output Format
请仅输出一个 JSON 数组，每个元素对应一张图片（按编号顺序），不要包含 markdown 标记或解释文字：

[
  {{"index": 0, "is_interior": true/false, "style_match": 0-10, "has_human": true/false, "scene_completeness": 0-10, "is_approved": true/false, "reasoning": "简短理由"}},
  {{"index": 1, "is_interior": ..., ...}},
  ...
]

注意：数组中必须有 {count} 个元素，编号从 0 到 {count_minus}。"""


class PromptGenerator:
    """Prompt 生成器

    支持两种模式：
    1. 静态模式（默认）：根据查询词匹配预设模板
    2. 动态模式：接受外部 LLM 生成的详细筛选标准
    """

    # 类级别缓存：同一查询词的动态 criteria 只生成一次
    _dynamic_cache: dict = {}

    @classmethod
    def set_dynamic_criteria(cls, query: str, criteria_data: dict) -> None:
        """设置某个查询词的动态筛选标准（由外部 LLM 生成）

        Args:
            query: 查询词
            criteria_data: 包含 criteria, style_keywords, negative_examples 的字典
        """
        cls._dynamic_cache[query] = criteria_data

    @classmethod
    def has_dynamic_criteria(cls, query: str) -> bool:
        """检查是否有某个查询词的动态筛选标准"""
        return query in cls._dynamic_cache

    @staticmethod
    def generate(query: str, dynamic_template: dict = None) -> str:
        """根据检索词生成入口筛选 Prompt

        Args:
            query: 检索词
            dynamic_template: 可选的动态模板数据，优先级高于静态匹配
        """
        template = dynamic_template or PromptGenerator._resolve_template(query)

        return BASE_PROMPT_TEMPLATE.format(
            query=query,
            criteria=template["criteria"],
            keywords=", ".join(template["style_keywords"]),
            negative_examples=template["negative_examples"],
        )

    @staticmethod
    def generate_collection_prompt(query: str, dynamic_template: dict = None) -> str:
        """根据检索词生成收集阶段深度筛选 Prompt

        Args:
            query: 检索词
            dynamic_template: 可选的动态模板数据，优先级高于静态匹配
        """
        template = dynamic_template or PromptGenerator._resolve_template(query)

        return COLLECTION_PROMPT_TEMPLATE.format(
            query=query,
            criteria=template["criteria"],
            keywords=", ".join(template["style_keywords"]),
            negative_examples=template["negative_examples"],
        )

    @staticmethod
    def generate_batch_collection_prompt(count: int, query: str, dynamic_template: dict = None) -> str:
        """根据检索词生成批量收集阶段深度筛选 Prompt

        Args:
            count: 图片数量
            query: 检索词
            dynamic_template: 可选的动态模板数据，优先级高于静态匹配
        """
        template = dynamic_template or PromptGenerator._resolve_template(query)

        return BATCH_COLLECTION_PROMPT_TEMPLATE.format(
            count=count,
            count_minus=count - 1,
            query=query,
            criteria=template["criteria"],
            keywords=", ".join(template["style_keywords"]),
            negative_examples=template["negative_examples"],
        )

    @staticmethod
    def _resolve_template(query: str) -> dict:
        """解析模板数据：优先使用动态缓存，回退到静态匹配"""
        cache = PromptGenerator._dynamic_cache
        if query in cache:
            return cache[query]

        return PromptGenerator._match_template(query)

    @staticmethod
    def _match_template(query: str) -> dict:
        """匹配最接近的静态模板"""
        query_lower = query.lower()

        for key, template in PROMPT_TEMPLATES.items():
            if key == "default":
                continue
            if key in query_lower or query_lower in key:
                return template

        return PROMPT_TEMPLATES["default"]
