"""Tests for agentflow.proxy.hooks — AgentFlowHooks compression bias logic."""

from agentflow.proxy.hooks import AgentFlowHooks


class TestComputeBiases:
    def setup_method(self):
        self.hooks = AgentFlowHooks()

    def test_compute_biases_matches_idx_pattern(self):
        """Message containing .idx line-range pattern gets bias 999.0."""
        messages = [
            {"role": "user", "content": "PTYWrapper.__init__:29-63\nsome other text"},
        ]
        biases = self.hooks.compute_biases(messages)
        assert biases == {0: 999.0}

    def test_compute_biases_ignores_normal_text(self):
        """Message without .idx pattern returns empty dict."""
        messages = [
            {"role": "user", "content": "Just a normal message with no idx pattern"},
        ]
        biases = self.hooks.compute_biases(messages)
        assert biases == {}

    def test_compute_biases_multiline(self):
        """Pattern match works across multiline message content."""
        messages = [
            {"role": "user", "content": "First line\nSecond line"},
            {"role": "assistant", "content": "Line before\nMyClass.method:83-100\nLine after"},
        ]
        biases = self.hooks.compute_biases(messages)
        assert biases == {1: 999.0}

    def test_compute_biases_multiple_messages_with_pattern(self):
        """Multiple messages with patterns all get bias 999.0."""
        messages = [
            {"role": "user", "content": "PTYWrapper:20-139"},
            {"role": "assistant", "content": "no pattern here"},
            {"role": "user", "content": "TokenizerModule.count:5-20"},
        ]
        biases = self.hooks.compute_biases(messages)
        assert biases == {0: 999.0, 2: 999.0}

    def test_compute_biases_list_content_blocks(self):
        """Handles list-format content blocks (Anthropic tool-result format)."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "MyClass.method:10-50"},
                ],
            },
        ]
        biases = self.hooks.compute_biases(messages)
        assert biases == {0: 999.0}

    def test_compute_biases_rejects_partial_match(self):
        """Pattern requires word chars before colon — pure numbers don't match."""
        messages = [
            {"role": "user", "content": "123:45-67"},  # no leading word char
        ]
        biases = self.hooks.compute_biases(messages)
        assert biases == {}

    def test_compute_biases_list_content_multiple_text_blocks(self):
        """Multiple text blocks in content list are joined and matched."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "first block"},
                    {"type": "text", "text": "PTYWrapper.read_output:91-135"},
                ],
            },
        ]
        biases = self.hooks.compute_biases(messages)
        assert biases == {0: 999.0}

    def test_compute_biases_empty_messages(self):
        """Empty messages list returns empty dict without errors."""
        biases = self.hooks.compute_biases([])
        assert biases == {}

    def test_compute_biases_with_ctx_arg(self):
        """compute_biases accepts optional ctx argument (CompressionHooks interface)."""
        messages = [{"role": "user", "content": "MyClass.method:1-10"}]
        biases = self.hooks.compute_biases(messages, ctx=None)
        assert biases == {0: 999.0}
