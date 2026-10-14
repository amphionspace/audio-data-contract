"""Periodic storage audit: scan usage and flag data outside the registry.

The audit only reports; it never deletes. A scan walks the filesystem once and
keeps per-directory totals only where the zone file needs them, so the snapshot
stays small even for hundreds of millions of files.
"""

from __future__ import annotations

import base64
import csv
import fnmatch
import gzip
import hashlib
import hmac
import json
import os
import pwd
import queue
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .catalog import load_catalog
from .errors import ContractError
from .roots import load_roots, resolve_root_path

WEBHOOK_ENV = "STORAGE_AUDIT_FEISHU_WEBHOOK"
SECRET_ENV = "STORAGE_AUDIT_FEISHU_SECRET"
SNAPSHOT_NAME = "snapshot.jsonl.gz"
CONTENTS = {"whole", "listed", "per-child"}
_UNITS = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40, "P": 1 << 50}


def parse_size(value: int | str | None) -> int | None:
    """Bytes from an int or a binary-suffixed string such as ``50G``."""
    if value is None or isinstance(value, int):
        return value
    text = str(value).strip().upper().removesuffix("IB").removesuffix("B")
    if text and text[-1] in _UNITS:
        return int(float(text[:-1]) * _UNITS[text[-1]])
    return int(text)


def format_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError


@dataclass(frozen=True)
class Entry:
    path: str
    contents: str = "whole"
    owner: str | None = None
    budget: int | None = None
    child_budget: int | None = None
    stale_days: int | None = None
    expires: date | None = None
    note: str | None = None
    strict: bool = False


@dataclass
class Zones:
    scan_root: str
    base_depth: int
    entries: list[Entry]
    units: set[str]
    missing: list[dict]
    min_bytes: int
    growth_min_bytes: int
    watermark_percent: float

    def __post_init__(self) -> None:
        claimed = [entry.path for entry in self.entries] + list(self.units)
        # Proper ancestors of every claimed path: they hold registered data
        # somewhere below, so only their other children can be unregistered.
        self.ancestors: set[str] = set()
        for path in claimed:
            parent = os.path.dirname(path)
            while _is_within(parent, self.scan_root) and parent not in self.ancestors:
                self.ancestors.add(parent)
                if parent == self.scan_root:
                    break
                parent = os.path.dirname(parent)
        # Directories whose children get their own snapshot rows.
        self.expand = self.ancestors | {
            entry.path
            for entry in self.entries
            if entry.contents != "whole" or entry.stale_days is not None
        }
        self._by_path = {entry.path: entry for entry in self.entries}

    def depth(self, path: str) -> int:
        if path == self.scan_root:
            return 0
        return len(os.path.relpath(path, self.scan_root).split(os.sep))

    def keeps(self, path: str) -> bool:
        return (
            self.depth(path) <= self.base_depth
            or os.path.dirname(path) in self.expand
        )

    def entry_for(self, path: str) -> Entry | None:
        for candidate in _with_parents(path, self.scan_root):
            if candidate in self._by_path:
                return self._by_path[candidate]
        return None

    def is_strict(self, path: str) -> bool:
        """Under a strict entry every unregistered item is reported, any size."""
        return any(
            entry.strict and _is_within(path, entry.path) for entry in self.entries
        )

    def classify(self, path: str) -> tuple[str, Entry | None]:
        """One of registered, catalog, container, or unregistered."""
        entry = self.entry_for(path)
        if any(candidate in self.units for candidate in _with_parents(path, "/")):
            return "catalog", entry
        if entry is not None and (
            entry.contents == "whole"
            or (entry.contents == "per-child" and path != entry.path)
        ):
            return "registered", entry
        if path in self.ancestors or (entry is not None and path == entry.path):
            return "container", entry
        return "unregistered", entry


def _is_within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _user(uid: int | None) -> str | None:
    if uid is None:
        return None
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def _with_parents(path: str, stop: str):
    """Yield ``path`` and its ancestors down to ``stop`` (inclusive)."""
    while True:
        yield path
        if path == stop or path in ("/", ""):
            return
        path = os.path.dirname(path)


