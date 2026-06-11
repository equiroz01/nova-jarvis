"""Tests for the Brave→DuckDuckGo search fallback (Week 3.4)."""

from unittest.mock import patch

import app.tools.cloud.search_tool as st


class TestSearchFallback:
    def test_should_FallBackToDDG_when_BraveFails(self):
        with patch.object(st, "_brave_search", side_effect=RuntimeError("Brave 503")), \
             patch.object(st, "_ddg_search", return_value="DDG result") as ddg:
            out = st.web_search.invoke({"query": "noticias"})
        assert out == "DDG result"
        assert ddg.called

    def test_should_NotCallDDG_when_BraveSucceeds(self):
        with patch.object(st, "_brave_search", return_value="BRAVE result"), \
             patch.object(st, "_ddg_search") as ddg:
            out = st.web_search.invoke({"query": "hi"})
        assert out == "BRAVE result"
        assert not ddg.called

    def test_should_ReturnGracefulError_when_BothFail(self):
        with patch.object(st, "_brave_search", side_effect=RuntimeError("no key")), \
             patch.object(st, "_ddg_search", side_effect=Exception("ddg down")):
            out = st.web_search.invoke({"query": "x"})
        assert "no" in out.lower() and "disponibles" in out.lower()
