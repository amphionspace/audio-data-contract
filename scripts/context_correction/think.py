"""Build the think text of each training record from the cleaning decisions.

One line per explained word: '<pinyin> 这个音，说话人说是「<evidence>」，写作「<word>」。'. Chars and evidence come from
the two judges (both must give the same set of chars); pinyin comes from pypinyin, toneless, read in the evidence.
Records whose explanation is uncertain, or whose lines fail the checks, may only train with think off. Records the scan
or the regex rules flagged as possibly explaining a spelling are listed think-off too; every record not listed is an
ordinary one (think off, or think on with the fixed sentence ``NO_EXPLANATION``).

Audio-record sources: one decision per distinct target text, shared by its records. Lhotse sources (WenetSpeech, VITW):
a decision covers a window of segments and each segment is a training record, so a line goes to the segment holding
its whole quote; its record ID is ``<dataset>@<version>:<split>:<supervision id>``, as the training loader names it.

Sources, paths and the cleaning version come from clean_recipe.yaml next to this script.

usage: think.py <out dir> [source ...]   (needs pypinyin and pyyaml)
"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from pypinyin import Style, lazy_pinyin

RECIPE = yaml.safe_load(Path(__file__).with_name("clean_recipe.yaml").read_text())
CLEAN = Path(RECIPE["out"])  # the cleaning decisions
DATA = Path(RECIPE["data_root"])
NO_EXPLANATION = "这段没有说明字怎么写。"
HAN = re.compile(r"[㐀-鿿]")
JUDGES = ("qwen", "deepseek")
MAX_QUOTE = 30  # longer quotes are mostly lectures that wander off the explanation ("…好，我们再回头看，梨冒号。")


def pinyin_of(text: str) -> list[str]:
    """One toneless syllable per character of ``text`` (non-Han characters map to themselves)."""
    out = lazy_pinyin(text, style=Style.NORMAL, v_to_u=True, errors=lambda s: list(s))
    assert len(out) == len(text), (text, out)
    return out


def final_span(evidence: str, text: str, final: str) -> str | None:
    """The evidence as it reads in the final text (corrections substitute characters in place)."""
    if evidence in final:
        return evidence
    at = text.find(evidence)
    if at >= 0 and len(text) == len(final):
        return final[at:at + len(evidence)]
    return None


NEGATION = ("不是", "不要", "并非", "不能")
BOUNDARY = set("，。！？；、,.!?;")
RADICAL = ("字旁", "字头", "字底", "字框", "字边", "旁")
MERGE_GAP = 6  # a negated clause this close to a written word joins that word's quote
RETRACTION = re.compile(r"(?<!对)不对|说错")  # "哎呀，不对" after the quote, not the tag question "对不对"


def clause_before(s: str, i: int) -> str:
    j = i
    while j > 0 and s[j - 1] not in BOUNDARY:
        j -= 1
    return s[j:i]


def negated(c: str, evidence: str) -> bool:
    """The char is only named as what is NOT meant ("不是竟然的竟"): some occurrence follows a negation and none
    follows an affirming 是 ("而是炒房的炒")."""
    neg = aff = False
    for i, ch in enumerate(evidence):
        if ch != c:
            continue
        before = clause_before(evidence, i)
        last = max(before.rfind(m) for m in NEGATION)
        rest = before[last + 2:] if last >= 0 else before
        if "是" in rest.replace("不是", ""):
            aff = True
        elif last >= 0:
            neg = True
    return neg and not aff


def radical_only(c: str, evidence: str) -> bool:
    """The char is only the radical named in the quote ("火字旁"), not a word whose spelling is explained."""
    at = [i for i, ch in enumerate(evidence) if ch == c]
    return bool(at) and all(evidence[i + 1:].startswith(RADICAL) for i in at)


def reading(c: str, context: str) -> str:
    """Toneless pinyin of ``c`` as read in ``context``: a reading other than the default one comes from a phrase
    (长辈 zhang, 重庆 chong) and wins over the bare repeated char."""
    default = lazy_pinyin(c, style=Style.NORMAL, v_to_u=True)[0]
    syllables = pinyin_of(context)
    other = [syllables[i] for i, ch in enumerate(context) if ch == c and syllables[i] != default]
    return other[0] if other else default


def words_of(chars: set[str], evidence: str) -> list[str]:
    """Chars explained by one quote, joined into the words they form in it (高+山 -> 高山; 射, 涉 stay apart)."""
    order = sorted(chars, key=lambda c: evidence.find(c) if c in evidence else len(evidence))
    words = []
    for c in order:
        if words and words[-1] + c in evidence:
            words[-1] += c
        else:
            words.append(c)
    return words


def judge_chars(explanations: list[dict], renamed: dict[str, str], text: str, final: str) -> list[tuple[str, dict]]:
    """(char, explanation) pairs of one judge. A word given as the char ("集块岩") counts as its chars. In a corrected
    window a char named as the original transcript wrote it ("猪呢是朱红色的猪" for 朱) counts as the corrected one,
    when its quote, as corrected, holds the corrected char and no longer the original one."""
    pairs = []
    for e in explanations:
        c = e.get("char") or ""
        span = final_span(e["evidence"], text, final) or ""
        for x in list(c) if len(c) > 1 and all(HAN.fullmatch(y) for y in c) else [c] if c else []:
            new = renamed.get(x)
            pairs.append((new if new and new in span and x not in span else x, e))
    return pairs


def agreed_chars(pairs: list[list[tuple[str, dict]]], final: str) -> set[str] | None:
    """The explained chars, when the judges agree: the same set, or one judge adds chars of the same word
    ("小鹿" against "鹿": each extra char sits next to a shared one in the text)."""
    sets = [{c for c, _ in p} for p in pairs]
    small, big = sorted(sets, key=len)
    if not small:
        return None
    if small == big or small < big and all(any(c + x in final or x + c in final for c in small) for x in big - small):
        return big
    return None


def render(quote: str, word: str, syllables: list[str]) -> str:
    return f"{' '.join(syllables)} 这个音，说话人说是「{quote}」，写作「{word}」。"


def think_lines(row: dict, final: str) -> tuple[list[tuple[int, int, str, list[str]]] | None, str, list[str]]:
    """(lines, reason, subtypes): lines are (start, end, word, syllables) with the quote's span in ``final``; None when
    the record may only train with think off."""
    first = row["explanations"]
    second = {k: a.get("explanations") or [] for k, a in row["rescue"].items()} if "rescued" in row["reasons"] else first
    subtypes = sorted({e.get("subtype") for k in JUDGES for e in first.get(k, []) if e.get("subtype")})
    to = defaultdict(set)
    for e in row["edits"] if row["decision"] == "corrected" else []:
        to[e["from"]].add(e["to"])
    renamed = {a: next(iter(b)) for a, b in to.items() if len(b) == 1}
    pairs = [judge_chars(second.get(k, []), renamed, row["text"], final) for k in JUDGES]
    chars = agreed_chars(pairs, final)
    if not chars:
        return None, "chars_differ", subtypes
    negation = {c for k in JUDGES for c, e in judge_chars(first.get(k, []), renamed, row["text"], final)
                if e.get("subtype") == "否定对比"}
    by_evidence, denied = defaultdict(set), []
    for char in sorted(chars):
        found = {s for p in pairs for c, e in p if c == char
                 for s in [final_span(e["evidence"], row["text"], final)] if s}
        if not found:
            return None, "evidence_not_found", subtypes
        if not HAN.fullmatch(char) or char not in final:
            return None, "char_not_in_text", subtypes
        # Quotes holding the char first; negations keep their "不是…" part (longest), others the shortest quote;
        # equal lengths go by position, so that reruns pick the same quote.
        ranked = sorted(found, key=lambda e: (char not in e, -len(e) if char in negation else len(e), final.find(e), e))
        denials = [e for e in ranked if negated(char, e)]
        # A shorter quote cut out of a denial ("大臣的“臣”" from "左上角不是一个大臣的“臣”") is still a denial.
        written = [e for e in ranked if not any(e in d for d in denials)]
        if not written:
            denied.append(denials[0])
        elif not radical_only(char, written[0]):
            by_evidence[written[0]].add(char)
    if not by_evidence:
        return None, "no_written_word", subtypes
    spans = []  # [start, end, word] in the final text
    for evidence, group in by_evidence.items():
        start = final.find(evidence)
        spans += [[start, start + len(evidence), w] for w in words_of(group, evidence)]
    for evidence in denied:  # "不是竟然的竟" joins the quote of the word it is contrasted with, if next to it
        start = final.find(evidence)
        end = start + len(evidence)
        near = min(spans, key=lambda s: max(start - s[1], s[0] - end, 0))
        if max(start - near[1], near[0] - end, 0) <= MERGE_GAP:
            for s in spans:
                if s[:2] == near[:2]:
                    s[0], s[1] = min(s[0], start), max(s[1], end)
    lines = []
    for start, end, word in sorted(spans):
        quote = final[start:end]
        if RETRACTION.search(final[end:end + 8]):
            return None, "retracted", subtypes
        if len(quote) > MAX_QUOTE:
            return None, "long_quote", subtypes
        syllables = [reading(c, quote if c in quote else final) for c in word]
        if not all(s.isalpha() and s.isascii() or "ü" in s for s in syllables):
            return None, "no_pinyin", subtypes
        lines.append((start, end, word, syllables))
    return lines, "ok", subtypes


def gz_rows(path: Path):
    with gzip.open(path, "rt") as f:
        for line in f:
            yield json.loads(line)


def judged(source: str):
    """(decision row, category, final text, lines, reason, subtypes) for every window still in the training data."""
    with open(CLEAN / source / "decisions.jsonl") as f:
        rows = [json.loads(line) for line in f]
    for row in rows:
        if row.get("eval_excluded"):
            continue
        reason = row["reasons"][0] if row["reasons"] else ""
        if row["decision"] in ("consistent", "corrected") or reason == "rescued":
            category = "rescued" if reason == "rescued" else row["decision"]
            final = row["corrected"] if row["decision"] == "corrected" else row["text"]
            yield (row, category, final, *think_lines(row, final))
        elif row["decision"] == "not_hit":  # often still talks about writing ("口字旁", "D I S C O R D"): not a negative
            yield row, "not_hit", row["text"], None, "may_explain", []
        elif row["decision"] == "unchanged":  # one judge saw an explanation, the other did not
            yield row, "uncertain", row["text"], None, "uncertain", []
        # quarantined: not in the training data


def candidates(source: str) -> set[str]:
    """Units the regex rules flagged but the rescan let go: some still explain a spelling ("支沟就是认知的知")."""
    with open(CLEAN / source / "decisions.jsonl") as f:
        decided = {json.loads(line)["unit_id"] for line in f}
    with open(CLEAN / source / "regex.jsonl") as f:
        return {r["unit_id"] for line in f for r in [json.loads(line)] if r["unit_id"] not in decided}


def think_of(lines, final: str) -> str | None:
    return None if lines is None else "\n".join(render(final[s:e], w, py) for s, e, w, py in lines) or NO_EXPLANATION


def records_source(source: str, spec: dict, build: dict):
    """Units keyed by final target text; yields (dataset, record_id, unit) for every record carrying one."""
    units = {}
    for row, category, final, lines, why, subtypes in judged(source):
        if final in units:  # two decisions end in the same text: neither one is sure
            units[final].update(think=None, think_on=False, reason="duplicate_text")
            continue
        units[final] = {"unit_id": row["unit_id"], "category": category, "subtypes": subtypes, "text": final,
                        "think": think_of(lines, final), "think_on": lines is not None, "reason": why, "records": 0}
    loose = candidates(source)
    for u in gz_rows(CLEAN / source / "units.jsonl.gz"):
        if u["unit_id"] in loose and u["text"] not in units:
            units[u["text"]] = {"unit_id": u["unit_id"], "category": "candidate", "subtypes": [], "text": u["text"],
                                "think": None, "think_on": False, "reason": "may_explain", "records": 0}
    targets = [{"dataset": spec["dataset"], "records": spec["records"]}, *spec.get("also_derive", [])]
    for target in targets:
        derived = build[target["dataset"]]["derived"]
        if derived:
            version = derived.split("@")[1]
            paths = {s: Path(p).parents[2] / version / "records" / Path(p).name for s, p in target["records"].items()}
        else:  # nothing changed: the original version is the one to train on
            derived, paths = target["dataset"], {s: Path(p) for s, p in target["records"].items()}
        if not all(p.exists() for p in paths.values()):
            print(f"{source}: {derived} has no records on disk, skipped")
            continue
        for path in paths.values():
            for row in gz_rows(path):
                unit = units.get((row.get("target") or "").strip()) if row.get("language") == "zh" else None
                if unit:
                    unit["records"] += 1
                    yield derived, row["id"], unit
    return units


def lhotse_source(source: str, spec: dict, build: dict):
    """Windows of segments; each segment of a kept window is a record of the derived version."""
    derived = build["derived"]
    version = derived.split("@")[1]
    supervisions = DATA / "datasets" / derived.split("@")[0] / "versions" / version / "supervisions" / f"{spec['split']}.jsonl.gz"
    rows = []  # (segment id, final segment text, unit)
    units = {}
    for row, category, final, lines, why, subtypes in judged(source):
        texts = {s["id"]: list(s["text"]) for s in row["segments"]}
        for e in row["edits"] if category == "corrected" else []:
            assert texts[e["segment"]][e["offset"]] == e["from"], (row["unit_id"], e)
            texts[e["segment"]][e["offset"]] = e["to"]
        segments = [(s["id"], "".join(texts[s["id"]])) for s in row["segments"]]
        assert "，".join(t for _, t in segments) == final, row["unit_id"]
        unit = {"unit_id": row["unit_id"], "category": category, "subtypes": subtypes, "text": final,
                "think": think_of(lines, final), "think_on": lines is not None, "reason": why, "records": 0,
                "segments": []}
        units[row["unit_id"]] = unit
        offset = 0
        for sid, text in segments:
            begin, end = offset, offset + len(text)
            offset = end + 1  # the "，" joining segments
            if lines is None:
                think, reason = None, why
            else:
                inside, split = [], False
                for s, e, w, py in lines:
                    if e <= begin or s >= end:
                        continue
                    piece = final[max(s, begin):min(e, end)]
                    # A quote cut by the segment boundary still serves when its piece here is a whole "X的X"
                    # ("不是忘记的忘" | "而是眺望的望"); otherwise this segment hears only part of the explanation.
                    if (begin <= s and e <= end) or re.search(f"{re.escape(w)}.*的{re.escape(w)}", piece):
                        inside.append(render(piece, w, py))
                    else:
                        split = True
                think = "\n".join(inside) if inside and not split else None
                reason = "ok" if think else "quote_split" if split else "other_segment"
            unit["segments"].append({"id": sid, "text": text, "think": think, "reason": reason})
            rows.append((sid, text, unit, think, reason))
    loose = candidates(source)
    for u in gz_rows(CLEAN / source / "units.jsonl.gz"):
        if u["unit_id"] in loose:
            unit = {"unit_id": u["unit_id"], "category": "candidate", "subtypes": [], "text": u["text"], "think": None,
                    "think_on": False, "reason": "may_explain", "records": 0, "segments": []}
            units[u["unit_id"]] = unit
            rows += [(s["id"], s["text"], unit, None, "may_explain") for s in u["segments"]]
    wanted = {sid: text for sid, text, *_ in rows}
    found = {r["id"]: (r.get("text") or "").strip() for r in gz_rows(supervisions) if r["id"] in wanted}
    for sid, text, unit, think, reason in rows:
        if sid not in found:  # e.g. a segment of an evaluation recording that a candidate window still lists
            continue
        assert found[sid] == text, (sid, found[sid], text)
        unit["records"] += 1
        # The record ID the training loader gives a Lhotse supervision (as in positives.jsonl).
        yield derived, f"{derived}:{spec['split']}:{sid}", {**unit, "think": think, "think_on": think is not None,
                                                            "reason": reason}
    return units


def write_review(path: Path, units: list[dict]):
    """Every unit, think-on first, for reading."""
    order = {"corrected": 0, "rescued": 1, "consistent": 2, "uncertain": 3, "not_hit": 4, "candidate": 5}
    with open(path, "w") as f:
        for u in sorted(units, key=lambda u: (not u["think_on"] and not any(s["think"] for s in u.get("segments", [])),
                                              order[u["category"]], u["reason"], u["unit_id"])):
            if u["category"] == "candidate":
                continue
            f.write(f"## {u['unit_id']} [{u['category']} {'/'.join(u['subtypes'])}] {u['reason']} records={u['records']}\n")
            f.write(f"文本：{u['text']}\n")
            if u.get("segments") and len(u["segments"]) > 1:
                f.writelines(f"  - [{s['reason']}] {s['text']}\n"
                             + "".join(f"      {t}\n" for t in (s["think"] or "").split("\n") if t)
                             for s in u["segments"])
            elif u["think"]:
                f.write(u["think"] + "\n")
            f.write("\n")


def main():
    out, sources = Path(sys.argv[1]), sys.argv[2:]
    sources = sources or list(RECIPE["sources"])
    total = {}
    for source in sources:
        spec = RECIPE["sources"][source]
        build = json.loads((CLEAN / source / "build.json").read_text())
        rows = records_source(source, spec, build) if spec["kind"] == "records" else lhotse_source(source, spec, build)
        (out / source).mkdir(parents=True, exist_ok=True)
        summary = {"records": Counter(), "datasets": Counter()}
        with gzip.open(out / source / "think.jsonl.gz", "wt") as f:
            while True:
                try:
                    dataset, record_id, u = next(rows)
                except StopIteration as stop:
                    units = stop.value
                    break
                f.write(json.dumps({"dataset": dataset, "record_id": record_id, "unit_id": u["unit_id"],
                                    "category": u["category"], "think_on": u["think_on"], "think": u["think"],
                                    "reason": u["reason"]}, ensure_ascii=False) + "\n")
                summary["records"][f"{u['category']}:{u['reason']}"] += 1
                summary["datasets"][dataset] += 1
        units = list(units.values())
        with open(out / source / "units.jsonl", "w") as f:
            for u in units:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")
        write_review(out / source / "review.txt", units)
        summary["units"] = Counter(f"{u['category']}:{u['reason']}" for u in units)
        summary["units_without_records"] = sum(1 for u in units if not u["records"] and u["category"] != "candidate")
        summary["think_on_records"] = sum(v for k, v in summary["records"].items() if k.endswith(":ok"))
        (out / source / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        total[source] = summary
        print(source, json.dumps(summary, ensure_ascii=False))
    (out / "summary.json").write_text(json.dumps(total, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
