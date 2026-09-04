import pytest

from mac_transcribe.bedrock import converse


class FakeClient:
    """Records the request converse() builds and returns a canned response."""

    def __init__(self, content_blocks):
        self.content_blocks = content_blocks
        self.last_kwargs = None

    def converse(self, **kwargs):
        self.last_kwargs = kwargs
        return {"output": {"message": {"content": self.content_blocks}}}


def test_converse_returns_text_block():
    client = FakeClient([{"text": "the outline text"}])

    result = converse(client, "deepseek.v3.2", "prompt", max_tokens=100)

    assert result == "the outline text"


def test_converse_finds_text_block_after_reasoning_block():
    """Real bug: Claude Sonnet 5 with extended thinking returns a
    reasoningContent block before the text block, and the old code
    unconditionally read content[0]['text'], raising KeyError: 'text'."""
    client = FakeClient([
        {"reasoningContent": {"reasoningText": {"text": "thinking..."}}},
        {"text": "the actual outline"},
    ])

    result = converse(client, "global.anthropic.claude-sonnet-5", "prompt", max_tokens=100)

    assert result == "the actual outline"


def test_converse_raises_descriptive_error_when_no_text_block():
    client = FakeClient([{"reasoningContent": {"reasoningText": {"text": "thinking..."}}}])

    with pytest.raises(RuntimeError, match="no text block"):
        converse(client, "global.anthropic.claude-sonnet-5", "prompt", max_tokens=100)


def test_converse_disables_thinking_for_anthropic_models():
    client = FakeClient([{"text": "ok"}])

    converse(client, "global.anthropic.claude-sonnet-5", "prompt", max_tokens=100)

    assert client.last_kwargs["additionalModelRequestFields"] == {"thinking": {"type": "disabled"}}


def test_converse_does_not_send_thinking_field_for_non_anthropic_models():
    client = FakeClient([{"text": "ok"}])

    converse(client, "deepseek.v3.2", "prompt", max_tokens=100)

    assert "additionalModelRequestFields" not in client.last_kwargs


def test_converse_passes_max_tokens_through():
    client = FakeClient([{"text": "ok"}])

    converse(client, "deepseek.v3.2", "prompt", max_tokens=8192)

    assert client.last_kwargs["inferenceConfig"] == {"maxTokens": 8192}
