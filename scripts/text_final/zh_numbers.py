"""Chinese numerals -> Arabic digits for training text (rule zh-num-v1, 2026-11-27).

Only numeral characters change (plus 百分之X -> X% and X点Y -> X.Y). Every other character stays as it was:
no unit symbols (公斤 stays 公斤), no date reformatting, no spaces. Follows GB/T 15835-2011 where it is
explicit and the common ASR inverse-normalization convention elsewhere:

- to Arabic: numbers of 10 and above, digit strings (years, phone / ID / plate numbers, codes), numerals
  next to Latin letters (5G, A4, MP3, H265), decimals, percentages, months and days in dates, clock times;
- kept as Chinese: single-digit counts and ordinals (三个人, 第一次), adjacent-number estimates (三四个,
  七八十岁, 一两天), estimates with 几 (十几个), fractions (三分之一), weekdays and lunar days (星期三, 初三),
  and fixed words and idioms (一下, 统一, 万一, 十分, 千万, 一五一十, 五四运动).

convert(text) returns (new_text, [(category, old, new), ...]).
"""
import re
from itertools import pairwise

import cn2an

DIGIT = "零〇一二三四五六七八九"
DIGIT_VAL = {c: str(i) for i, c in enumerate("零一二三四五六七八九")} | {"〇": "0", "幺": "1", "两": "2", "拐": "7", "洞": "0"}
UNIT = "十百千万亿"
NUMCH = f"{DIGIT}{UNIT}两幺拐洞"
RUN = re.compile(f"[{NUMCH}]+")
HOUR = f"[{DIGIT}两十]{{1,3}}"
MINUTE = f"[{DIGIT}十]{{1,3}}"
# 八点四十五: minutes read as a value (10-59) without 分 are a clock time, since decimals are read digit by digit
MINUTE_VALUE = f"([二三四五]?十[{DIGIT[1:]}]?)(?![{NUMCH}分倍米元块克斤吨升度秒%公个人岁年月日号天次位名条张台辆家件页章节集层楼栋路种等只本口道项场间座点几])"
TIME = re.compile(
    f"({HOUR})点(?:({MINUTE})分|(钟|半|整|一刻|三刻)|(零[{DIGIT[1:]}])(?![{NUMCH}分倍米元块克斤吨升度秒%公])|{MINUTE_VALUE})(?!之)"
)
TIME_RANGE = re.compile(f"({HOUR})点(?:到|至)({HOUR})点")
TIME_PREFIX = re.compile(f"(?:凌晨|早上|早晨|上午|中午|下午|傍晚|晚上|夜里|半夜|今晚|昨晚|明晚|今早|明早|每天|每晚)({HOUR})点")
DECIMAL = re.compile(f"([{DIGIT}{UNIT}两]+)点([{DIGIT}]+)([万亿])?(?![{NUMCH}钟]|分之)")
ONE_WORD_AFTER = set("刻直线下些样起般定点边切共会次种天句面")  # 八点一直, 四点一刻, 三点一线
TIME_UNIT_AFTER = set("倍米元块克斤吨升度秒万亿%")
# After a decimal X点Y: units and punctuation. A count word after it (七点四人座, 一点五种, 八点八点) means 点 is a clock or a list.
DECIMAL_NEXT = set("倍米元块克斤吨升度秒万亿%分毫厘寸尺亩码级岁兆赫的折公千平立英海摄年天小月周时到至和或左以多") | set("，。？！、：；,.?!;: ")
COUNT_AFTER = set("人个种等位条张件本只家口道项次场名台辆套间座点")
VERSION = re.compile(f"([{DIGIT}两]+)点([{DIGIT}]+)点([{DIGIT}]+)")
PERCENT = re.compile(f"百分之([{DIGIT}{UNIT}两]+(?:点[{DIGIT}]+)?)")
LATIN = re.compile(r"[A-Za-z]")
ESTIMATE_PAIRS = ["一二", "二三", "三四", "四五", "五六", "六七", "七八", "八九", "三五", "一两", "两三"]
# Words and idioms that contain numeral characters but are not numbers. A match anywhere overlapping the run
# keeps the run as Chinese, unless the run touches a Latin letter.
LEXICON = [
    "十足", "十全十美", "十字", "十有八九", "百分百", "成千上万", "千千万万", "十万八千里", "一五一十", "五四运动",
    "五四青年", "三三两两", "七七八八", "九九八十一", "百万富翁", "三十而立", "四十不惑", "七十二变", "十八般",
    "十八罗汉", "九九归一", "二八年华", "三七开", "二八开", "九五至尊", "一千零一夜", "星期", "礼拜", "周一", "周二",
    "周三", "周四", "周五", "周六", "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一长假", "十一假期", "国庆十一", "一一对应", "一一列举", "一一道来", "十二分", "万分", "两两", "一二九运动", "一二·九", "九一八", "七七事变", "一二八事变", "八一三", "四一二", "三点一线", "一点一点", "一点点", "一点一滴", "十月围城", "五月天", "九月九", "十三香",
]
TWO_DIGIT_BEFORE = set("年后届级号路次期班栋楼层室")  # 九八年, 零零后, 二三号 convert; other two-digit strings stay
WORDS_WITH_ONE = {"一样", "一个", "一下", "一些", "一起", "一直", "一定", "一般", "一点", "一种", "一次", "一边", "一共", "一切", "一面", "一会", "一句", "一天"}
COUNT_WORDS = set("项种只本套份批支根头匹双对场段篇首部款门所座间把块片台道封轮张条位名家件")  # GPO一项, 两A股
MEASURE = set("个年月日号岁天人次分秒元块米斤里度位名条张台辆家件页章节集万亿倍公克毫厘升吨层楼栋路公")


