"""Tests for the web_search cloud tool (DuckDuckGo)."""

from unittest.mock import patch, MagicMock


class TestWebSearch:
    @patch("app.tools.cloud.search_tool.DDGS")
    def test_should_ReturnFormattedResults_when_ResultsFound(self, mock_ddgs_cls):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.text.return_value = [
            {"title": "Result 1", "body": "Body 1", "href": "https://example.com/1"},
            {"title": "Result 2", "body": "Body 2", "href": "https://example.com/2"},
        ]
        mock_ddgs_cls.return_value = mock_ctx

        from app.tools.cloud.search_tool import web_search
        result = web_search.invoke({"query": "test query"})

        assert "Result 1" in result
        assert "Result 2" in result
        assert "https://example.com/1" in result
        assert "Search results for 'test query'" in result

    @patch("app.tools.cloud.search_tool.DDGS")
    def test_should_ReturnNoResults_when_SearchReturnsEmpty(self, mock_ddgs_cls):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.text.return_value = []
        mock_ddgs_cls.return_value = mock_ctx

        from app.tools.cloud.search_tool import web_search
        result = web_search.invoke({"query": "xyznonexistent123"})

        assert "No results" in result

    @patch("app.tools.cloud.search_tool.DDGS")
    def test_should_ReturnError_when_SearchRaisesException(self, mock_ddgs_cls):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.text.side_effect = ConnectionError("network down")
        mock_ddgs_cls.return_value = mock_ctx

        from app.tools.cloud.search_tool import web_search
        result = web_search.invoke({"query": "test"})

        assert "Search error" in result

    @patch("app.tools.cloud.search_tool.DDGS")
    def test_should_NumberResults_when_MultipleReturned(self, mock_ddgs_cls):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.text.return_value = [
            {"title": f"T{i}", "body": f"B{i}", "href": f"http://e.com/{i}"}
            for i in range(3)
        ]
        mock_ddgs_cls.return_value = mock_ctx

        from app.tools.cloud.search_tool import web_search
        result = web_search.invoke({"query": "test"})

        assert "1." in result
        assert "2." in result
        assert "3." in result

    @patch("app.tools.cloud.search_tool.DDGS")
    def test_should_LimitTo3Results_when_SearchCalled(self, mock_ddgs_cls):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.text.return_value = []
        mock_ddgs_cls.return_value = mock_ctx

        from app.tools.cloud.search_tool import web_search
        web_search.invoke({"query": "test"})

        mock_ctx.text.assert_called_once_with(
            "test", region="wt-wt", safesearch="Moderate", max_results=3
        )
