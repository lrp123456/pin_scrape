"""动态提示词生成器 - 将用户查询词转化为精准的视觉筛选清单

调用远程/本地 LLM（纯文本，不带图），将模糊的装修风格名称
拆解为结构化的视觉特征检查清单，替代静态模板。
"""

import json
import logging
import requests
from typing import Optional, Dict

from shared.ollama_config import get_ollama_config

_dp_logger = logging.getLogger("pinterest_scraper.dynamic_prompt")

# ============================================================
# 动态提示词生成的系统 Prompt
# ============================================================
DYNAMIC_PROMPT_SYSTEM = """# Role（角色设定）
你是一个专业的室内设计视觉分析专家与多模态大模型（VLM）评估工程师。你的任务是将用户输入的模糊装修风格，转化为一套极其精准、客观且可被视觉算法识别的「图片筛选标准」。

# Task（任务目标）
把用户输入的风格名称，拆解为结构化的视觉特征检查清单（Checklist）。这套清单将直接输入给下游的视觉模型，用于判断一张图片是否符合该风格。输出的特征必须是肉眼和机器都可以明确分辨的客观物理属性。

# Guidelines（视觉拆解维度）
请严格按照以下维度输出筛选标准：

## 1. 主色调与色彩比例 (Color Distribution)
画面中必须占据绝对主导（如 60% 以上）的色系，以及允许的点缀色。必须具体到色号描述（如"奶白色"、"米黄色"、"珍珠白"、"浅咖色"、"燕麦色"）。

## 2. 高频材质与纹理 (Key Materials)
画面中必须出现的核心硬装或软装材质特征。必须具体描述表面质感（如"哑光柔光砖"、"微水泥"、"羊羔绒面料"、"哑光木饰面"、"棉麻布艺"）。

## 3. 可检测的核心物件 (Detectable Objects/Shapes)
该风格标志性的、具有明确几何形态的家具或元素（作为加分项）。必须指出具体的形状特征（如"圆弧边角家具"、"拱形门洞"、"造型圆润饱满的沙发"、"落地纸灯"）。

## 4. 一票否决项 (Disqualifying Elements / Negative Anchors)
绝对不能出现在画面中的元素、材质或颜色。一旦检测到，直接判定为不符合。必须具体列举（如"大面积高饱和度亮色"、"复杂的欧式石膏线雕花"、"亮面大理石"、"大面积黑金/黄铜反光金属"、"水晶吊灯"）。

## 5. 判定逻辑 (Scoring Logic)
简要概括如何综合以上条件判断一张图是"高度符合"、"勉强符合"还是"完全不符"。

# Output Format（输出格式）
请务必仅输出合法的 JSON 格式数据，不要包含任何额外的 markdown 代码块标记(如 ```json) 或解释性文字。

{
  "criteria": "<完整的筛选标准文本，将上述1-5维度的内容整合为一段连贯的判定标准文本>",
  "style_keywords": ["<关键词1>", "<关键词2>", "<关键词3>", "..."],
  "negative_examples": "<一票否决项的简要列表，用中文逗号分隔>"
}

# Examples（参考示例）

输入词：奶油风
输出：
{
  "criteria": "【主色调】绝对主导色为低饱和度的暖色系（奶白、米黄、珍珠白、浅咖、燕麦色）。视觉上不能有强烈的色彩对比。【高频材质】微水泥地面或哑光柔光砖、羊羔绒/毛毛虫沙发面料、哑光木饰面、棉麻布艺。反光材质极少。【可检测物件】带有圆弧边角的家具（拒绝直棱直角）、弧形门洞/拱门、造型圆润饱满的沙发、落地纸灯或奶油色造型吊灯。【一票否决项】出现大面积高饱和度亮色（如大红、亮蓝）；出现复杂的欧式石膏线雕花；出现亮面大理石、大面积黑金/黄铜反光金属、水晶吊灯；黑色占比超过画面 5%。【判定逻辑】画面整体呈现柔和、低对比度的高明度状态。若命中一票否决项或存在大面积锐利直角，直接判定为不符合。",
  "style_keywords": ["奶油色", "米白", "奶咖", "圆润", "柔和", "温馨", "治愈", "哑光", "低饱和度"],
  "negative_examples": "高饱和度亮色、欧式石膏线雕花、亮面大理石、黑金/黄铜反光金属、水晶吊灯、大面积黑色"
}

输入词：侘寂风
输出：
{
  "criteria": "【主色调】大地色系主导（灰白、米灰、枯木色、泥土色、黯淡的绿色）。整体明度偏低，带有斑驳的做旧感。【高频材质】粗糙的微水泥/硅藻泥墙面、未经精细打磨的原木（带木结或裂纹）、藤编、亚麻、陶土/粗陶。【可检测物件】枯枝/干花插花艺术（代替鲜艳绿植）、低矮的无腿沙发或地台床、形态不规则的陶罐、暗藏式局部光源（见光不见灯）。【一票否决项】任何极具现代工业感的抛光材质（不锈钢、亮面玻璃、烤漆面板）；色彩鲜艳明亮的塑料制品；对称且极其规整的家具布局。【判定逻辑】视觉重点在于残缺美和哑光粗糙感。如果画面看起来过于崭新、光泽度高、色彩饱和度高，即判定不符合。",
  "style_keywords": ["侘寂", "大地色", "微水泥", "原木", "藤编", "亚麻", "粗陶", "做旧", "斑驳", "哑光"],
  "negative_examples": "抛光不锈钢、亮面玻璃、烤漆面板、鲜艳塑料制品、对称规整布局、高光泽度"
}"""