def _catalog_units(config: dict) -> tuple[set[str], list[dict]]:
    """Directories claimed by registered catalog artifacts, plus missing ones."""
    catalog = load_catalog(config["path"])
    roots = load_roots(config.get("roots"))
    patterns = [Path(item).parts for item in config.get("unit_patterns", [])]
    units: set[str] = set()
    missing: list[dict] = []
    for spec in catalog:
        for artifact in spec.artifacts:
            where = f"{spec.key}:{artifact.name}"
            try:
                path = resolve_root_path(
                    artifact.root_alias, artifact.relative_path, roots, where
                )
            except ContractError as exc:
                missing.append({"artifact": where, "path": None, "error": str(exc)})
                continue
            if not os.path.lexists(path):
                missing.append(
                    {"artifact": where, "path": str(path), "error": "path not found"}
                )
                continue
            for pattern in patterns:
                if len(path.parts) > len(pattern) and all(
                    fnmatch.fnmatchcase(part, glob)
                    for part, glob in zip(path.parts, pattern)
                ):
                    units.add(str(Path(*path.parts[: len(pattern)])))
                    break
            else:
                units.add(str(path if path.is_dir() else path.parent))
    # A shared directory (e.g. a dataset's source/ audio, referenced by its
    # version records) is claimed once any sibling unit is registered.
    for item in config.get("shared_patterns", []):
        pattern = Path(item).parts
        for unit in list(units):
            parts = Path(unit).parts
            if len(parts) >= len(pattern) and all(
                fnmatch.fnmatchcase(part, glob)
                for part, glob in zip(parts, pattern[:-1])
            ):
                shared = Path(*parts[: len(pattern) - 1], pattern[-1])
                if shared.exists():
                    units.add(str(shared))
    return units, missing


def load_zones(path: str | Path) -> Zones:
    try:
        data = YAML(typ="safe").load(Path(path).read_text(encoding="utf-8"))
    except (OSError, YAMLError) as exc:
        raise ContractError(f"failed to load zones file {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != "storage-zones/1.0":
        raise ContractError("zones file must declare schema_version: storage-zones/1.0")
    scan_root = os.path.normpath(data["scan_root"])
    entries = []
    for row in data.get("entries", []):
        contents = row.get("contents", "whole")
        if contents not in CONTENTS:
            raise ContractError(
                f"{row.get('path')}: contents must be one of {sorted(CONTENTS)}"
            )
        entry_path = os.path.normpath(row["path"])
        if not _is_within(entry_path, scan_root):
            raise ContractError(f"{entry_path}: entry is outside scan_root {scan_root}")
        expires = row.get("expires")
        entries.append(
            Entry(
                path=entry_path,
                contents=contents,
                owner=row.get("owner"),
                budget=parse_size(row.get("budget")),
                child_budget=parse_size(row.get("child_budget")),
                stale_days=row.get("stale_days"),
                expires=date.fromisoformat(str(expires)) if expires else None,
                note=row.get("note"),
                strict=bool(row.get("strict", False)),
            )
        )
    units, missing = (
        _catalog_units(data["catalog"]) if data.get("catalog") else (set(), [])
    )
    thresholds = data.get("thresholds", {})
    return Zones(
        scan_root=scan_root,
        base_depth=int(data.get("base_depth", 2)),
        entries=entries,
        units=units,
        missing=missing,
        min_bytes=parse_size(thresholds.get("min_bytes", "50G")),
        growth_min_bytes=parse_size(thresholds.get("growth_min_bytes", "1T")),
        watermark_percent=float(thresholds.get("watermark_percent", 90)),
    )


# --------------------------------------------------------------------- scan


def scan(zones: Zones, workers: int = 32) -> tuple[dict[str, dict], list[dict]]:
    """Walk ``scan_root`` once; return subtree totals for kept directories."""
    root = zones.scan_root
    root_stat = os.lstat(root)
    work: queue.Queue = queue.Queue()
    errors: list[dict] = []
    seen_links: set[tuple[int, int]] = set()
    links_lock = threading.Lock()
    partials: list[dict[str, list]] = []
    owners: dict[str, int] = {root: root_stat.st_uid}

    def add(totals, key, size, files, dirs, mtime):
        row = totals.get(key)
        if row is None:
            totals[key] = [size, files, dirs, mtime]
        else:
            row[0] += size
            row[1] += files
            row[2] += dirs
            row[3] = max(row[3], mtime)

    def run() -> None:
        totals: dict[str, list] = {}
        partials.append(totals)
        while True:
            item = work.get()
            if item is None:
                work.task_done()
                return
            path, key = item
            try:
                with os.scandir(path) as listing:
                    for entry in listing:
                        st = entry.stat(follow_symlinks=False)
                        if entry.is_dir(follow_symlinks=False):
                            if st.st_dev != root_stat.st_dev:
                                continue
                            child = entry.path
                            if zones.keeps(child):
                                owners[child] = st.st_uid
                                add(totals, child, 0, 0, 1, st.st_mtime)
                                work.put((child, child))
                            else:
                                add(totals, key, 0, 0, 1, st.st_mtime)
                                work.put((child, key))
                            continue
                        if st.st_nlink > 1:
                            with links_lock:
                                if (st.st_dev, st.st_ino) in seen_links:
                                    continue
                                seen_links.add((st.st_dev, st.st_ino))
                        add(totals, key, st.st_size, 1, 0, st.st_mtime)
            except OSError as exc:
                errors.append({"path": path, "error": str(exc)})
            finally:
                work.task_done()

    threads = [threading.Thread(target=run, daemon=True) for _ in range(workers)]
    for thread in threads:
        thread.start()
    work.put((root, root))
    work.join()
    for _ in threads:
        work.put(None)
    for thread in threads:
        thread.join()

    own: dict[str, list] = {root: [0, 0, 0, root_stat.st_mtime]}
    for totals in partials:
        for key, (size, files, dirs, mtime) in totals.items():
            add(own, key, size, files, dirs, mtime)
    # Files not inside any kept child, i.e. loose files of each kept directory.
    loose = {key: (row[0], row[1]) for key, row in own.items()}
    # Roll each kept directory into its parent, deepest first.
    for key in sorted(own, key=zones.depth, reverse=True):
        if key != root:
            add(own, os.path.dirname(key), *own[key])
    nodes = {
        key: {
            "bytes": size,
            "files": files,
            "dirs": dirs,
            "max_mtime": int(mtime),
            "uid": owners.get(key),
            "loose_bytes": loose[key][0],
            "loose_files": loose[key][1],
        }
        for key, (size, files, dirs, mtime) in own.items()
    }
    return nodes, errors


def write_snapshot(
    output_dir: str | Path, nodes: dict[str, dict], errors: list[dict], meta: dict
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = Path(output_dir) / stamp
    target.mkdir(parents=True, exist_ok=False)
    partial = target / (SNAPSHOT_NAME + ".partial")
    with gzip.open(partial, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "meta", **meta}) + "\n")
        for path in sorted(nodes):
            row = {"type": "node", "path": path, **nodes[path]}
            stream.write(json.dumps(row) + "\n")
        for error in errors:
            stream.write(json.dumps({"type": "error", **error}) + "\n")
    partial.rename(target / SNAPSHOT_NAME)
    return target / SNAPSHOT_NAME


