"""Thread-local event callback channel.

MainAgent and CodeAgent run in the same thread. Thread-local variables carry structured
events such as tool results and retries without adding callbacks to LangChain tool signatures.
"""

import threading


class RunCancelled(Exception):
    """Signal user cancellation so RunManager can update the run state."""


_local = threading.local()


def set_callback(callback):
    """Set the event callback for the current run thread."""
    _local.callback = callback


def get_callback():
    """Return the current thread's event callback, if any."""
    return getattr(_local, "callback", None)


def clear_callback():
    """Clear the current thread's event callback."""
    if hasattr(_local, "callback"):
        del _local.callback


def set_cancel_event(event: threading.Event):
    """Set the cancellation signal for the current run thread."""
    _local.cancel_event = event


def get_cancel_event():
    """Return the current thread's cancellation signal, if any."""
    return getattr(_local, "cancel_event", None)


def is_cancelled() -> bool:
    """Return whether cancellation was requested for the current run."""
    ev = get_cancel_event()
    return ev is not None and ev.is_set()


def clear_cancel_event():
    """Clear the current thread's cancellation signal."""
    if hasattr(_local, "cancel_event"):
        del _local.cancel_event
