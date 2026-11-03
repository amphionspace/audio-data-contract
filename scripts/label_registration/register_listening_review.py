"""Register human listening-review answers as <dataset>@listening-review-v1-<date> versions plus views.

Every answer of a review page keeps its question, choices, answer, note, date, review name, audio origin (dataset,
version, record or window id, clip offsets) and the key that says what each choice means (`resolved_to`).
A version holds ONLY the reviewed records: rows copied from the parent, each with metadata.listening_review
(Lhotse custom.listening_review) = the list of answers about that record. Recordings and audio indexes stay the
parent's artifacts (referenced, never copied). The evidence artifact `listening_review` (gzip JSONL) holds all
answers of the version; answers that cannot be attached to a parent row (no record id in the source, or the id is
not among the parent's rows) live only there. Answers about customer material (business_feedback) are left out.

Inputs are the review-page directories left by the listening sessions (review.json / spec.json beside an
answers.json), the 2026-10-12 README with written conclusions, the 10.21-vs-10.22 page and the RAMC identity page.

    python scripts/label_registration/register_listening_review.py --root /workspace/data \
        --catalog catalog --data-dir <amphiondata runs dir> --scratch-dir <scratch dir> \
        --output catalog/listening_review.yaml --views views/listening_review.yaml
"""

import argparse
import copy
import gzip
import json
import re
from collections import Counter
from pathlib import Path

from common import artifact, new_version_dir, sha256, write_jsonl_gz

from audio_data_contract import load_catalog
from audio_data_contract.catalog import resolve_artifact
from audio_data_contract.declarations import write_declarations

PUBLIC_PREFIX = "/workspace/data/"
EMILIA = "emilia2_zh_dialogue_diarize"
EMILIA_MOSS = "moss-transcribe-diarize-0.9B"
EMILIA_PRO = "moss-transcribe-diarize-0.9B-pro4plus"
SAME_PERSON = "A 和 B 是不是同一个人？"
EXCLUDED_PREFIXES = ("business_feedback",)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clip_origin(audio):
    """Audio clips of an item; personal run directories are reduced to the file name."""
    clips = audio if isinstance(audio, list) else [audio]
    result = []
    for clip in clips:
        path = clip["path"] if isinstance(clip, dict) else clip
        entry = {"file": path[len(PUBLIC_PREFIX):] if path.startswith(PUBLIC_PREFIX) else Path(path).name}
        for key in ("start", "duration"):
            if isinstance(clip, dict) and key in clip:
                entry[key] = round(clip[key], 3)
        result.append(entry)
    return result


def record_id(item):
    meta = item.get("meta", "")
    if "窗口 " in meta:
        return meta.split("窗口 ", 1)[1].strip()
    return meta.split(" · ", 1)[0].strip() or item["id"]


def day(stamp):
    return stamp[:10]


def load_page(spec_rel, answers_rel, dataset, version, base, inputs, record_of=record_id):
    """Answers of one spec/review.json + answers.json page (paths relative to base)."""
    spec_path, answers_path = base / spec_rel, base / answers_rel
    spec, answers = read_json(spec_path), read_json(answers_path)
    for path in (spec_path, answers_path):
        inputs.append({"file": str(path.relative_to(base)), "sha256": sha256(path)})
    rows = []
    for item in spec["items"]:
        given = answers["answers"].get(item["id"])
        if given is None:
            continue
        choice = given.get("choice")
        rows.append({
            "review": spec["id"], "experiment": spec["title"], "date": day(given["updated"]),
            "answered_at": given["updated"], "item": item["id"], "question": item.get("question"),
            "context": item.get("context"), "choices": item.get("choices"), "answer": choice,
            "note": given.get("note"), "resolved_to": (item.get("key") or {}).get(choice),
            "origin": {"dataset_id": dataset, "version": version, "record_id": record_of(item),
                       "audio": clip_origin(item["audio"]) if "audio" in item else []},
        })
    return rows


