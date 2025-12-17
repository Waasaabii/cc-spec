"""Unit tests for Codex JSONL stream parser."""

from cc_spec.codex.parser import parse_codex_jsonl


def test_parse_codex_jsonl_extracts_session_and_message() -> None:
    lines = [
        '{"type":"thread.started","thread_id":"sess-123"}\n',
        '{"type":"item.completed","item":{"type":"agent_message","text":" Hello "}}\n',
    ]

    parsed = parse_codex_jsonl(lines)

    assert parsed.session_id == "sess-123"
    assert parsed.message == "Hello"
    assert parsed.events_parsed == 2


def test_parse_codex_jsonl_ignores_invalid_lines_and_non_dict_json() -> None:
    lines = [
        "not json\n",
        "[]\n",
        '{"type":"thread.started","thread_id":"sess-1"}\n',
        '{"type":"item.completed","item":null}\n',
    ]

    parsed = parse_codex_jsonl(lines)

    assert parsed.session_id == "sess-1"
    assert parsed.message == ""
    # Only dict JSON objects count as parsed events
    assert parsed.events_parsed == 2


def test_parse_codex_jsonl_last_agent_message_wins() -> None:
    lines = [
        '{"type":"thread.started","thread_id":"sess-123"}\n',
        '{"type":"item.completed","item":{"type":"agent_message","text":"first"}}\n',
        '{"type":"item.completed","item":{"type":"agent_message","text":"second"}}\n',
    ]

    parsed = parse_codex_jsonl(lines)

    assert parsed.message == "second"
    assert parsed.session_id == "sess-123"
    assert parsed.events_parsed == 3


def test_parse_codex_jsonl_normalizes_text_variants() -> None:
    lines = [
        '{"type":"item.completed","item":{"type":"agent_message","text":["a","b"]}}\n',
        '{"type":"item.completed","item":{"type":"agent_message","text":{"text":" ok "}}}\n',
    ]

    parsed = parse_codex_jsonl(lines)

    assert parsed.message == "ok"
    assert parsed.session_id is None
    assert parsed.events_parsed == 2


def test_parse_codex_jsonl_ignores_non_agent_message_items() -> None:
    lines = [
        '{"type":"item.completed","item":{"type":"tool_call","text":"nope"}}\n',
        '{"type":"item.completed","item":{"type":"agent_message","text":""}}\n',
    ]

    parsed = parse_codex_jsonl(lines)

    assert parsed.message == ""
    assert parsed.events_parsed == 2

