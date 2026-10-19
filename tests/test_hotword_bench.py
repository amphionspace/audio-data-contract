import runpy
from pathlib import Path

import pytest

pytest.importorskip("soundfile")
pytest.importorskip("yaml")
REPO = Path(__file__).resolve().parents[1]
build = runpy.run_path(str(REPO / "scripts/hotword_bench/build.py"))
common = runpy.run_path(str(REPO / "scripts/hotword_bench/common.py"))
RECIPE = {"seed": 1, "list_size": 6, "confusables_per_word": 2}


def item(text, gold, split="cv_zh", language="zh", **extra):
    return {"split": split, "id": "u1", "text": text, "gold": gold, "language": language, **extra}


def test_longest_hotword_wins_and_english_needs_whole_words():
    assert common["occurrences"]("搜狐娱乐报道搜狐", ["搜狐", "搜狐娱乐"], "zh") == ["搜狐娱乐", "搜狐"]
    assert common["occurrences"]("i met joe keaton", ["joe", "kea"], "en") == ["joe"]


def test_k50_holds_gold_confusables_and_random_words_without_reference_words():
    pool = ["上海", "北京", "广州", "深圳", "杭州", "南京", "苏州", "刘燕"]
    lists, kinds = build["build_lists"](
        item("我叫刘燕住在上海", ["刘燕"]), pool, {"刘燕": ["柳岩", "刘艳", "刘雁"]}, RECIPE
    )
    k50, no_gold = lists["k50"], lists["k50_no_gold"]
    assert len(k50) == len(no_gold) == 6 and "刘燕" in k50 and "刘燕" not in no_gold
    assert {"柳岩", "刘艳"} <= set(k50) and "刘雁" not in k50  # at most two per word
    assert "上海" not in k50 + no_gold  # spoken in the reference
    assert kinds["柳岩"] == "confusable" and all(kinds[w] for w in no_gold)
    again, _ = build["build_lists"](
        item("我叫刘燕住在上海", ["刘燕"]), pool, {"刘燕": ["柳岩", "刘艳", "刘雁"]}, RECIPE
    )
    assert again == lists


def test_too_many_confusables_keep_one_per_gold_word_first():
    confusables = {"甲乙": ["甲一", "甲二"], "丙丁": ["丙一", "丙二"], "戊己": ["戊一", "戊二"]}
    recipe = {**RECIPE, "list_size": 6}
    lists, _ = build["build_lists"](item("甲乙丙丁戊己", ["甲乙", "丙丁", "戊己"]), [], confusables, recipe)
    assert {"甲一", "丙一", "戊一"} <= set(lists["k50"]) and len(lists["k50"]) == 6


def test_librispeech_keeps_official_lists_and_adds_a_no_gold_list():
    upstream = {"n100": ["fir"] + [f"w{i}" for i in range(100)], "n1000": ["fir"]}
    pool = [f"x{i}" for i in range(5000)]
    lists, _ = build["build_lists"](
        item("a nice fir tree", ["fir"], split="librispeech_test_clean", language="en", lists=upstream),
        pool, {}, RECIPE,
    )
    assert lists["n100"] == upstream["n100"] and lists["gold"] == ["fir"]
    assert len(lists["n100_no_gold"]) == 100 and "fir" not in lists["n100_no_gold"]


def test_pool_lists_rank_sound_alikes_and_keep_reference_words_out():
    pytest.importorskip("pypinyin")
    pool_mod = runpy.run_path(str(REPO / "scripts/hotword_bench/pool.py"))
    recipe = {"seed": 1, "list_size": 4, "confusables_per_word": 2}
    record = {"id": "u1", "target": "我叫刘燕住在上海", "hotwords": ["刘燕"],
              "metadata": {"bias_lists": {"gold": ["刘燕"], "k50": [], "k50_no_gold": []}}}
    library = ["上海", "留言", "柳树", "北京", "广州", "深圳"]
    pool, own = pool_mod["tenant_pool"]([record], library, {"刘燕": ["柳岩", "刘艳"]}, 2)
    lists, kinds = pool_mod["tenant_lists"]((recipe, [record], pool, own, {"刘燕": ["柳岩", "刘艳"]}))["u1"]
    assert set(lists) == {"gold", "pool50", "pool50_no_gold"}
    assert len(lists["pool50"]) == len(lists["pool50_no_gold"]) == 4
    assert "刘燕" in lists["pool50"] and "刘燕" not in lists["pool50_no_gold"]
    assert {"柳岩", "刘艳", "留言"} <= set(lists["pool50_no_gold"])  # same pinyin as the gold word
    assert "上海" not in lists["pool50"] + lists["pool50_no_gold"]  # spoken in the reference
    assert kinds["柳岩"] == "confusable" and kinds["留言"] == "base"