def load_ts_hard(base_s, inputs):
    review, answers = base_s / "ts-hard-listen/review.json", base_s / "ts-hard-listen/answers.json"
    key_path = base_s / "ts-hard-listen-answer-key.json"
    for path in (review, answers, key_path):
        inputs.append({"file": str(path.relative_to(base_s)), "sha256": sha256(path)})
    spec, given, key = read_json(review), read_json(answers)["answers"], read_json(key_path)
    out = {"ts_asr_benchmark": [], "ts_asr_real": []}
    for item in spec["items"]:
        answer, solution = given.get(item["id"]), key[item["id"]]
        if answer is None:
            continue
        # 甲/乙 is randomised per item; the key says which of the two texts is the reference.
        choice = answer.get("choice")
        resolved = solution.get(choice[0]) if choice and choice[0] in "甲乙" else None
        dataset = "ts_asr_real" if solution["id"].startswith("real-") else "ts_asr_benchmark"
        out[dataset].append({
            "review": "ts-asr-hard-cases-20261026", "experiment": spec["title"], "date": day(answer["updated"]),
            "answered_at": answer["updated"], "item": item["id"], "question": item["question"],
            "context": item["context"], "choices": item["choices"], "answer": choice, "note": answer.get("note"),
            "resolved_to": resolved,
            "origin": {"dataset_id": dataset, "version": "v4-20261022", "record_id": solution["id"],
                       "section": solution["section"], "reference": solution["ref"],
                       "model_output_10.21": solution["model_10.21"], "model_output_9.26": solution["model_9.26"],
                       "audio": []},
        })
    return out


def load_1021_vs_1022(base_s, inputs):
    """Final round of the 10.21-vs-10.22 page: 'is the label right?'; business_feedback answers are excluded."""
    manifest_path, answers_path = base_s / "listen-1021-vs-1022/page/manifest.json", base_s / "listen-1021-vs-1022/page/answers.json"
    for path in (manifest_path, answers_path):
        inputs.append({"file": str(path.relative_to(base_s)), "sha256": sha256(path)})
    items = {item["id"]: item for item in read_json(manifest_path)["items"]}
    out, excluded = {}, 0
    for key, given in read_json(answers_path).items():
        if key.startswith(EXCLUDED_PREFIXES):
            excluded += 1
            continue
        pair, rest = key.split(":", 1)
        dataset, version = pair.split("@")
        item = items.get(key)
        stamp = given["time"].replace(" ", "T")
        split, record = rest.split("|", 1)
        origin = {"dataset_id": dataset, "version": version, "record_id": record, "split": split, "audio": []}
        if item:
            question = item["hint"]
            context = f"{item['kind_text']}；参考文本：{item['reference']}"
            origin.update({"reference": item["reference"], "model_output_10.21": item["out_1021"],
                           "model_output_10.22": item["out_1022"]})
        else:  # answered only in the earlier "which output is right" round; the item is not in the final manifest
            question = "10.21 与 10.22 两版输出哪一版与录音一致？（早期一轮，条目文本未保留在最终页面清单）"
            context = None
        out.setdefault((dataset, version), []).append({
            "review": "listen-1021-vs-1022", "experiment": "10.21 与 10.22 输出分歧：标注是否正确",
            "date": day(stamp), "answered_at": stamp, "item": rest, "question": question, "context": context,
            "choices": ["yes", "no", "unsure"] if item else ["10.21", "10.22", "both", "unsure"],
            "answer": given.get("label_ok") if item else given.get("which"), "note": given.get("comment") or None,
            "resolved_to": None, "previous_round": {"answer": given.get("answer"), "which": given.get("which")},
            "origin": origin,
        })
    return out, excluded


def load_readme_1012(path, inputs, base):
    """Seven written conclusions (WenetSpeech) and one for Emilia2 in the 2026-10-12 README."""
    inputs.append({"file": str(path.relative_to(base)), "sha256": sha256(path)})
    out = {"wenetspeech_diarize": [], EMILIA: []}
    for number, body in re.findall(r"^## (\d\d) `audio/\d\d\.wav`\n(.*?)(?=^## |\Z)", path.read_text(encoding="utf-8"), re.MULTILINE | re.DOTALL):
        source = re.search(r"^- (.+)$", body, re.MULTILINE).group(1)
        parts = {name: text for name, text in re.findall(r"^- ([AB])：“(.*)”$", body, re.MULTILINE)}
        answer = re.search(r"^答：(.*)$", body, re.MULTILINE).group(1).strip()
        dataset = EMILIA if source.startswith("Emilia2") else "wenetspeech_diarize"
        version = EMILIA_PRO if dataset == EMILIA else "moss-transcribe-diarize-0.9B"
        out[dataset].append({
            "review": "listen-review-20261012", "experiment": "说话人归属：本地 MOSS 与 Pro 意见相反处",
            "date": "2026-10-12", "answered_at": None, "item": number, "question": SAME_PERSON,
            "context": f"{source}；A：{parts.get('A')}；B：{parts.get('B')}", "choices": ["是", "否", "听不出"],
            "answer": answer, "note": None, "resolved_to": None,
            "origin": {"dataset_id": dataset, "version": version, "record_id": None,
                       "note": "the README names the corpus and the two utterance texts, not the window id", "audio": []},
        })
    return out


