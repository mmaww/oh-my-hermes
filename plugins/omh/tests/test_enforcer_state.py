"""Tests for OMH enforcer state ledger."""

from plugins.omh.omh_enforcer_state import (
    get_state,
    has_state,
    mark_completed,
    record_tool_evidence,
    record_tool_intent,
    request_cancel,
    reset_state_for_tests,
    set_phase,
)


def setup_function() -> None:
    reset_state_for_tests()


def teardown_function() -> None:
    reset_state_for_tests()


def test_phase_and_terminal_markers(tmp_path, monkeypatch):
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))

    set_phase("state-1", "ralph")
    state = get_state("state-1")
    assert state.current_phase == "ralph"

    mark_completed("state-1", "verified")
    state = get_state("state-1")
    assert state.current_phase == "completed"
    assert state.completion_verified is True
    assert state.terminal_reason == "verified"


def test_cancel_and_records(tmp_path, monkeypatch):
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))

    record_tool_intent("state-2", "terminal", {"cmd": "echo hi"}, tool_call_id="t1")
    record_tool_evidence("state-2", "terminal", {"cmd": "echo hi"}, "hi", tool_call_id="t1", is_error=False)
    request_cancel("state-2", "user cancelled")

    state = get_state("state-2")
    assert state.cancel_requested is True
    assert state.current_phase == "cancelled"
    assert len(state.tool_intents) == 1
    assert len(state.evidence_records) == 1


def test_reset_state_clears_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OMH_ENFORCER_STATE_FILE", str(tmp_path / "workflow-state.json"))

    set_phase("state-3", "ralph")
    assert has_state("state-3") is True

    reset_state_for_tests()
    assert has_state("state-3") is False
