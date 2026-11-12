"""Chrome's DevTools port file must survive Windows sharing violations.

Chrome keeps ``DevToolsActivePort`` open while it starts; on Windows a
concurrent read can fail with a sharing violation (``PermissionError``). That
is a transient condition, not a failure - the screenshot must keep waiting
for the file instead of aborting.
"""

from __future__ import annotations

from pathlib import Path

from lm_optimizer.services import html_shot


def test_read_port_returns_none_while_the_file_is_locked(tmp_path, monkeypatch):
    target = tmp_path / "DevToolsActivePort"
    target.write_text("4242\n", encoding="utf-8")

    def locked(self, *args, **kwargs):
        raise PermissionError(13, "used by another process")

    monkeypatch.setattr(Path, "read_text", locked)
    assert html_shot._read_port(target) is None


def test_wait_for_port_survives_a_transient_lock(tmp_path, monkeypatch):
    target = tmp_path / "DevToolsActivePort"
    target.write_text("4242\n", encoding="utf-8")

    real_read_text = Path.read_text
    state = {"reads": 0}

    def flaky(self, *args, **kwargs):
        if self.name == "DevToolsActivePort":
            state["reads"] += 1
            if state["reads"] == 1:
                raise PermissionError(13, "used by another process")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)
    assert html_shot._wait_for_port(target, timeout_s=5) == 4242
    assert state["reads"] >= 2