def load_ramc(scratch, inputs):
    """Same-voice questions about magicdata_ramc speaker units (A + 0.6 s silence + B)."""
    base = scratch / "ramc-pools/listen"
    answers_path, key_path = base / "page/answers.json", base / "key.json"
    summary = Path("/workspace/data/datasets/ts_scene_pool/source/ramc-voice-identities-20261028/listening-20261028.json")
    for path, name in ((answers_path, "ramc-pools/listen/page/answers.json"), (key_path, "ramc-pools/listen/key.json"),
                       (summary, "ts_scene_pool/source/ramc-voice-identities-20261028/listening-20261028.json")):
        inputs.append({"file": name, "sha256": sha256(path)})
    answers, key, listed = read_json(answers_path), read_json(key_path), read_json(summary)
    if any(listed["items"][i]["answer"] != answers[a["id"]]["same_person"] for i, a in enumerate(listed["items"])):
        raise SystemExit("listening-20261028.json disagrees with the page answers")
    rows = []
    for item_id, given in sorted(answers.items()):
        pair = key[item_id]
        units = []
        for role in ("A", "B"):
            unit = pair[role]
            parts = unit["unit"].split("|")
            entry = {"role": role, "speaker": parts[0], "heldout_split": parts[1] if len(parts) == 3 else None,
                     "recording_id": "magicdata_ramc_" + parts[-1].removesuffix(".wav"),
                     "start": unit["start_s"], "end": round(unit["start_s"] + unit["duration_s"], 3),
                     "clip_offset": unit["clip_offset_s"]}
            units.append(entry)
        rows.append({
            "review": "ramc-voice-identities-20261028", "experiment": "RAMC 说话人编号是否同一人（声纹阈值 0.60 核对）",
            "date": day(given["time"]), "answered_at": given["time"].replace(" ", "T"), "item": item_id,
            "question": "A 和 B 是同一个人吗？（盲听，A + 0.6 s 静音 + B，原音量）",
            "context": None, "choices": ["same", "different", "unsure"], "answer": given["same_person"],
            "note": given["comment"] or None, "resolved_to": None,
            "origin": {"dataset_id": "magicdata_ramc", "version": "speaker-identity-v1-20261028", "record_id": None,
                       "kind": pair["kind"], "cosine": pair["cosine"], "units": units, "audio": []},
        })
    return rows


def collect(data_dir, scratch_dir):
    """(dataset, parent version) -> {"rows": answers, "inputs": input file hashes}; plus the excluded count."""
    groups = {}

    def add(dataset, version, rows, inputs):
        group = groups.setdefault((dataset, version), {"rows": [], "inputs": []})
        group["rows"].extend(rows)
        group["inputs"].extend(i for i in inputs if i not in group["inputs"])

    def page(spec_rel, answers_rel, dataset, version):
        inputs = []
        add(dataset, version, load_page(spec_rel, answers_rel, dataset, version, data_dir, inputs), inputs)

    emilia_dir = "emilia2-zh-dialogue-diarize-20261010/listen-review"
    split_dir = "similar-voice-views-20261014/listen-review/speaker-split-20261015"
    page(f"{emilia_dir}/speaker-merge-20261014/spec.json", f"{emilia_dir}/speaker-merge-20261014/answers.json", EMILIA, EMILIA_MOSS)
    page(f"{split_dir}/spec.json", f"{split_dir}/answers.json", EMILIA, EMILIA_MOSS)
    for name in ("pro-diff-20261014", "pro-overlap-20261014"):
        page(f"{emilia_dir}/{name}/review.json", f"{emilia_dir}/{name}/answers.json", EMILIA, EMILIA_PRO)
    inputs = []
    readme = load_readme_1012(data_dir / "listen-review-20261012/README.md", inputs, data_dir)
    add("wenetspeech_diarize", "moss-transcribe-diarize-0.9B", readme["wenetspeech_diarize"], inputs)
    add(EMILIA, EMILIA_PRO, readme[EMILIA], inputs)
    chuan_dir = "wenetspeech-chuan-qwen-20261023/listen-review"
    for answers in sorted((data_dir / chuan_dir).glob("qwen-diff-*/answers.json")):
        name = answers.parent.name
        page(f"{chuan_dir}/{name}.json", f"{chuan_dir}/{name}/answers.json", "wenetspeech_chuan", "extracted-20261021")
    single = "police-terms-single-20261022/listen-review/review-20261022"
    page(f"{single}/review.json", f"{single}/answers.json", "police_terms_single", "v1-20261022")
    train = "police-terms-single-train-20261023/listen-review/review-20261023"
    page(f"{train}/review.json", f"{train}/answers.json", "police_terms_single_train", "v1-20261023")
    inputs = []
    hard = load_ts_hard(scratch_dir, inputs)
    add("ts_asr_benchmark", "v4-20261022", hard["ts_asr_benchmark"], inputs)
    add("ts_asr_real", "v4-20261022", hard["ts_asr_real"], inputs)
    inputs = []
    versus, excluded = load_1021_vs_1022(scratch_dir, inputs)
    for (dataset, version), rows in versus.items():
        add(dataset, version, rows, inputs)
    inputs = []
    add("magicdata_ramc", "speaker-identity-v1-20261028", load_ramc(scratch_dir, inputs), inputs)
    return groups, excluded


