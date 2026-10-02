"""Persistent run lifecycle, event logging, cancellation, and SSE replay."""

import json
import inspect
import os
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime
from typing import TYPE_CHECKING

from config import RUN_DB
from agent.events import RunCancelled

if TYPE_CHECKING:
    from editor_controls import EditorContextSnapshot


class RunBusyError(Exception):
    """Raised when a thread already has an active run."""


class RunManager:
    """Store each Agent turn as a run with an ordered event stream."""

    def __init__(self, db_path: str = RUN_DB):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._active_runs: dict[str, threading.Event] = {}
        self._thread_runs: dict[str, str] = {}
        self._checkpoint_map: dict[str, str] = {}
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with self._lock:
            with closing(self._connect()) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        run_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL,
                        type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
                    """
                )

    def create_run(self, thread_id: str) -> str:
        """Create a run in the ``running`` state."""
        run_id = uuid.uuid4().hex
        now = datetime.now().isoformat()
        with self._lock:
            with closing(self._connect()) as conn, conn:
                conn.execute(
                    "INSERT INTO runs (run_id, thread_id, status, created_at, updated_at) VALUES (?,?,?,?,?)",
                    (run_id, thread_id, "running", now, now),
                )
        return run_id

    def append_event(self, run_id: str, event_type: str, payload: dict):
        """Append an event and update run status for terminal events."""
        now = datetime.now().isoformat()
        with self._lock:
            with closing(self._connect()) as conn, conn:
                conn.execute(
                    "INSERT INTO events (run_id, type, payload, created_at) VALUES (?,?,?,?)",
                    (run_id, event_type, json.dumps(payload, ensure_ascii=False), now),
                )
                if event_type == "terminal":
                    status = payload.get("status", "succeeded")
                    conn.execute(
                        "UPDATE runs SET status=?, updated_at=? WHERE run_id=?",
                        (status, now, run_id),
                    )

    def get_run(self, run_id: str) -> dict | None:
        """Return run metadata, or ``None`` when it does not exist."""
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT run_id, thread_id, status, created_at, updated_at FROM runs WHERE run_id=?",
                    (run_id,),
                ).fetchone()
        return dict(row) if row else None

    def get_events(self, run_id: str) -> list[dict]:
        """Return all run events in replay order."""
        with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT type, payload, created_at FROM events WHERE run_id=? ORDER BY id",
                    (run_id,),
                ).fetchall()
        return [
            {"type": r["type"], **json.loads(r["payload"]), "created_at": r["created_at"]}
            for r in rows
        ]

    def start(
        self,
        thread_id: str,
        video_id: str,
        user_input: str,
        pinned_joints: dict,
        effect_mentions: list[dict] | None = None,
        selected_option_id: str | None = None,
        editor_context: "EditorContextSnapshot | None" = None,
        runner=None,
    ) -> str:
        """Create a run and execute it in a background thread.

        Each thread permits one active run. ``runner`` is injectable for tests.
        """
        with self._lock:
            if thread_id in self._thread_runs:
                raise RunBusyError(
                    f"Thread {thread_id} already has an active run; wait or cancel it first"
                )
            run_id = self.create_run(thread_id)
            cancel_event = threading.Event()
            self._active_runs[run_id] = cancel_event
            self._thread_runs[thread_id] = run_id
            resume_checkpoint_id = self._checkpoint_map.get(thread_id, "")

        if runner is None:
            runner = self._default_runner

        def worker():
            try:
                runner_kwargs = {
                    "run_id": run_id,
                    "thread_id": thread_id,
                    "video_id": video_id,
                    "user_input": user_input,
                    "pinned_joints": pinned_joints,
                    "cancel_event": cancel_event,
                    "resume_checkpoint_id": resume_checkpoint_id,
                    "on_event": lambda stage, content: self.append_event(
                        run_id, "stage", {"stage": stage, "content": content}
                    ),
                    "on_tool_event": lambda ev: self.append_event(
                        run_id, ev["type"], {k: v for k, v in ev.items() if k != "type"}
                    ),
                }
                if "effect_mentions" in inspect.signature(runner).parameters:
                    runner_kwargs["effect_mentions"] = effect_mentions or []
                if "selected_option_id" in inspect.signature(runner).parameters:
                    runner_kwargs["selected_option_id"] = selected_option_id
                if "editor_context" in inspect.signature(runner).parameters:
                    runner_kwargs["editor_context"] = editor_context
                result = runner(**runner_kwargs)
                checkpoint_id = result.get("checkpoint_id", "") if isinstance(result, dict) else ""
                if checkpoint_id:
                    with self._lock:
                        self._checkpoint_map[thread_id] = checkpoint_id
                self.append_event(run_id, "terminal", {"status": "succeeded", "result": result})
            except RunCancelled:
                self.append_event(run_id, "terminal", {"status": "cancelled", "result": None})
            except Exception as e:
                self.append_event(
                    run_id,
                    "terminal",
                    {"status": "failed", "result": None, "error": str(e)},
                )
            finally:
                with self._lock:
                    if self._thread_runs.get(thread_id) == run_id:
                        del self._thread_runs[thread_id]
                    self._active_runs.pop(run_id, None)

        threading.Thread(target=worker, daemon=True).start()
        return run_id

    def _default_runner(
        self,
        run_id: str,
        thread_id: str,
        video_id: str,
        user_input: str,
        pinned_joints: dict,
        effect_mentions: list[dict],
        selected_option_id: str | None,
        editor_context: "EditorContextSnapshot | None",
        cancel_event,
        resume_checkpoint_id: str,
        on_event,
        on_tool_event,
    ) -> dict:
        """Run the complete MainAgent workflow."""
        from agent.agent import process_user_message

        return process_user_message(
            video_id=video_id,
            user_input=user_input,
            effect_id=thread_id,
            effect_messages=[],
            prev_code="",
            effect_name="",
            effect_list=[],
            pinned_joints=pinned_joints,
            effect_mentions=effect_mentions,
            selected_option_id=selected_option_id,
            editor_context=editor_context,
            thread_id=thread_id,
            progress_callback=on_event,
            event_callback=on_tool_event,
            cancel_event=cancel_event,
            resume_checkpoint_id=resume_checkpoint_id,
        )

    def cancel(self, run_id: str) -> bool:
        """Request cancellation of an active run."""
        with self._lock:
            event = self._active_runs.get(run_id)
            if event is None:
                return False
            event.set()
            return True

    def event_stream(self, run_id: str, poll_interval: float = 0.2):
        """Replay stored events, then stream new events through completion."""
        seen = 0
        while True:
            events = self.get_events(run_id)
            for ev in events[seen:]:
                seen += 1
                yield f"event: message\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if any(e["type"] == "terminal" for e in events):
                break
            time.sleep(poll_interval)
