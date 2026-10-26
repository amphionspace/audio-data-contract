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

# v3 标签（annotate.py）。键是写进数据的英文标识，值是给模型看的定义。
TYPES = {
    "person": "人名：真实或虚构的人物、历史人物、角色，含外文译名、昵称和带称谓的人名（王先生）",
    "place": "地名：国家、行政区、街道、山川河湖、建筑、景点、车站机场、场馆",
    "organization": "机构与品牌：公司、品牌、商店、政府部门、学校、医院、协会团体、球队、媒体",
    "product": "产品：具体的产品、型号、软件或 App、车型、药品商品名、设备、技术平台或引擎",
    "work": "作品：书籍、影视、游戏、歌曲、节目、栏目、文章、法规文件等的标题",
    "term": "术语：学科、医学、法律、金融、技术等领域的专业概念，疾病、药物通用名、物种和化学物质名",
    "other": "其他专名：事件、会议、赛事、节日、朝代、奖项、政策或口号、流行语等不属于以上各类的专有名词",
    "common": "普通词：不是专有名词、也不是专业术语的日常词或低频普通词（含成语、形容词、动词）",
}

DOMAIN_GROUPS = {
    "medical": "医疗健康：临床各科、医药、中医、护理、公共卫生、养生",
    "science_tech": "科技：信息技术、互联网、人工智能、电子通信、航空航天、科研、工程技术",
    "business_finance": "经济金融：金融、投资、经济、企业管理、商业、电商、营销、房地产",
    "law_politics": "法律政务：法律、司法、政治、外交、国际关系、公共管理、社会治理",
    "military": "军事：军事科技、装备、训练、战史",
    "sports": "体育：各类体育运动、赛事、健身",
    "entertainment": "文娱：影视、音乐、游戏、电竞、综艺、动漫、明星",
    "culture_history": "文史艺术：文学、历史、艺术、书法、文化遗产、宗教、哲学、语言",
    "education": "教育：学校教育、考试、培训、学术交流",
    "nature_environment": "自然环境：生态、环保、动植物、地理、地质、气象、农林牧渔",
    "travel_life": "旅游与生活：旅游、交通出行、餐饮美食、时尚、家居、育儿、日常消费",
    "industry_energy": "工业能源：制造、能源、化工、建筑、交通运输工程、材料",
    "other": "其他：不属于以上各类",
}


def _choices(table: dict) -> str:
    return "\n".join(f"- {key}：{text}" for key, text in table.items())


TYPE_SYSTEM = f"""你在给语音识别热词评测集里的热词标类型。每条给出一个热词和它所在的句子（转写，可能只截取了一段）。按这个词在这句话里的意思，从下面选一个类型：

{_choices(TYPES)}

拿不准时选最贴近说话人所指的一类；既是公司名又是品牌名的选 organization。
只输出 JSON：{{"results": [{{"id": 编号, "type": "类型"}}, ...]}}，类型只能写上面的英文标识，每条都要有结果。"""

TYPE_REVIEW_SYSTEM = f"""你在复核语音识别热词评测集的热词类型标注。每条给出一个热词、它所在的句子（转写，可能只截取了一段），以及另一个模型标的类型（可能为空）。类型定义：

{_choices(TYPES)}

按这个词在这句话里的意思独立判断：标注正确就照抄，不正确或为空就写正确的类型。
只输出 JSON：{{"results": [{{"id": 编号, "type": "类型"}}, ...]}}，类型只能写上面的英文标识，每条都要有结果。"""

DOMAIN_SYSTEM = f"""你在给语音识别评测集的领域标签归类。每条是一个自由文本的领域名，把它归到下面的一个大类：

{_choices(DOMAIN_GROUPS)}

只输出 JSON：{{"results": [{{"id": 编号, "group": "大类"}}, ...]}}，大类只能写上面的英文标识，每条都要有结果。"""

DOMAIN_REVIEW_SYSTEM = f"""你在复核语音识别评测集的领域归类。每条给出一个自由文本的领域名，以及另一个模型归的大类（可能为空）。大类定义：

{_choices(DOMAIN_GROUPS)}

独立判断：归类正确就照抄，不正确或为空就写正确的大类。
只输出 JSON：{{"results": [{{"id": 编号, "group": "大类"}}, ...]}}，大类只能写上面的英文标识，每条都要有结果。"""