def _digits(s):
    return "".join(DIGIT_VAL[c] for c in s) if all(c in DIGIT_VAL for c in s) else None


def _value(s):
    """Integer value of a numeral run; keeps a trailing 万 / 亿 on round numbers (两千万 -> 2000万)."""
    if not any(c in UNIT for c in s):
        return _digits(s)
    if s[-1] in "万亿" and len(s) > 1 and s[-2] not in "万亿":
        head = _value(s[:-1])
        return None if head is None else head + s[-1]
    try:
        v = cn2an.cn2an(s.replace("两", "二").replace("幺", "一"), "strict")
    except (ValueError, KeyError, IndexError):
        return None
    return str(int(v)) if float(v).is_integer() else None


def _in_lexicon(text, i, j):
    lo, hi = max(0, i - 5), min(len(text), j + 5)
    win = text[lo:hi]
    for w in LEXICON:
        k = win.find(w)
        while k >= 0:
            if lo + k < j and lo + k + len(w) > i:
                return True
            k = win.find(w, k + 1)
    return False


def _month_context(text, i, j):
    """X月 is a date only next to a year or day, or with 份 / 初 / 中旬 / 底 (not 十月围城, 五月天)."""
    after = text[j + 1: j + 4]
    if _at(text, i - 1) == "年":
        return True
    return bool(re.match(f"[{DIGIT}十]+[日号]", after) or re.match("份|初|上旬|中旬|下旬|底|末", after))


def _at(text, k):
    return text[k] if 0 <= k < len(text) else ""