def read_snapshot(path: str | Path) -> tuple[dict, dict[str, dict], list[dict]]:
    meta: dict = {}
    nodes: dict[str, dict] = {}
    errors: list[dict] = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            kind = row.pop("type")
            if kind == "meta":
                meta = row
            elif kind == "node":
                nodes[row.pop("path")] = row
            else:
                errors.append(row)
    return meta, nodes, errors


def snapshots(output_dir: str | Path) -> list[Path]:
    return sorted(Path(output_dir).glob(f"*/{SNAPSHOT_NAME}"))


# ------------------------------------------------------------------- report


def watermark(path: str) -> dict:
    st = os.statvfs(path)
    used = (st.f_blocks - st.f_bfree) * st.f_frsize
    avail = st.f_bavail * st.f_frsize
    return {
        "path": path,
        "used_bytes": used,
        "avail_bytes": avail,
        "used_percent": round(100 * used / (used + avail), 1) if used + avail else 0.0,
    }


def find_issues(
    zones: Zones,
    nodes: dict[str, dict],
    previous: dict[str, dict] | None = None,
    *,
    now: float | None = None,
    today: date | None = None,
) -> list[dict]:
    """Findings sorted by category then size; every row has the same keys."""
    now = time.time() if now is None else now
    today = date.today() if today is None else today
    findings: list[dict] = []

    def finding(category, path, size, entry, detail, owner=None):
        findings.append(
            {
                "category": category,
                "path": path,
                "bytes": size,
                "owner": owner or (entry.owner if entry else None),
                "detail": detail,
            }
        )

    classes = {path: zones.classify(path) for path in nodes}
    for path, (kind, entry) in classes.items():
        parent = os.path.dirname(path)
        strict = zones.is_strict(path)
        if (
            kind == "unregistered"
            and classes.get(parent, ("",))[0] != "unregistered"
            and (strict or nodes[path]["bytes"] >= zones.min_bytes)
        ):
            # Unregistered data has no registered owner: name whoever owns it on disk.
            finding(
                "unregistered", path, nodes[path]["bytes"], entry, "未在注册表中",
                _user(nodes[path].get("uid")),
            )
        if kind == "container" and strict and nodes[path].get("loose_files"):
            finding(
                "unregistered", path, nodes[path]["loose_bytes"], entry,
                f"目录下直接存放了 {nodes[path]['loose_files']} 个未登记文件",
                _user(nodes[path].get("uid")),
            )

    for entry in zones.entries:
        node = nodes.get(entry.path)
        if node is None:
            if not os.path.lexists(entry.path):
                finding("missing", entry.path, 0, entry, "登记的路径不存在")
            continue
        if entry.budget is not None and node["bytes"] > entry.budget:
            finding(
                "over_budget", entry.path, node["bytes"], entry,
                f"预算 {format_size(entry.budget)}",
            )
        if entry.expires is not None and entry.expires < today:
            finding(
                "expired", entry.path, node["bytes"], entry,
                f"登记已于 {entry.expires.isoformat()} 到期",
            )
        children = [
            path for path in nodes if os.path.dirname(path) == entry.path
        ]
        for child in children:
            if (
                entry.contents == "per-child"
                and entry.child_budget is not None
                and nodes[child]["bytes"] > entry.child_budget
            ):
                finding(
                    "over_budget", child, nodes[child]["bytes"], entry,
                    f"单目录预算 {format_size(entry.child_budget)}",
                )
            age_days = (now - nodes[child]["max_mtime"]) / 86400
            if (
                entry.stale_days is not None
                and age_days > entry.stale_days
                and nodes[child]["bytes"] >= zones.min_bytes
            ):
                finding(
                    "stale", child, nodes[child]["bytes"], entry,
                    f"{int(age_days)} 天未修改",
                )

    for item in zones.missing:
        findings.append(
            {
                "category": "missing",
                "path": item["path"] or "",
                "bytes": 0,
                "owner": None,
                "detail": f"{item['artifact']}: {item['error']}",
            }
        )

    if previous is not None:
        deltas = {
            path: node["bytes"] - previous.get(path, {}).get("bytes", 0)
            for path, node in nodes.items()
        }
        grown = {
            path for path, delta in deltas.items() if delta >= zones.growth_min_bytes
        }
        # Report the deepest growing directory, not every ancestor above it.
        parents_of_grown = {os.path.dirname(path) for path in grown}
        for path in sorted(grown - parents_of_grown):
            finding(
                "growth", path, nodes[path]["bytes"], zones.entry_for(path),
                f"较上次增长 {format_size(deltas[path])}",
            )

    order = ["unregistered", "over_budget", "growth", "stale", "expired", "missing"]
    findings.sort(key=lambda row: (order.index(row["category"]), -row["bytes"]))
    return findings


