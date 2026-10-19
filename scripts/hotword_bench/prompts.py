"""LLM prompts for the hotword benchmark (the extraction prompt is AmphionData's)."""

from __future__ import annotations

import ast
from pathlib import Path


def extract_prompt(amphiondata_repo: str) -> str:
    """AmphionData's EXTRACT_HOTWORD, read from source so labels keep the same definition."""
    path = Path(amphiondata_repo) / "src" / "amphiondata" / "llm" / "prompts.py"
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "EXTRACT_HOTWORD" for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f"EXTRACT_HOTWORD not found in {path}")


EXTRACT_BATCH = """下面有 {n} 条文本，请对每条分别按上述要求抽取热词。
只输出一个 JSON 对象：{{"results": [{{"id": 编号, "hotwords": [...]}}, ...]}}，编号与输入一致，每条都要有结果，没有热词就给空列表。

{texts}"""

REVIEW_SYSTEM = """你在复核语音识别热词评测集的标注。每条给出一句参考转写，以及另一个模型从中抽取的热词（程序已确认每个词都出现在转写里）。逐个判断：

1. keep：这个词是否适合放进用户的热词列表——人名、具体地名或建筑、机构/品牌/产品/球队、专业术语，或其他只凭发音容易写错的专有名词。常见名词、动词、形容词、泛称（公司、学校、老师）和最常见的国家与首都（中国、美国、北京）都不算。
2. 如果参考转写本身明显把这个词写错了（错别字、同音误写、说话内容与写法对不上），keep=false，reason 写"参考疑似错误"。
3. type：人名 / 地名 / 机构品牌 / 专业术语 / 其他，只能选一个。

只输出 JSON：{"results": [{"id": 编号, "terms": [{"term": "原词", "keep": true, "type": "人名", "reason": "简短理由"}]}]}，每个输入的词都要出现一次。"""

REVIEW_USER = """{items}"""

CONFUSABLE_SYSTEM = """你在为语音识别热词评测构造干扰词。部署时，系统会从用户的热词库里检索出几十个和音频相似的词放进提示；库里常有与说出的词读音相同或相近、但其实是另一个条目的词。请为每个热词写出最多 {k} 个这样的干扰词：

- 读音相同或相近的不同写法（刘燕 → 柳岩、刘艳；郑州 → 正洲），或名字很像的另一个真实条目（另一个人名、地名、机构、产品、术语）。
- 必须像真实热词库里会有的条目，类型与原词一致。
- 与原词写法不同，且说话人说原词时转写成干扰词一定算错：不能是原词的同义写法、简繁体、异体字、英文缩写/全称、只差空格或标点的写法。
- 不要照抄原词，不要只在原词后面加"儿""网""市"之类的字凑数，不要写阿拉伯数字与汉字数字互换的写法。
- 想不出合适的就少写，不要凑数。

例子：
刘燕 → 柳岩、刘艳、刘雁
郎平 → 郎萍、朗平、梁平
温州 → 文州、温洲、云州
中国人民银行 → 中国人民保险、中国农业银行、中国人民大学
心肌梗死 → 心肌缺血、心肌梗阻、心肌劳损

只输出 JSON：{{"results": [{{"term": "原词", "confusables": ["干扰词", ...]}}]}}，每个输入的词都要出现一次。"""

CONFUSABLE_REVIEW_SYSTEM = """你在复核语音识别热词评测的干扰词。每对给出一个原词（说话人实际说的词）和一个干扰词。判断干扰词是否合格，合格需同时满足以下三条：

1. 如果说话人说的是原词，转写成干扰词一定算错。同义写法、简繁体、异体字、英文缩写或全称、只差空格或标点、本来就是同一个东西的另一种叫法，都不合格。
2. 确实容易混淆：读音相同或相近，或者是名字很像的另一个条目。读音和写法都差得很远的不合格。
3. 像真实热词库里会有的条目（人名、地名、机构、产品、术语）。只在原词后面加"儿""子"之类的字凑出来、不像真实条目的不合格。

只输出 JSON：{"results": [{"id": 编号, "keep": true}, {"id": 编号, "keep": false, "reason": "不合格的简短理由"}]}，每对都要出现一次；合格的不写理由。"""