def generate_dynamic_criteria(
    query: str,
    ollama_endpoint: Optional[str] = None,
    ollama_model: Optional[str] = None,
    timeout: int = 120,
) -> Optional[Dict[str, object]]:
    """将查询词转化为动态视觉筛选标准

    调用远程/本地 Ollama 进行纯文本推理，将模糊的风格名称
    拆解为结构化的视觉特征检查清单。

    Args:
        query: 用户的搜索查询词（如"现代简约"、"日式禅意"）
        ollama_endpoint: Ollama API 地址，默认从配置读取
        ollama_model: Ollama 模型名，默认从配置读取
        timeout: 请求超时时间（秒），默认 120

    Returns:
        {
            "criteria": str,          # 完整筛选标准文本
            "style_keywords": [str],  # 风格关键词列表
            "negative_examples": str  # 一票否决项
        }
        如果生成失败，返回 None（调用方应回退到静态模板）
    """
    config = get_ollama_config()
    endpoint = ollama_endpoint or config.endpoint
    model = ollama_model or config.model

    _dp_logger.info(f"[动态提示词] 开始为查询词生成筛选标准: {query}")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": DYNAMIC_PROMPT_SYSTEM,
            },
            {
                "role": "user",
                "content": f"请根据以下风格名称生成筛选标准：{query}",
            },
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.3,  # 低温度以获得稳定输出
        },
    }

    try:
        response = requests.post(
            f"{endpoint}/api/chat",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()

        result_data = response.json()
        content = result_data.get("message", {}).get("content", "")

        if not content:
            _dp_logger.warning("[动态提示词] 模型返回空内容")
            return _fallback_static(query)

        # 清理可能的 markdown 代码块标记
        content = content.strip()
        if content.startswith("```"):
            # 移除 ```json 或 ``` 标记
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        parsed = json.loads(content)

        # 验证必要字段
        criteria = parsed.get("criteria", "")
        style_keywords = parsed.get("style_keywords", [])
        negative_examples = parsed.get("negative_examples", "")

        if not criteria:
            _dp_logger.warning("[动态提示词] 缺少 criteria 字段，回退静态模板")
            return _fallback_static(query)

        # 确保 style_keywords 是列表
        if isinstance(style_keywords, str):
            style_keywords = [k.strip() for k in style_keywords.split(",") if k.strip()]

        result = {
            "criteria": criteria,
            "style_keywords": style_keywords,
            "negative_examples": negative_examples,
        }

        _dp_logger.info(
            f"[动态提示词] ✅ 生成成功: {len(criteria)} 字符, "
            f"{len(style_keywords)} 个关键词"
        )
        return result

    except requests.Timeout:
        _dp_logger.warning(f"[动态提示词] 请求超时 ({timeout}s)，回退静态模板")
        return _fallback_static(query)
    except requests.ConnectionError:
        _dp_logger.warning(f"[动态提示词] 连接失败: {endpoint}")
        return _fallback_static(query)
    except json.JSONDecodeError as e:
        _dp_logger.warning(f"[动态提示词] JSON 解析失败: {e}，原始内容: {content[:200]}")
        # 尝试用正则从非 JSON 内容中提取有用文本
        return _fallback_static(query)
    except Exception as e:
        _dp_logger.warning(f"[动态提示词] 未知错误: {e}")
        return _fallback_static(query)


def _fallback_static(query: str) -> Optional[Dict[str, object]]:
    """回退到静态模板"""
    _dp_logger.info(f"[动态提示词] 回退到静态模板: {query}")
    from shared.prompt_templates import PROMPT_TEMPLATES

    # 尝试从静态模板中匹配
    for key, template in PROMPT_TEMPLATES.items():
        if key == "default":
            continue
        query_lower = query.lower()
        if key in query_lower or query_lower in key:
            _dp_logger.info(f"[动态提示词] 匹配到静态模板: {key}")
            return {
                "criteria": template["criteria"],
                "style_keywords": template.get("style_keywords", []),
                "negative_examples": template.get("negative_examples", ""),
            }

    _dp_logger.info(f"[动态提示词] 使用默认模板: {query}")
    default = PROMPT_TEMPLATES["default"]
    return {
        "criteria": default["criteria"],
        "style_keywords": default.get("style_keywords", []),
        "negative_examples": default.get("negative_examples", ""),
    }
