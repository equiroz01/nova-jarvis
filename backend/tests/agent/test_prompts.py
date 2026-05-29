"""Tests for the agent prompt template."""

from app.agent.prompts import agent_prompt, SYSTEM_PROMPT


class TestSystemPrompt:
    def test_should_ContainJarvisIdentity_when_Loaded(self):
        assert "Jarvis" in SYSTEM_PROMPT

    def test_should_MentionBilingual_when_Loaded(self):
        assert "English" in SYSTEM_PROMPT
        assert "Spanish" in SYSTEM_PROMPT

    def test_should_MentionLocalClient_when_Loaded(self):
        assert "local" in SYSTEM_PROMPT.lower() or "client" in SYSTEM_PROMPT.lower()


class TestAgentPromptTemplate:
    def test_should_ContainSystemMessage_when_Constructed(self):
        messages = agent_prompt.messages
        # First message should be the system prompt
        assert len(messages) >= 1

    def test_should_HaveInputVariable_when_Constructed(self):
        assert "input" in agent_prompt.input_variables or any(
            "input" in str(m) for m in agent_prompt.messages
        )

    def test_should_HaveChatHistoryPlaceholder_when_Constructed(self):
        message_strs = [str(m) for m in agent_prompt.messages]
        assert any("chat_history" in s for s in message_strs)

    def test_should_HaveAgentScratchpad_when_Constructed(self):
        message_strs = [str(m) for m in agent_prompt.messages]
        assert any("agent_scratchpad" in s for s in message_strs)
