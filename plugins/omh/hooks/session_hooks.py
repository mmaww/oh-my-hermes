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
    for m in modes:
        if m["mode"] != "ralph":
            continue
        instance_id = m.get("instance_id")
        try:
            # Read ralph-tasks state to check for pending tasks
            tasks_result = state_read("ralph-tasks", instance_id=instance_id)
            if not tasks_result.get("exists"):
                continue
            tasks_data = tasks_result["data"]
            tasks = tasks_data.get("tasks", [])
            if not tasks:
                continue

            # Guard: only auto-schedule if ralph made progress this session
            # (last_progress_at must be set by ralph when it marks a task passed)
            ralph_result = state_read("ralph", instance_id=instance_id)
            ralph_data = ralph_result.get("data", {}) if ralph_result.get("exists") else {}
            last_progress = ralph_data.get("last_progress_at")
            if not last_progress:
                logger.debug("OMH auto-continue: ralph %s has no last_progress_at, skipping", instance_id or "default")
                continue

            # Check that progress was made recently (within last 5 minutes)
            from datetime import datetime, timezone
            try:
                progress_dt = datetime.fromisoformat(last_progress)
                if progress_dt.tzinfo is None:
                    progress_dt = progress_dt.replace(tzinfo=timezone.utc)
                age_seconds = (datetime.now(timezone.utc) - progress_dt).total_seconds()
                if age_seconds > 300:
                    logger.debug(
                        "OMH auto-continue: ralph %s last progress was %ds ago (>300s), skipping",
                        instance_id or "default", int(age_seconds)
                    )
                    continue
            except Exception:
                pass  # If parse fails, assume recent

            # Count pending (passes=False or not completed)
            pending = [t for t in tasks if not t.get("passes", False)]
            if not pending:
                logger.info("OMH auto-continue: ralph %s has no pending tasks", instance_id or "default")
                continue

            logger.info(
                "OMH auto-continue: ralph %s has %d pending tasks, scheduling cron job",
                instance_id or "default", len(pending)
            )

            # Schedule a one-shot cron job
            from cron.jobs import create_job, save_jobs, list_jobs

            # Build a self-contained prompt for the cron job
            prompt = (
                f"Continue ralph execution for paper-writing task. "
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
                deliver="origin",
                skills=["paper-learning-workflow", "omh-ralph"],
            )

            jobs = list_jobs(include_disabled=False)
            jobs.append(new_job)
            save_jobs(jobs)

            logger.info(
                "OMH auto-continue: scheduled cron job %s for ralph %s",
                new_job.get("id", "unknown"), instance_id or "default"
            )

        except Exception as e:
            logger.warning("OMH auto-continue: failed for ralph %s: %s", instance_id or "default", e)
