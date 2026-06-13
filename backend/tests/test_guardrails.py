"""Tests for the guardrails audit log + confirmation gate (Week 3 guardrails).

NOVA_HOME is isolated per test by the autouse conftest fixture, so the audit log
is written under the temp dir.
"""

import json
import os
from pathlib import Path

from langchain_core.tools import StructuredTool

from app.guardrails import wrap_tools


def _make_tool(name, sink):
    def fn(payload: str = "") -> str:
        sink.append(payload)
        return "ok"
    return StructuredTool.from_function(fn, name=name, description="x")


def _audit_lines():
    path = Path(os.environ["NOVA_HOME"]) / "data" / "audit.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


class TestAuditWrapping:
    def test_should_LogAndRun_when_SideEffectTool(self):
        calls = []
        wrapped = wrap_tools([_make_tool("send_email", calls)])[0]
        wrapped.invoke({"payload": "a@b.com"})
        assert calls == ["a@b.com"]                    # underlying ran
        lines = _audit_lines()
        assert len(lines) == 1 and lines[0]["tool"] == "send_email"

    def test_should_NotWrapOrLog_when_NonSideEffectTool(self):
        calls = []
        original = _make_tool("web_search", calls)
        out = wrap_tools([original])
        assert out[0] is original          # passed through unchanged
        out[0].invoke({"payload": "hi"})
        assert calls and _audit_lines() == []

    def test_should_NotMutateGlobal_when_Wrapped(self):
        calls = []
        original = _make_tool("create_task", calls)
        wrapped = wrap_tools([original])[0]
        assert wrapped is not original     # a copy, original untouched
        original.invoke({"payload": "t"})  # invoking the ORIGINAL does not audit
        assert _audit_lines() == []


class TestConfirmationGate:
    def test_should_Block_when_ConfirmEnabled(self, monkeypatch):
        monkeypatch.setenv("NOVA_GUARDRAILS_CONFIRM", "1")
        calls = []
        wrapped = wrap_tools([_make_tool("send_email", calls)])[0]
        out = wrapped.invoke({"payload": "x@y.com"})
        assert "NOT executed" in out
        assert calls == []  # underlying never fired

    def test_should_NotBlock_when_ConfirmDisabled(self):
        calls = []
        wrapped = wrap_tools([_make_tool("send_email", calls)])[0]
        wrapped.invoke({"payload": "x@y.com"})
        assert calls == ["x@y.com"]
