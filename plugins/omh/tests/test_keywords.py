"""Tests for OMH keyword routing."""

from plugins.omh.hooks.llm_hooks import pre_llm_call
from plugins.omh.omh_keywords import detect_keyword_routes, keyword_routing_context


def test_detects_autopilot_keyword():
    routes = detect_keyword_routes("autopilot: build a task app")
    assert routes[0].name == "autopilot"


def test_detects_wait_and_pipeline_keywords():
    routes = detect_keyword_routes("wait for rate limit then run pipeline")
    names = [r.name for r in routes]
    assert "wait" in names
    assert "pipeline" in names


def test_ignores_keywords_inside_code_and_urls():
    assert detect_keyword_routes("```bash\nautopilot build\n```") == []
    assert detect_keyword_routes("see https://example.com/ralph") == []


def test_cancel_has_priority_over_other_routes():
    routes = detect_keyword_routes("stopomc then ralph can resume later")
    assert routes[0].name == "cancel"


def test_context_names_surface():
    ctx = keyword_routing_context("ralplan this migration")
    assert ctx is not None
    assert "omh-ralplan" in ctx


def test_detects_config_stop_callback_keyword():
    ctx = keyword_routing_context("please configure notifications for discord")
    assert ctx is not None
    assert "omh config-stop-callback" in ctx


def test_pre_llm_call_injects_keyword_context_on_first_turn():
    result = pre_llm_call(is_first_turn=True, user_message="deep interview this idea")
    assert result is not None
    assert "OMH keyword routing" in result["context"]
    assert "omh-deep-interview" in result["context"]
