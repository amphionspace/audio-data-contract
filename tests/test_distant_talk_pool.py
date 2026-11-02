"""Labels of the distant-talk pool: what two models' answers against the source transcript turn into."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "finalize_distant_talk_pool", Path(__file__).parents[1] / "scripts/ts_robust/finalize_distant_talk_pool.py")
finalize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalize)

ONE = [{"text": "今天我们聊的话题是职业规划"}]
TWO = [{"text": "今天我们聊的话题是职业规划"}, {"text": None}]


def test_both_empty_is_empty_for_any_clip():
    assert finalize.classify(ONE, "", "") == ("empty", "both_empty")
    assert finalize.classify(TWO, "", "。") == ("empty", "both_empty")


def test_both_reading_the_transcript_keeps_the_text():
    assert finalize.classify(ONE, "今天我们聊的话题是职业规划。", "今天我们聊的话题是职业归化") == ("text", "both_read_it")


def test_one_model_reading_it_is_dropped_not_emptied():
    assert finalize.classify(ONE, "今天我们聊的话题是职业规划", "")[0] is None


def test_both_far_is_empty_only_when_they_disagree():
    assert finalize.classify(ONE, "完全无关的一句别的内容啊", "另外不同的句子什么东西呢")[0] == "empty"
    assert finalize.classify(ONE, "完全无关的一句别的内容啊", "完全无关的一句别的内容呀") == (None, "both_far_but_agree")
    assert finalize.classify(ONE, "完全无关的一句别的内容啊", "") == ("empty", "one_empty_other_far")


def test_two_conversations_need_two_written_disagreeing_answers():
    assert finalize.classify(TWO, "完全无关的一句别的内容啊", "另外不同的句子什么东西呢")[0] == "empty"
    assert finalize.classify(TWO, "今天我们聊的话题", "今天我们聊的话题呀")[0] is None
    assert finalize.classify(TWO, "今天我们聊的话题", "")[0] is None
