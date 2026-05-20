"""Tests for the OMH CLI helpers."""

import json
from pathlib import Path

import pytest

import plugins.omh.omh_config as omh_config_module
from plugins.omh import cli
from plugins.omh.omh_state import state_write


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    omh_config_module._config_cache = {
        "state_dir": ".omh/state",
        "staleness_hours": 2,
        "cancel_ttl_seconds": 30,
        "evidence": {},
    }
    from plugins.omh import omh_state as mod
    mod._list_cache["result"] = None
    mod._list_cache["expires_at"] = 0.0
    yield tmp_path
    omh_config_module._config_cache = None
    mod._list_cache["result"] = None
    mod._list_cache["expires_at"] = 0.0


def test_setup_dry_run_reports_targets(capsys):
    rc = cli.main(["setup", "--dry-run", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["actions"][0]["status"] in {"would-link", "already-linked", "exists"}


def test_status_json_reads_state(capsys):
    state_write("ralph", {"active": True, "phase": "execute"})
    rc = cli.main(["status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_count"] == 1
    assert payload["states"][0]["mode"] == "ralph"


def test_hud_prints_one_line(capsys):
    state_write("ralph", {"active": True, "phase": "verify"})
    rc = cli.main(["hud"])
    assert rc == 0
    assert "OMH active=1" in capsys.readouterr().out


def test_ask_dry_run_writes_artifact(capsys):
    rc = cli.main(["ask", "codex", "--prompt", "review this", "--dry-run", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    artifact = Path(payload["artifact"])
    assert artifact.exists()
    assert "review this" in artifact.read_text(encoding="utf-8")


def test_team_dry_run_builds_worker_plan(capsys):
    rc = cli.main(["team", "--dry-run", "2:codex", "review auth"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workers"] == 2
    assert len(payload["commands"]) == 2


def test_cancel_all_active_modes(capsys):
    state_write("ralph", {"active": True})
    rc = cli.main(["cancel", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["cancelled"][0]["mode"] == "ralph"


def test_skill_add_and_search(capsys):
    rc = cli.main(["skill", "add", "fix-proxy", "--description", "Fix proxy crashes", "--triggers", "proxy,aiohttp"])
    assert rc == 0
    path = Path(capsys.readouterr().out.strip())
    assert path.exists()

    rc = cli.main(["skill", "search", "aiohttp", "--scope", "project", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["matches"][0]["name"] == "fix-proxy"
