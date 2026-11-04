import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("cos_mirror", SCRIPTS / "cos_mirror.py")
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


def test_local_files_follow_cos_key_order(tmp_path):
    for name in ("a/x", "a-b", "a.txt", "a0", "b/c/d", ".amphion-bucket-" + "0" * 32 + "/t"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"1" * len(name))
    (tmp_path / "link").symlink_to(tmp_path / "a0")
    skipped = []

    keys = [key for key, _, _ in mirror.local_files(str(tmp_path), skipped)]

    assert keys == sorted(keys) == ["a-b", "a.txt", "a/x", "a0", "b/c/d"]
    assert skipped == [str(tmp_path / "link")]


def test_outermost_drops_nested_directories():
    paths = ["datasets/a/v1", "datasets/a-b/v1", "datasets/a", "datasets/a/v1/x", "DATA/z"]

    assert mirror.outermost(paths) == ["DATA/z", "datasets/a", "datasets/a-b/v1"]


def test_merge_pairs_local_and_remote_by_key():
    local = [("a", 1, "/a"), ("b", 2, "/b"), ("d", 4, "/d")]
    remote = [("a", 1), ("b", 3), ("c", 9)]

    assert list(mirror.merge(iter(local), iter(remote))) == [
        ("a", 1, "/a", 1),
        ("b", 2, "/b", 3),
        ("c", None, None, 9),
        ("d", 4, "/d", None),
    ]


def test_known_mirrors_keep_their_cos_names():
    plan = {"known": {"DATA-TTS/dns5": "p/datasets/dns5_noise_rir/"}}

    assert mirror.destination(plan, "DATA-TTS/dns5", "p/") == "p/datasets/dns5_noise_rir/"
    assert mirror.destination(plan, "DATA-TTS/dns5/x", "p/") == "p/datasets/dns5_noise_rir/x/"
    assert mirror.destination(plan, "datasets/a/source", "p/") == "p/datasets/a/source/"


def test_ledger_lists_only_versions_whose_directories_are_verified():
    def done(dest, day="2026-11-04"):
        return {"dest": dest, "files": 1, "bytes": 2, "verified": day, "first_verified": day}

    plan = {
        "data_root": "/data",
        "units": ["datasets/a/source", "datasets/a/v1", "datasets/b/v1", "datasets/c/v1"],
        "datasets": {
            "a@v1": ["datasets/a/source", "datasets/a/v1"],
            "b@v1": ["datasets/a/source", "datasets/b/v1"],
            "c@v1": ["datasets/c/v1"],
        },
    }
    state = {
        "datasets/a/source": done("p/datasets/a/source/", "2026-11-03"),
        "datasets/a/v1": done("p/datasets/a/v1/"),
        "datasets/b/v1": done("p/datasets/b/v1/"),
        "datasets/c/v1": {"dest": "p/datasets/c/v1/", "ok": False},
        "T/ann/run1": done("p/T/ann/run1/"),
        "T/datasets/t/v0.1": done("p/T/datasets/t/v0.1/"),
    }
    plan["units"] += ["T/ann/run1", "T/datasets/t/v0.1"]
    plan["datasets"]["t@v0.1"] = ["T/ann/run1", "T/datasets/t/v0.1"]

    ledger = mirror.ledger(plan, state, "bucket", "p/")

    assert "datasets/c/v1" not in ledger["directories"]
    assert ledger["datasets"] == {
        "a@v1": {"alias": "datasets/a", "synced": "2026-11-04"},
        "b@v1": {
            "alias": "datasets/b",
            "synced": "2026-11-04",
            "requires": ["datasets/a/source", "datasets/b/v1"],
        },
        "t@v0.1": {
            "alias": "T/datasets/t",
            "synced": "2026-11-04",
            "requires": ["T/ann/run1", "T/datasets/t/v0.1"],
        },
    }