def _plain(text, i, j):
    """Category for a plain numeral run text[i:j] (no 点), or None to keep it Chinese."""
    run = text[i:j]
    prev, nxt, nxt2 = _at(text, i - 1), _at(text, j), text[j: j + 2]
    left = re.search(r"[A-Za-z]+$", text[:i])
    left_word = bool(left) and len(left.group()) >= 3 and left.group().islower()
    latin = bool((LATIN.match(prev) and not left_word) or LATIN.match(nxt))
    if latin and len(run) == 1 and (run == "两" or (not LATIN.match(nxt) and (nxt in MEASURE or nxt in COUNT_WORDS or text[i:i + 2] in WORDS_WITH_ONE))):
        latin = False  # will一个, yesterday一样: Chinese words after an English word, not a code
    if latin:
        return "latin" if _value(run) else None
    if _in_lexicon(text, i, j):
        return None
    named = _at(text, j + 1)
    if nxt == "的" and named and named in UNIT and named in run and _at(text, j + 2) in ("", "字") + tuple("，。？！、；：,.?!;:"):
        return None  # 数字一百的百，: the numeral names its own unit character (not 七十的十七次方)
    if nxt == "几" or prev == "几":
        return None  # 十几个, 二十几岁
    if nxt2 == "分之" or text[i - 2: i] == "分之":
        return None  # fractions stay Chinese
    if len(run) >= 4 and len(run) % 2 == 0 and all(run[k:k + 2] in ESTIMATE_PAIRS for k in range(0, len(run), 2)):
        return None  # 二三五六岁: stammered estimates
    if any(run.startswith(p) for p in ESTIMATE_PAIRS) and (len(run) == 2 or run[2] in UNIT):
        return None  # 三四个, 七八十岁, 一两天
    if run[0] in "百千万亿":
        return None  # 百姓, 千万, 万一: words, not numbers
    has_unit = any(c in UNIT for c in run)
    if not has_unit:
        if len(run) >= 3:
            if all(c in DIGIT[1:] for c in run) and all(DIGIT.index(b) - DIGIT.index(a) == 1 for a, b in pairwise(run)):
                return None  # counting aloud: 一二三
            return "digits"
        if len(run) == 2:
            return "digits" if all(c in DIGIT for c in run) and nxt in TWO_DIGIT_BEFORE else None
        # single digit: only months and days of dates
        if nxt == "月" and _month_context(text, i, j):
            return "date"
        if nxt in ("日", "号") and _at(text, i - 1) == "月":
            return "date"
        return None
    if run == "十" and not (nxt in MEASURE and not (nxt == "分" and _at(text, j + 1) != "钟")):
        return None  # 十分 (very), bare 十; 十个 / 十分钟 convert
    v = _value(run)
    if v is None:
        return None
    if nxt == "月":
        return "date" if v.isdigit() and int(v) <= 12 and _month_context(text, i, j) else None
    if nxt in ("日", "号") and _at(text, i - 1) == "月":
        return "date"
    return "value"


def convert(text):
    out, pos, changes = [], 0, []
    for s, e, cat, new in edits(text):
        out.append(text[pos:s])
        out.append(new)
        changes.append((cat, text[s:e], new))
        pos = e
    out.append(text[pos:])
    return "".join(out), changes


