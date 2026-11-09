import importlib.util
import io
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


class FakeClient:
    """In-memory COS: just the calls the mirror makes."""

    def __init__(self):
        self.objects, self.uploads = {}, {}

    def create_multipart_upload(self, Bucket, Key):
        self.uploads[Key] = {}
        return {"UploadId": Key}

    def upload_part(self, Bucket, Key, Body, PartNumber, UploadId, EnableMD5=False):
        self.uploads[Key][PartNumber] = bytes(Body)
        return {"ETag": str(PartNumber)}

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):
        parts = self.uploads.pop(Key)
        assert [p["PartNumber"] for p in MultipartUpload["Part"]] == sorted(parts)
        self.objects[Key] = b"".join(parts[n] for n in sorted(parts))

    def abort_multipart_upload(self, Bucket, Key, UploadId):
        self.uploads.pop(Key, None)

    def put_object(self, Bucket, Body, Key, EnableMD5=False):
        self.objects[Key] = Body

    get_calls = 0

    def get_object(self, Bucket, Key):
        self.get_calls += 1

        class Body:
            def get_raw_stream(self_inner):
                return io.BytesIO(self.objects[Key])
        return {"Body": Body()}

    def list_objects(self, Bucket, Prefix, Marker="", MaxKeys=1000):
        keys = sorted(k for k in self.objects if k.startswith(Prefix) and k > Marker)
        return {"Contents": [{"Key": k, "Size": len(self.objects[k])} for k in keys],
                "IsTruncated": "false"}


def fake_mirror(client, **overrides):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    args = SimpleNamespace(pack_below=1000, shard_size=3000, part_size=1024, part_inflight=2,
                           data_root="", **overrides)
    backend = SimpleNamespace(client=client, remote=SimpleNamespace(bucket="b"),
                              head=lambda key: SimpleNamespace(size=len(client.objects[key])))
    m = object.__new__(mirror.Mirror)
    m.args, m.backend = args, lambda: backend
    m.remote = backend.remote
    m.lock, m.uploaded, m.bytes = threading.Lock(), 0, 0
    m.parts, m.shards, m.pool = (ThreadPoolExecutor(4) for _ in range(3))
    m.shard_slots = threading.BoundedSemaphore(4)
    m.slots = threading.BoundedSemaphore(4)
    return m


def test_small_files_are_streamed_into_tar_shards_once(tmp_path):
    import gzip
    import io
    import json
    import tarfile

    for i in range(10):
        (tmp_path / "d" / f"s{i % 2}").mkdir(parents=True, exist_ok=True)
        (tmp_path / "d" / f"s{i % 2}" / f"{i}.wav").write_bytes(bytes([i]) * 700)
    (tmp_path / "d" / "big.bin").write_bytes(b"x" * 2000)  # not small: uploaded alone
    client = FakeClient()
    m = fake_mirror(client)
    pushed = []
    def push(path, key):
        pushed.append(key)
        client.objects[key] = path.read_bytes()
        return "uploaded", None

    m.push = push
    m.args.data_root = str(tmp_path)

    first = m.unit("d", "p/d/", [])
    second = m.unit("d", "p/d/", [])

    assert pushed == ["p/d/big.bin"]
    assert first["ok"] and first["packed"] == 10 and first["shards"] == 2
    assert second["ok"] and second["packed"] == 0 and second["present"] == 11
    tars = sorted(k for k in client.objects if k.endswith(".tar"))
    assert len(tars) == first["shards"]
    seen = {}
    for name in tars:
        index = json.loads(gzip.decompress(client.objects[name[:-4] + ".json.gz"]))
        with tarfile.open(fileobj=io.BytesIO(client.objects[name])) as tar:
            assert [m_.name for m_ in tar.getmembers()] == [k for k, _ in index["members"]]
            seen.update({m_.name: tar.extractfile(m_).read() for m_ in tar.getmembers()})
        assert index["size"] == len(client.objects[name])
    assert seen == {f"s{i % 2}/{i}.wav": bytes([i]) * 700 for i in range(10)}
    assert not any("p/d/s" in k for k in client.objects)  # nothing small went up on its own


def test_failed_shard_is_aborted_and_counted(tmp_path, monkeypatch):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "a.wav").write_bytes(b"a" * 100)
    client = FakeClient()
    client.upload_part = lambda **kw: (_ for _ in ()).throw(OSError("network"))
    m = fake_mirror(client)
    m.args.data_root = str(tmp_path)
    monkeypatch.setattr(mirror.time, "sleep", lambda s: None)

    counts = m.unit("d", "p/d/", [])

    assert not counts["ok"] and counts["failed"] == 1 and "network" in counts["errors"][0]
    assert not client.uploads and not client.objects


def test_unpack_streams_shards_back_and_skips_files_already_there(tmp_path):
    src = tmp_path / "src" / "d"
    for i in range(6):
        (src / f"s{i % 2}").mkdir(parents=True, exist_ok=True)
        (src / f"s{i % 2}" / f"{i}.wav").write_bytes(bytes([i]) * 700)
    client = FakeClient()
    m = fake_mirror(client)
    m.args.data_root = str(tmp_path / "src")
    assert m.unit("d", "p/d/", [])["packed"] == 6
    client.get_object_raw = client.get_object
    backend = m.backend()
    out = tmp_path / "out"
    (out / "s0").mkdir(parents=True)
    (out / "s0" / "0.wav").write_bytes(bytes([0]) * 700)  # already restored: left alone

    files, errors = mirror.unpack_shards(backend, "p/d/", out, workers=2)

    assert (files, errors) == (6, [])
    assert {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*.wav")} == {
        f"s{i % 2}/{i}.wav": bytes([i]) * 700 for i in range(6)}
    reads = client.get_calls
    again = mirror.unpack_shards(backend, "p/d/", out, workers=2)
    assert again == (6, []) and client.get_calls - reads == len(
        [k for k in client.objects if k.endswith(".json.gz")])  # indexes only: no shard is downloaded again
    only, problems = mirror.unpack_shards(backend, "p/d/", tmp_path / "part", only=["s1/"])
    assert problems == []
    assert only == 3 and sorted(p.name for p in (tmp_path / "part").rglob("*.wav")) == ["1.wav", "3.wav", "5.wav"]


def test_unpack_reports_a_shard_that_disagrees_with_its_index(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "a.wav").write_bytes(b"a" * 100)
    client = FakeClient()
    m = fake_mirror(client)
    m.args.data_root = str(tmp_path)
    m.unit("d", "p/d/", [])
    tar_key = next(k for k in client.objects if k.endswith(".tar"))
    index_key = tar_key[:-4] + ".json.gz"
    import gzip
    import json
    index = json.loads(gzip.decompress(client.objects[index_key]))
    index["members"].append(["missing.wav", 5])
    client.objects[index_key] = gzip.compress(json.dumps(index).encode())

    files, errors = mirror.unpack_shards(m.backend(), "p/d/", tmp_path / "out")

    assert files == 1 and "missing" in errors[0]


def test_pushing_small_files_one_by_one_needs_an_explicit_override(capsys):
    args = mirror.argparse.Namespace(pack_below=0, allow_small_files=False)

    assert mirror.push(args) == 2
    assert "tar shards" in capsys.readouterr().err
