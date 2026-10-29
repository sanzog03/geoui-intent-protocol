import json

from geouibench.records import (
    TurnRecord,
    TurnUsage,
    append_record,
    deepest_in_chain,
    flatten_exceptions,
    load_records,
    scrub_paths,
    underlying_cause_summary,
    usage_from_run_usage,
)


def test_append_and_load_round_trip(tmp_path):
    path = tmp_path / "turns.jsonl"
    rec = TurnRecord(
        agent="vlm",
        session_id="s",
        turn_index=1,
        user_prompt="p",
        wall_clock_s=2.5,
        output_kind="structured",
        final_url="https://x",
        usage=TurnUsage(input_tokens=10, output_tokens=5, cache_read_tokens=4),
        golden_name="g",
        dataset="gold",
    )
    append_record(rec, path)
    append_record(rec, path)
    rows = load_records(path, TurnRecord)
    assert rows == [rec, rec]
    assert load_records(tmp_path / "missing.jsonl", TurnRecord) == []


def test_cache_adjusted_tokens_follow_the_prompts_md_recipe():
    usage = TurnUsage(input_tokens=1000, output_tokens=100, cache_read_tokens=500)
    assert usage.cache_adjusted_tokens == 1000 - 500 + 50 + 100
    assert TurnUsage().cache_adjusted_tokens is None


def test_usage_from_run_usage_reads_pydantic_ai_2_layout():
    from decimal import Decimal

    from pydantic_ai.usage import RunUsage

    usage = RunUsage(
        input_tokens=30613,
        output_tokens=736,
        cache_read_tokens=28800,
        output_reasoning_tokens=310,
        requests=3,
        tool_calls=2,
        cost=Decimal("0.0185"),
    )
    ours = usage_from_run_usage(usage)
    assert ours.input_tokens == 30613 and ours.total_tokens == 30613 + 736
    assert ours.reasoning_tokens == 310 and ours.cost_usd == 0.0185 and ours.tool_calls == 2
    assert usage_from_run_usage(None) is None


def test_exception_helpers():
    try:
        try:
            raise ConnectionError("tcp reset")
        except ConnectionError as inner:
            raise RuntimeError("model failed") from inner
    except RuntimeError as exc:
        err = exc
    assert deepest_in_chain(err).args == ("tcp reset",)
    assert underlying_cause_summary(err) == "ConnectionError: tcp reset"
    assert underlying_cause_summary(ValueError("alone")) is None
    group = ExceptionGroup("g", [ValueError("a"), ExceptionGroup("h", [KeyError("b")])])
    assert [type(e).__name__ for e in flatten_exceptions(group)] == ["ValueError", "KeyError"]


def test_scrub_paths_removes_home_and_repo():
    text = json.dumps({"tb": "/Users/someone/Devs/x.py and /home/bob/y.py"})
    assert "/Users/" not in scrub_paths(text) and "/home/" not in scrub_paths(text)
    assert scrub_paths("/tmp/here/file.py", {"/tmp/here": "<repo>"}) == "<repo>/file.py"
