"""
on_session_end hook — mark active OMH modes with an interruption timestamp.

When Hermes exits while OMH modes are active, writes _interrupted_at to
their state files so the next session knows it was interrupted mid-workflow.
"""

import logging
from datetime import datetime, timezone

from ..omh_state import _invalidate_list_cache, state_list_active, state_read, state_write

logger = logging.getLogger(__name__)


def on_session_end(**kwargs) -> None:
    """Write _interrupted_at to all active OMH state files."""
    try:
        _invalidate_list_cache()  # Force fresh disk scan — avoids stale 5s cache at session boundary
        active = state_list_active()
    except Exception as e:
        logger.debug("on_session_end: state_list_active error: %s", e)
        return

    modes = active.get("modes", [])
    if not modes:
        return

    interrupted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    saved = []

    for m in modes:
        mode_name = m["mode"]
        instance_id = m.get("instance_id")
        try:
            result = state_read(mode_name, instance_id=instance_id)
            if not result.get("exists"):
                continue
            data = result["data"]
            if not data.get("active"):
                continue
            data["_interrupted_at"] = interrupted_at
            state_write(mode_name, data, instance_id=instance_id)
            saved.append(mode_name if instance_id is None else f"{mode_name}/{instance_id}")
        except Exception as e:
            logger.warning("on_session_end: failed to save %s/%s: %s", mode_name, instance_id, e)

    if saved:
        logger.info("OMH: saved interruption state for modes: %s", saved)

    # === Auto-continue ralph: if pending tasks remain, schedule a one-shot cron ===
    _auto_continue_ralph(modes)


def _auto_continue_ralph(modes: list) -> None:
    """If ralph has pending tasks, schedule a one-shot cron job to continue.

    Chain logic: cron session runs → writes next paper → on_session_end fires again
    → checks state again → if still pending, schedules another cron.
    """
    import json as _json
    from pathlib import Path as _Path

    for m in modes:
        if m["mode"] != "ralph":
            continue
        instance_id = m.get("instance_id")
        try:
            # Guard: only auto-schedule if ralph is currently active
            ralph_result = state_read("ralph", instance_id=instance_id)
            ralph_data = ralph_result.get("data", {}) if ralph_result.get("exists") else {}
            if not ralph_data.get("active"):
                logger.debug("OMH auto-continue: ralph %s is not active, skipping", instance_id or "default")
                continue

            # Extract project_path from ralph state — authoritative source for state dir
            project_path = ralph_data.get("project_path", "")

            # Read ralph-tasks from the PROJECT's .omh/state/ (not gateway cwd's stale copy)
            # Fixes bug: gateway cwd/.omh/state/ had 5/5 done while project had 673 pending
            tasks_data = None
            if project_path:
                tasks_file = _Path(project_path) / ".omh" / "state" / f"ralph-tasks--{instance_id or 'default'}.json"
                if tasks_file.exists():
                    try:
                        tasks_data = _json.loads(tasks_file.read_text())
                    except Exception as e:
                        logger.warning("OMH auto-continue: failed to read tasks from %s: %s", tasks_file, e)

            # Fallback: read from gateway's state dir (legacy behavior)
            if tasks_data is None:
                tasks_result = state_read("ralph-tasks", instance_id=instance_id)
                if not tasks_result.get("exists"):
                    continue
                tasks_data = tasks_result["data"]

            tasks = tasks_data.get("tasks", [])
            if not tasks:
                continue

            # Count pending (passes=False or not completed)
            pending = [t for t in tasks if not t.get("passes", False)]
            if not pending:
                logger.info("OMH auto-continue: ralph %s has no pending tasks", instance_id or "default")
                continue

            logger.info(
                "OMH auto-continue: ralph %s has %d pending tasks (project: %s), scheduling cron job",
                instance_id or "default", len(pending), project_path or "cwd"
            )

            # Guard 1: skip if a recurring cron job already handles this ralph instance
            from cron.jobs import load_jobs
            _existing_jobs = load_jobs()
            _jobs_list = _existing_jobs.get("jobs", _existing_jobs) if isinstance(_existing_jobs, dict) else _existing_jobs
            _recurring_exists = any(
                j.get("name", "").startswith("ralph-paper-writer")
                and j.get("schedule", {}).get("kind") in ("cron", "interval")
                and j.get("enabled", True)
                for j in _jobs_list
                if isinstance(j, dict)
            )
            if _recurring_exists:
                logger.debug("OMH auto-continue: recurring ralph-paper-writer cron exists, skipping oneshot")
                continue

            # Guard 2 (idempotent): remove ALL existing oneshots with the same name
            # before creating a fresh one. Prevents TOCTOU race where multiple
            # on_session_end hooks read stale state and each create a duplicate.
            from cron.jobs import save_jobs
            _oneshot_name = f"ralph-auto-{instance_id or 'default'}"
            _before_count = len(_jobs_list)
            _jobs_list = [j for j in _jobs_list if not (
                isinstance(j, dict)
                and j.get("name") == _oneshot_name
                and j.get("schedule", {}).get("kind") == "once"
            )]
            _removed = _before_count - len(_jobs_list)
            if _removed > 0:
                logger.info("OMH auto-continue: removed %d stale oneshot(s) %s before creating fresh one",
                            _removed, _oneshot_name)
                _jobs_container = _existing_jobs
                if isinstance(_jobs_container, dict):
                    _jobs_container["jobs"] = _jobs_list  # type: ignore[index]
                    save_jobs(_jobs_container)
                else:
                    save_jobs(_jobs_list)

            # Schedule a one-shot cron job
            # create_job() already calls save_jobs() internally —
            # do NOT append + save_jobs() again (caused duplicate bug)
            from cron.jobs import create_job

            # Build a self-contained prompt for the cron job
            cwd_instruction = f" IMPORTANT: workdir is {project_path}. All file paths are relative to this directory." if project_path else ""
            prompt = (
                f"Continue ralph execution for paper-writing task.{cwd_instruction} "
                f"Read state: omh_state(action='read', mode='ralph', instance_id='{instance_id or ''}'). "
                f"Check for pending tasks and execute the next one. "
                f"After completion, verify and update state. "
                f"If more tasks remain, this hook will auto-schedule the next continuation."
            )

            new_job = create_job(
                prompt=prompt,
                schedule="1m",
                repeat=1,
                name=f"ralph-auto-{instance_id or 'default'}",
                deliver="local",
                skills=["paper-collection-workflow", "omh-ralph"],
                workdir=project_path if project_path else None,
            )

            logger.info(
                "OMH auto-continue: scheduled cron job %s for ralph %s (workdir=%s)",
                new_job.get("id", "unknown"), instance_id or "default", project_path or "default"
            )

        except Exception as e:
            logger.warning("OMH auto-continue: failed for ralph %s: %s", instance_id or "default", e)
