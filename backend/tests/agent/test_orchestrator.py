"""Tests for the agent orchestrator (build_agent, invoke_agent)."""

from unittest.mock import patch, MagicMock

import pytest

from app.agent.session import _sessions


class TestBuildAgent:
    @patch("app.agent.orchestrator.AgentExecutor")
    @patch("app.agent.orchestrator.create_tool_calling_agent")
    @patch("app.agent.orchestrator.ChatGoogleGenerativeAI")
    def test_should_ReturnAgentExecutor_when_Called(self, mock_llm_cls, mock_create, mock_exec_cls):
        mock_create.return_value = MagicMock()
        mock_exec_cls.return_value = MagicMock()
        from app.agent.orchestrator import build_agent
        executor = build_agent()
        assert executor is not None

    @patch("app.agent.orchestrator.AgentExecutor")
    @patch("app.agent.orchestrator.create_tool_calling_agent")
    @patch("app.agent.orchestrator.ChatGoogleGenerativeAI")
    def test_should_UseGeminiFlash_when_BuildingLLM(self, mock_llm_cls, mock_create, mock_exec_cls):
        mock_create.return_value = MagicMock()
        mock_exec_cls.return_value = MagicMock()
        from app.agent.orchestrator import build_agent
        build_agent()
        call_kwargs = mock_llm_cls.call_args[1]
        assert call_kwargs["model"] == "gemini-2.0-flash"

    def test_should_Include11Tools_when_Built(self):
        from app.agent.orchestrator import CLOUD_TOOLS, LOCAL_TOOLS
        expected_count = len(CLOUD_TOOLS) + len(LOCAL_TOOLS)
        assert expected_count == 11

    @patch("app.agent.orchestrator.AgentExecutor")
    @patch("app.agent.orchestrator.create_tool_calling_agent")
    @patch("app.agent.orchestrator.ChatGoogleGenerativeAI")
    def test_should_SetMaxIterations_when_Built(self, mock_llm_cls, mock_create, mock_exec_cls):
        mock_create.return_value = MagicMock()
        mock_exec_cls.return_value = MagicMock()
        from app.agent.orchestrator import build_agent
        build_agent()
        call_kwargs = mock_exec_cls.call_args[1]
        assert call_kwargs["max_iterations"] == 5

    @patch("app.agent.orchestrator.AgentExecutor")
    @patch("app.agent.orchestrator.create_tool_calling_agent")
    @patch("app.agent.orchestrator.ChatGoogleGenerativeAI")
    def test_should_EnableVerbose_when_Built(self, mock_llm_cls, mock_create, mock_exec_cls):
        mock_create.return_value = MagicMock()
        mock_exec_cls.return_value = MagicMock()
        from app.agent.orchestrator import build_agent
        build_agent()
        call_kwargs = mock_exec_cls.call_args[1]
        assert call_kwargs["verbose"] is True

    @patch("app.agent.orchestrator.AgentExecutor")
    @patch("app.agent.orchestrator.create_tool_calling_agent")
    @patch("app.agent.orchestrator.ChatGoogleGenerativeAI")
    def test_should_HandleParsingErrors_when_Built(self, mock_llm_cls, mock_create, mock_exec_cls):
        mock_create.return_value = MagicMock()
        mock_exec_cls.return_value = MagicMock()
        from app.agent.orchestrator import build_agent
        build_agent()
        call_kwargs = mock_exec_cls.call_args[1]
        assert call_kwargs["handle_parsing_errors"] is True

    @patch("app.agent.orchestrator.AgentExecutor")
    @patch("app.agent.orchestrator.create_tool_calling_agent")
    @patch("app.agent.orchestrator.ChatGoogleGenerativeAI")
    def test_should_UseApiKeyFromSettings_when_Built(self, mock_llm_cls, mock_create, mock_exec_cls):
        mock_create.return_value = MagicMock()
        mock_exec_cls.return_value = MagicMock()
        from app.agent.orchestrator import build_agent
        build_agent()
        call_kwargs = mock_llm_cls.call_args[1]
        assert call_kwargs["google_api_key"] == "test-gemini-key"

    @patch("app.agent.orchestrator.AgentExecutor")
    @patch("app.agent.orchestrator.create_tool_calling_agent")
    @patch("app.agent.orchestrator.ChatGoogleGenerativeAI")
    def test_should_PassAllToolsToAgent_when_Built(self, mock_llm_cls, mock_create, mock_exec_cls):
        mock_create.return_value = MagicMock()
        mock_exec_cls.return_value = MagicMock()
        from app.agent.orchestrator import build_agent, CLOUD_TOOLS, LOCAL_TOOLS
        build_agent()
        call_kwargs = mock_create.call_args[1]
        assert len(call_kwargs["tools"]) == len(CLOUD_TOOLS) + len(LOCAL_TOOLS)


class TestInvokeAgent:
    def setup_method(self):
        _sessions.clear()

    def teardown_method(self):
        _sessions.clear()

    def test_should_ReturnOutput_when_AgentInvoked(self):
        from app.agent.orchestrator import invoke_agent
        executor = MagicMock()
        executor.invoke.return_value = {"output": "Hello, human!"}
        result = invoke_agent("Hi", "session-1", executor)
        assert result == "Hello, human!"

    def test_should_AddToMemory_when_InvokedSuccessfully(self):
        from app.agent.orchestrator import invoke_agent
        from app.agent.session import get_memory
        executor = MagicMock()
        executor.invoke.return_value = {"output": "Response"}
        invoke_agent("Hello", "s1", executor)
        mem = get_memory("s1")
        messages = mem.chat_memory.messages
        assert len(messages) == 2
        assert messages[0].content == "Hello"
        assert messages[1].content == "Response"

    def test_should_AccumulateChatHistory_when_MultipleInvocations(self):
        from app.agent.orchestrator import invoke_agent
        from app.agent.session import get_memory
        executor = MagicMock()
        executor.invoke.return_value = {"output": "R1"}
        invoke_agent("Q1", "s1", executor)
        executor.invoke.return_value = {"output": "R2"}
        invoke_agent("Q2", "s1", executor)
        # After 2 invocations: Q1, R1, Q2, R2 = 4 messages
        mem = get_memory("s1")
        assert len(mem.chat_memory.messages) == 4

    def test_should_PropagateException_when_AgentFails(self):
        from app.agent.orchestrator import invoke_agent
        executor = MagicMock()
        executor.invoke.side_effect = RuntimeError("kaboom")
        with pytest.raises(RuntimeError, match="kaboom"):
            invoke_agent("Hi", "s1", executor)

    def test_should_PassInputMessage_when_Invoking(self):
        from app.agent.orchestrator import invoke_agent
        executor = MagicMock()
        executor.invoke.return_value = {"output": "ok"}
        invoke_agent("What is 2+2?", "s1", executor)
        call_input = executor.invoke.call_args[0][0]
        assert call_input["input"] == "What is 2+2?"

    def test_should_CreateMemoryForNewSession_when_NewSession(self):
        """A brand-new session should have an empty memory before invoke_agent."""
        from app.agent.session import get_memory, _sessions
        _sessions.pop("fresh-session-xyz", None)
        mem = get_memory("fresh-session-xyz")
        assert len(mem.chat_memory.messages) == 0
        _sessions.pop("fresh-session-xyz", None)
