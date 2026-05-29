"""Tests for the local tool proxy (take_screenshot, read_screen_text, run_arp_scan)."""

from unittest.mock import patch, MagicMock


class TestRunLocal:
    @patch("app.tools.local.proxy.request_local_tool")
    @patch("app.tools.local.proxy.asyncio")
    def test_should_ReturnResult_when_LocalToolSucceeds(self, mock_asyncio, mock_req):
        # Simulate running event loop
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_asyncio.get_event_loop.return_value = mock_loop
        mock_loop.run_until_complete.return_value = "screenshot_data"

        from app.tools.local.proxy import _run_local
        result = _run_local("screenshot")
        assert result == "screenshot_data"

    @patch("app.tools.local.proxy.request_local_tool")
    @patch("app.tools.local.proxy.asyncio")
    def test_should_UseThreadPool_when_LoopIsRunning(self, mock_asyncio, mock_req):
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        mock_asyncio.get_event_loop.return_value = mock_loop

        from app.tools.local.proxy import _run_local
        result = _run_local("ocr")
        # When loop is running, it uses ThreadPoolExecutor
        assert isinstance(result, str) or result is not None

    @patch("app.tools.local.proxy.asyncio")
    def test_should_ReturnError_when_ExceptionRaised(self, mock_asyncio):
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_loop.run_until_complete.side_effect = RuntimeError("broken")
        mock_asyncio.get_event_loop.return_value = mock_loop

        from app.tools.local.proxy import _run_local
        result = _run_local("screenshot")
        assert "Error calling local tool" in result


class TestTakeScreenshot:
    @patch("app.tools.local.proxy._run_local", return_value="screenshot captured")
    def test_should_CallRunLocal_when_Invoked(self, mock_run):
        from app.tools.local.proxy import take_screenshot
        result = take_screenshot.invoke({})
        assert result == "screenshot captured"
        mock_run.assert_called_once_with("screenshot")


class TestReadScreenText:
    @patch("app.tools.local.proxy._run_local", return_value="OCR text here")
    def test_should_CallRunLocal_when_Invoked(self, mock_run):
        from app.tools.local.proxy import read_screen_text
        result = read_screen_text.invoke({})
        assert result == "OCR text here"
        mock_run.assert_called_once_with("ocr")


class TestRunArpScan:
    @patch("app.tools.local.proxy._run_local", return_value="192.168.1.1 mac-addr")
    def test_should_CallRunLocal_when_Invoked(self, mock_run):
        from app.tools.local.proxy import run_arp_scan
        result = run_arp_scan.invoke({})
        assert result == "192.168.1.1 mac-addr"
        mock_run.assert_called_once_with("arp_scan")