LABELS = {
    "unregistered": "未注册",
    "over_budget": "超预算",
    "growth": "增长异常",
    "stale": "长期未修改",
    "expired": "登记过期",
    "missing": "注册失效",
}


def usage_rows(zones: Zones, nodes: dict[str, dict]) -> list[tuple[str, dict]]:
    """Registered zones, plus each personal directory of a per-child zone."""
    rows = []
    for entry in zones.entries:
        if entry.path in nodes:
            rows.append((entry.path, nodes[entry.path]))
        if entry.contents == "per-child":
            children = [
                (path, node) for path, node in nodes.items()
                if os.path.dirname(path) == entry.path
            ]
            rows += sorted(children, key=lambda item: -item[1]["bytes"])
    return rows


def render_markdown(
    meta: dict, findings: list[dict], usage: dict, overview=()
) -> str:
    lines = [
        "# 存储巡检报告",
        "",
        f"- 扫描时间：{meta.get('started_at')}（耗时 {meta.get('seconds')} 秒）",
        f"- 扫描范围：`{meta.get('scan_root')}`，共 {meta.get('files')} 个文件、"
        f"{format_size(meta.get('bytes', 0))}，读取失败 {meta.get('errors')} 处",
        f"- 总水位：{usage['used_percent']}%（已用 {format_size(usage['used_bytes'])}，"
        f"剩余 {format_size(usage['avail_bytes'])}）",
        "",
    ]
    if overview:
        lines += ["## 用量概览", "", "| 路径 | 大小 | 文件数 |", "|---|---:|---:|"]
        lines += [
            f"| `{path}` | {format_size(node['bytes'])} | {node['files']} |"
            for path, node in overview
        ]
        lines.append("")
    for category, label in LABELS.items():
        rows = [row for row in findings if row["category"] == category]
        if not rows:
            continue
        lines += [f"## {label}（{len(rows)}）", "", "| 路径 | 大小 | 负责人 | 说明 |"]
        lines.append("|---|---:|---|---|")
        for row in rows:
            lines.append(
                f"| `{row['path']}` | {format_size(row['bytes'])} | "
                f"{row['owner'] or '-'} | {row['detail']} |"
            )
        lines.append("")
    if not findings:
        lines.append("未发现异常。")
    return "\n".join(lines) + "\n"


