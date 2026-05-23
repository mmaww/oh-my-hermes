"""Tests for OMH strict enforcer hooks."""

import plugins.omh.omh_config as omh_config_module
from plugins.omh.hooks.enforcer_hooks import (
    enforcer_on_session_end,
    enforcer_post_llm_call,
    enforcer_post_tool_call,
    enforcer_pre_gateway_send,
    enforcer_pre_llm_call,
    enforcer_pre_tool_call,
)
from plugins.omh.omh_enforcer_state import (
    get_state,
    record_required_item_count,
    reset_state_for_tests,
    set_phase,
)


def setup_function() -> None:
    reset_state_for_tests()


def teardown_function() -> None:
    reset_state_for_tests()


def test_pre_llm_first_turn_injects_required_omh_skills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))
    monkeypatch.setenv("OMH_ENFORCER_ENABLED", "1")
    omh_config_module._config_cache = {
        "state_dir": ".omh/state",
        "staleness_hours": 2,
        "cancel_ttl_seconds": 30,
        "evidence": {},
    }

    result = enforcer_pre_llm_call(
        session_id="enf-llm-first",
        user_message="ralph: implement feature",
        is_first_turn=True,
    )

    assert result is not None
    assert "context" in result
    assert "REQUIRED SKILLS PRELOADED" in result["context"]
    assert '<required_skill name="omh-ralph" status="loaded"' in result["context"]
    assert '<required_skill name="omh-ralplan" status="loaded"' in result["context"]
    assert '<required_skill name="omh-deep-interview" status="loaded"' in result["context"]


def test_pre_tool_blocks_destructive_and_records_intent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))
    monkeypatch.setenv("OMH_ENFORCER_ENABLED", "1")

    set_phase("enf-dangerous", "ralph")
    result = enforcer_pre_tool_call(
        session_id="enf-dangerous",
        tool_name="terminal",
        args={"cmd": "git reset --hard"},
        tool_call_id="tool-1",
    )

    assert result is not None
    assert result.get("action") == "block"
    state = get_state("enf-dangerous")
    assert len(state.tool_intents) == 1


def test_ralph_close_requires_ledger_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))
    monkeypatch.setenv("OMH_ENFORCER_ENABLED", "1")

    set_phase("enf-no-ledger", "ralph")
    result = enforcer_post_llm_call(
        session_id="enf-no-ledger",
        assistant_response=(
            "任务已全部完成。\n"
            "改动文件: /tmp/example.py:1\n"
            "验证：pytest -q\n"
            "命令输出: 12 passed in 0.10s\n"
            "无待办，无已知错误。"
        ),
    )

    assert result is not None
    assert result.get("block") is True
    assert result.get("type") == "ralph:no_ledger_evidence"


def test_post_tool_evidence_allows_ralph_close(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))
    monkeypatch.setenv("OMH_ENFORCER_ENABLED", "1")

    set_phase("enf-close", "ralph")
    enforcer_post_tool_call(
        session_id="enf-close",
        tool_name="terminal",
        args={"cmd": "pytest -q"},
        result="12 passed in 0.10s\nexit code 0",
        tool_call_id="tool-close",
        is_error=False,
    )

    first = enforcer_post_llm_call(
        session_id="enf-close",
        assistant_response=(
            "任务已全部完成。\n"
            "改动文件: /tmp/example.py:1\n"
            "验证：pytest -q\n"
            "命令输出: 12 passed in 0.10s\n"
            "无待办，无已知错误。"
        ),
    )

    assert first is not None
    assert first.get("type") == "ralph:close_check_not_enough"

    second = enforcer_post_llm_call(
        session_id="enf-close",
        assistant_response=(
            "任务已全部完成。\n"
            "改动文件: /tmp/example.py:1\n"
            "验证：pytest -q\n"
            "命令输出: 12 passed in 0.10s\n"
            "无待办，无已知错误。"
        ),
    )
    assert second is not None
    assert second.get("type") == "ralph:close_check_not_enough"

    third = enforcer_post_llm_call(
        session_id="enf-close",
        assistant_response=(
            "任务已全部完成。\n"
            "改动文件: /tmp/example.py:1\n"
            "验证：pytest -q\n"
            "命令输出: 12 passed in 0.10s\n"
            "无待办，无已知错误。"
        ),
    )

    assert third is None
    state = get_state("enf-close")
    assert state.current_phase == "completed"
    assert state.completion_verified is True
    assert state.ralph_close_checks == 0