def edits(text):
    """The replacements convert() makes, as sorted (start, end, category, new) spans of text."""
    edits = []  # (start, end, category, new)
    taken = [False] * len(text)

    def claim(s, e, cat, new):
        if new and not any(taken[s:e]):
            edits.append((s, e, cat, new))
            for k in range(s, e):
                taken[k] = True

    def _est(x):
        return any(x.startswith(p) for p in ESTIMATE_PAIRS)

    for m in VERSION.finditer(text):
        before, after = text[max(0, m.start() - 3): m.start()], text[m.end(): m.end() + 2]
        if re.search(r"[A-Za-z]$", before) or "版" in before or after.startswith("版"):
            parts = [_digits(m.group(1)), _digits(m.group(2)), _digits(m.group(3))]
            if all(parts):
                claim(m.start(), m.end(), "decimal", ".".join(parts))
    for m in TIME.finditer(text):
        if _est(m.group(1)):
            continue
        if m.group(4) and LATIN.match(_at(text, m.start() - 1)):
            continue  # KD一点零四 is a ratio, not 1:04
            continue
        h = _value(m.group(1))
        if h is None or int(h) > 24 or _in_lexicon(text, m.start(), m.end()):
            continue
        if m.group(4):
            claim(m.start(1), m.end(1), "time", h)
            claim(m.start(4), m.end(4), "time", _digits(m.group(4)))
        elif m.group(2) or m.group(5):
            g = 2 if m.group(2) else 5
            before = _at(text, m.start() - 1)
            if g == 5 and ((before and before in NUMCH) or text[max(0, m.start() - 3): m.start()] == "百分之"):
                continue  # 百分之一百一十六点三十, 百分之十六点二十六: part of a longer number, not a clock time
            if m.group(1) == "一" and m.group(2) == "十" and _at(text, m.start() - 1) in ("这", "那", "第", "每", "哪", "有"):
                continue  # 这一点十分重要: 十分 is "very", not ten past one
            mi = _value(m.group(g))
            if mi is None or int(mi) > 59:
                continue
            claim(m.start(1), m.end(1), "time", h)
            claim(m.start(g), m.end(g), "time", mi)
        else:
            claim(m.start(1), m.end(1), "time", h)
    for m in TIME_RANGE.finditer(text):
        if _est(m.group(1)) or _est(m.group(2)):
            continue
        a, b = _value(m.group(1)), _value(m.group(2))
        if a and b and int(a) <= 24 and int(b) <= 24 and not _in_lexicon(text, m.start(), m.end()):
            claim(m.start(1), m.end(1), "time", a)
            claim(m.start(2), m.end(2), "time", b)
    for m in TIME_PREFIX.finditer(text):
        h = None if _est(m.group(1)) else _value(m.group(1))
        if h and int(h) <= 24 and not re.match(f"[{DIGIT}]", _at(text, m.end())):
            claim(m.start(1), m.end(1), "time", h)
    for m in PERCENT.finditer(text):
        if _at(text, m.start() - 1) == "点":
            continue  # 十八点百分之三: odd reading, keep
        body = m.group(1)
        if "点" in body:
            w, f = body.split("点", 1)
            wv, fv = _value(w), _digits(f)
            new = None if wv is None or fv is None else f"{wv}.{fv}%"
        else:
            v = _value(body)
            new = None if v is None else f"{v}%"
        claim(m.start(), m.end(), "percent", new)
    for m in DECIMAL.finditer(text):
        if _in_lexicon(text, m.start(), m.end()):
            continue
        w, f, unit, nxt = _value(m.group(1)), _digits(m.group(2)), m.group(3) or "", _at(text, m.end())
        if w is None or f is None:
            continue
        if m.group(2) == "一" and not unit and nxt in ONE_WORD_AFTER:
            continue  # 八点一直, 四点一刻
        if not unit and nxt in COUNT_AFTER and text[m.end(): m.end() + 4] != "个百分点":
            continue  # 七点四人座, 一点五种, 八点八点
        if not unit and len(m.group(2)) == 1 and nxt and nxt not in DECIMAL_NEXT and not LATIN.match(nxt) \
                and text[m.end(): m.end() + 4] != "个百分点":
            continue  # 一点一拖拉: a single fractional digit needs a unit, punctuation or the end after it

        if w.isdigit() and int(w) <= 24 and m.group(2).startswith("零") and len(m.group(2)) == 2 and not unit \
                and nxt not in TIME_UNIT_AFTER and not LATIN.match(_at(text, m.start() - 1)):
            continue  # 十二点零五她就走了: a clock time, not 12.05
        claim(m.start(), m.end(), "decimal", f"{w}.{f}{unit}")
    for m in RUN.finditer(text):
        i, j = m.span()
        # split around already-claimed characters
        k = i
        while k < j:
            if taken[k]:
                k += 1
                continue
            e = k
            while e < j and not taken[e]:
                e += 1
            e2 = e
            while e2 - k >= 2 and text[e2 - 1] == "一" and text[e2 - 1: e2 + 1] in WORDS_WITH_ONE:
                e2 -= 1  # 一一一些人: the last 一 belongs to 一些
            cat = _plain(text, k, e2)
            if cat:
                claim(k, e2, cat, _value(text[k:e2]) if cat != "digits" else _digits(text[k:e2]))
            k = e
    return sorted(edits)


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        t = line.rstrip("\n")
        new, ch = convert(t)
        print(f"{t}\t{new}\t{ch}")