ROW_KINDS = ("audio-records", "lhotse-supervisions", "lhotse-cuts")
ANSWER_DROP = ("dataset_id", "version", "record_id")


def row_payload(answer):
    """The answer as stored on a row: everything except what the row already says."""
    payload = {k: v for k, v in answer.items() if k not in ("origin", "attached_rows", "attached", "attached_row_ids")}
    payload["origin"] = {k: v for k, v in answer["origin"].items() if k not in ANSWER_DROP}
    return payload


def attach(catalog, roots, spec, rows, out_dir):
    """Copy the reviewed rows of every row artifact of the parent; returns (new artifacts, touched names, stats)."""
    dataset, version = spec.dataset_id, spec.version
    row_artifacts = [a for a in spec.to_dict()["artifacts"] if a["kind"] in ROW_KINDS]
    by_id, by_unit = {}, []
    for answer in rows:
        origin = answer["origin"]
        if origin.get("record_id"):
            ids = {origin["record_id"], f"emilia2_zh_dialogue-train_120s-{origin['record_id']}"}
            for rid in ids:
                by_id.setdefault(rid, []).append(answer)
        for unit in origin.get("units", []):
            if unit["heldout_split"] is None:
                by_unit.append((unit, answer))
    new_artifacts, touched, attached_answers, kept_rows = [], {}, set(), 0
    for art in row_artifacts:
        path = resolve_artifact(catalog, dataset, version, art["name"], roots)
        found = []
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                hits = list(by_id.get(row.get("id"), []))
                matched = [(row_payload(a), a) for a in hits]
                for unit, answer in by_unit:
                    if (row.get("speaker") == unit["speaker"] and row.get("recording_id") == unit["recording_id"]
                            and row["start"] < unit["end"] and row["start"] + row["duration"] > unit["start"]):
                        payload = row_payload(answer)
                        payload["origin"] = {**payload["origin"], "unit_role": unit["role"]}
                        matched.append((payload, answer))
                if not matched:
                    continue
                for _, answer in matched:
                    attached_answers.add(id(answer))
                    answer.setdefault("attached_rows", []).append(row["id"])
                found.append((row, [m[0] for m in matched]))
        if not found:
            continue
        for row, payloads in found:
            target = row.setdefault("custom", {}) if art["kind"] != "audio-records" else row.setdefault("metadata", {})
            target["listening_review"] = payloads
        name = f"{art['name']}_listening"
        relative = f"{name}.jsonl.gz"
        count, size, digest = write_jsonl_gz(out_dir / relative, (r for r, _ in found))
        new_artifacts.append(artifact(name, art["kind"], dataset, out_dir.name, relative, size, digest,
                                      record_count=count, source=f"{dataset}@{version}:{art['name']}"))
        touched[art["name"]] = (name, count)
        kept_rows += count
    return new_artifacts, touched, attached_answers, kept_rows