def write_report(
    snapshot: Path, meta: dict, findings: list[dict], usage: dict, overview=()
) -> Path:
    report = snapshot.parent / "report.md"
    report.write_text(
        render_markdown(meta, findings, usage, overview), encoding="utf-8"
    )
    table = snapshot.parent / "findings.csv"
    with table.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, ["category", "path", "bytes", "owner", "detail"]
        )
        writer.writeheader()
        writer.writerows(findings)
    return report


def summary_markdown(findings: list[dict], usage: dict, report: Path | None) -> str:
    counts = " · ".join(
        f"{label} {sum(row['category'] == key for row in findings)}"
        for key, label in LABELS.items()
    )
    lines = [f"**总水位 {usage['used_percent']}%**，剩余 {format_size(usage['avail_bytes'])}"]
    if findings:
        lines.append(counts)
    top = [row for row in findings if row["category"] == "unregistered"][:10]
    if top:
        lines.append("**未注册 Top 10**")
        lines += [f"- {row['path']}  {format_size(row['bytes'])}" for row in top]
    budget = [row for row in findings if row["category"] == "over_budget"][:5]
    if budget:
        lines.append("**超预算**")
        lines += [
            f"- {row['path']}  {format_size(row['bytes'])}（{row['detail']}）"
            for row in budget
        ]
    if report is not None:
        lines.append(f"完整报告：{report}")
    return "\n".join(lines)


def notify_feishu(title: str, markdown: str, environ=None) -> None:
    environment = os.environ if environ is None else environ
    webhook = environment.get(WEBHOOK_ENV)
    if not webhook:
        raise ContractError(f"set {WEBHOOK_ENV} to send Feishu notifications")
    payload: dict = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": markdown}}
            ],
        },
    }
    secret = environment.get(SECRET_ENV)
    if secret:
        stamp = str(int(time.time()))
        key = f"{stamp}\n{secret}".encode()
        payload["timestamp"] = stamp
        payload["sign"] = base64.b64encode(
            hmac.new(key, digestmod=hashlib.sha256).digest()
        ).decode()
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read() or b"{}")
    if body.get("code", 0) != 0:
        raise ContractError(f"Feishu webhook rejected the message: {body}")


# ---------------------------------------------------------------------- cli


def run(args) -> int:
    zones = load_zones(args.zones)
    if args.action == "watermark":
        usage = watermark(zones.scan_root)
        alert = usage["used_percent"] >= zones.watermark_percent
        if alert and args.notify:
            notify_feishu(
                "存储水位告警",
                f"`{zones.scan_root}` 已用 **{usage['used_percent']}%**"
                f"（阈值 {zones.watermark_percent}%），"
                f"剩余 {format_size(usage['avail_bytes'])}",
            )
        print(json.dumps({**usage, "alert": alert}, sort_keys=True))
        return 0
    if args.action == "scan":
        started = time.time()
        nodes, errors = scan(zones, workers=args.workers)
        root = nodes[zones.scan_root]
        meta = {
            "scan_root": zones.scan_root,
            "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "seconds": round(time.time() - started),
            "bytes": root["bytes"],
            "files": root["files"],
            "nodes": len(nodes),
            "errors": len(errors),
        }
        path = write_snapshot(args.output_dir, nodes, errors, meta)
        print(json.dumps({"snapshot": str(path), **meta}, sort_keys=True))
        return 0
    if args.action == "report":
        history = snapshots(args.output_dir)
        current = Path(args.snapshot) if args.snapshot else (history or [None])[-1]
        if current is None:
            raise ContractError(f"no snapshot found under {args.output_dir}")
        meta, nodes, _ = read_snapshot(current)
        earlier = [path for path in history if path.parent.name < current.parent.name]
        previous = read_snapshot(earlier[-1])[1] if earlier else None
        findings = find_issues(zones, nodes, previous)
        usage = watermark(zones.scan_root)
        report = write_report(
            current, meta, findings, usage, usage_rows(zones, nodes)
        )
        if args.notify:
            notify_feishu("存储巡检", summary_markdown(findings, usage, report))
        counts = {key: sum(r["category"] == key for r in findings) for key in LABELS}
        print(json.dumps({"report": str(report), **counts}, sort_keys=True))
        return 0
    raise AssertionError(args.action)