def test_ralph_question_marks_block_and_reset_close_checks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))
    monkeypatch.setenv("OMH_ENFORCER_ENABLED", "1")

    set_phase("enf-question-mark", "ralph")
    enforcer_post_tool_call(
        session_id="enf-question-mark",
        tool_name="terminal",
        args={"cmd": "pytest -q"},
        result="12 passed in 0.10s\nexit code 0",
        tool_call_id="tool-question-mark",
        is_error=False,
    )

    first = enforcer_post_llm_call(
        session_id="enf-question-mark",
        assistant_response=(
            "任务已全部完成。\n"
            "改动文件: /tmp/example.py:1\n"
            "验证：pytest -q\n"
            "命令输出: 12 passed in 0.10s\n"
            "无待办，无已知错误。"
        ),
    )
    assert first is not None
    assert first.get("type") == "ralph:close_check_not_enough"
    state = get_state("enf-question-mark")
    assert state.ralph_close_checks == 1

    blocked_by_question = enforcer_post_llm_call(
        session_id="enf-question-mark",
        assistant_response="这个结果看起来正常？\n请确认还要继续吗？",
    )
    assert blocked_by_question is not None
    assert blocked_by_question.get("type") == "ralph:question_mark"

    state = get_state("enf-question-mark")
    assert state.ralph_close_checks == 0

    final = enforcer_post_llm_call(
        session_id="enf-question-mark",
        assistant_response=(
            "任务已全部完成。\n"
            "改动文件: /tmp/example.py:1\n"
            "验证：pytest -q\n"
            "命令输出: 12 passed in 0.10s\n"
            "无待办，无已知错误。"
        ),
    )
    assert final is not None
    assert final.get("type") == "ralph:close_check_not_enough"


def test_scope_shrinkage_blocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))
    monkeypatch.setenv("OMH_ENFORCER_ENABLED", "1")

    set_phase("enf-scope", "ralph")
    record_required_item_count("enf-scope", 100, "用户要求 100 件")
    enforcer_post_tool_call(
        session_id="enf-scope",
        tool_name="terminal",
        args={"cmd": "pytest -q"},
        result="100/100 processed\n12 passed in 0.10s\nexit code 0",
        tool_call_id="tool-scope",
        is_error=False,
    )

    result = enforcer_post_llm_call(
        session_id="enf-scope",
        assistant_response=(
            "任务已全部完成。\n"
            "已完成 10 件。\n"
            "改动文件: /tmp/example.py:1\n"
            "验证：pytest -q\n"
            "命令输出: 12 passed in 0.10s\n"
            "无待办，无已知错误。"
        ),
    )

    assert result is not None
    assert result.get("block") is True
    assert result.get("type") == "ralph:scope_mismatch"


def test_gateway_guard_blocks_lazy_handoff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))
    monkeypatch.setenv("OMH_ENFORCER_ENABLED", "1")

    result = enforcer_pre_gateway_send(
        platform="feishu",
        chat_id="chat-1",
        content="我可以继续吗？",
        metadata={},
        operation="send",
    )

    assert result is not None
    assert result.get("block") is True
    assert result.get("gateway_blocked") is True
    assert result.get("type") == "omc:stopped_to_ask"


def test_session_end_preserves_active_ralph(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))
    monkeypatch.setenv("OMH_ENFORCER_ENABLED", "1")

    set_phase("enf-end", "ralph")
    enforcer_on_session_end(session_id="enf-end")

    state = get_state("enf-end")
    assert state.current_phase == "ralph"