def build_version(catalog, roots, spec, rows, root, inputs):
    dataset, parent = spec.dataset_id, spec.version
    date = max(r["date"] for r in rows).replace("-", "")
    version = f"listening-review-v1-{date}"
    out_dir = new_version_dir(root, dataset, version)
    rows.sort(key=lambda r: (r["review"], r["item"]))
    new_artifacts, touched, attached, kept_rows = attach(catalog, roots, spec, rows, out_dir)
    for answer in rows:
        answer["attached"] = id(answer) in attached
        answer["attached_row_ids"] = answer.pop("attached_rows", [])
    count, size, digest = write_jsonl_gz(out_dir / "listening_review.jsonl.gz", rows)
    if count != len(rows):
        raise SystemExit(f"{dataset}@{version}: wrote {count} of {len(rows)} rows")
    source = spec.to_dict()
    kept = [copy.deepcopy(a) for a in source["artifacts"]
            if a["kind"] == "lhotse-recordings" or a["kind"] == "audio-index" or "audio-index" in a["name"]]
    keep_names = {a["name"] for a in kept}
    splits = {}
    for split_name, split in source["splits"].items():
        roles = split.get("artifacts", {})
        hit = {n for names in roles.values() for n in names if n in touched}
        if not hit:
            continue
        new_roles = {}
        for role, names in roles.items():
            mapped = [touched[n][0] if n in touched else n for n in names if n in touched or (n in keep_names)]
            if mapped:
                new_roles[role] = mapped
        records = sum(touched[n][1] for n in hit)
        splits[split_name] = {"artifacts": new_roles, "statistics": {"records": records}}
        for key in ("task",):
            if key in split:
                splits[split_name][key] = split[key]
    attached_n = sum(1 for r in rows if r["attached"])
    reviews = Counter(r["review"] for r in rows)
    note = "" if attached_n == count else (
        f"其中 {count - attached_n} 条没有记录 ID 或记录不在父版本数据行里，无法挂到行上，只在证据文件里。")
    entry = {
        "schema_version": source["schema_version"], "dataset_id": dataset, "version": version,
        "languages": list(source["languages"]), "tasks": list(source["tasks"]), "aliases": [],
        "artifacts": kept + new_artifacts + [
            artifact("listening_review", "quality-report", dataset, version, "listening_review.jsonl.gz", size, digest,
                     record_count=count)],
        "splits": splits,
        "provenance": {
            "preparation_status": "prepared", "lineage_status": "exact", "materialization": "full",
            "source": f"{dataset}@{parent}",
            "description": (
                f"{dataset}@{parent} 中被人工听审过的 {kept_rows} 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），"
                f"每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表："
                f"问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。"
                f"共 {count} 条答案（{'、'.join(f'{n} {c} 条' for n, c in sorted(reviews.items()))}），"
                f"{attached_n} 条已挂到数据行。{note}证据文件 listening_review.jsonl.gz 含该版本全部答案。"
                "只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py。"),
            "facts": {"answers": count, "answers_attached": attached_n, "answers_evidence_only": count - attached_n,
                      "rows": kept_rows, "reviews": dict(reviews)},
        },
    }
    view = {
        "schema_version": "dataset-view/1.0", "view_id": f"{dataset}/listening-review", "version": version,
        "source": {"dataset_id": dataset, "version": parent}, "result": {"dataset_id": dataset, "version": version},
        "materialization": "full", "lineage_status": "exact",
        "transforms": [{
            "name": "listening-review", "version": "v1", "kind": "annotate",
            "writes": ["$membership", "metadata.listening_review"],
            "parameters": {
                "kept": "only the rows whose record or window id has a listening-review answer",
                "rows": kept_rows, "answers": count, "answers_attached": attached_n,
                "answers_evidence_only": count - attached_n, "reviews": dict(reviews),
                "tool": "scripts/label_registration/register_listening_review.py", "label_inputs": inputs}}],
        "provenance": {"registered_at": "2026-11-03"},
    }
    return entry, view


def write_with_comment(path, rows, comment):
    write_declarations(path, json.loads(json.dumps(rows)))  # a JSON round trip drops shared objects (YAML anchors)
    text = Path(path).read_text(encoding="utf-8")
    temporary = Path(path).with_name(Path(path).name + ".tmp")
    temporary.write_text(f"# {comment}\n{text}", encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--scratch-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--roots-file", type=Path, help="default: <root>/registry/roots.json")
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    roots = json.loads((args.roots_file or args.root / "registry/roots.json").read_text())
    groups, excluded = collect(args.data_dir, args.scratch_dir)
    entries, views = [], []
    for (dataset, version), group in sorted(groups.items()):
        entry, view = build_version(catalog, roots, catalog.get(dataset, version), group["rows"], args.root, group["inputs"])
        entries.append(entry)
        views.append(view)
        facts = entry["provenance"]["facts"]
        print(f"{dataset}@{entry['version']}: rows {facts['rows']}, answers {facts['answers']} "
              f"(attached {facts['answers_attached']}, evidence only {facts['answers_evidence_only']})", flush=True)
    write_with_comment(args.output, entries, "人工听审答案：被听过的数据行及其 metadata.listening_review，完整答案在证据文件 listening_review")
    write_with_comment(args.views, views, "人工听审答案各版本的 view：只保留被听过的记录并写入 metadata.listening_review")
    print(f"excluded business_feedback answers: {excluded}")


if __name__ == "__main__":
    main()
