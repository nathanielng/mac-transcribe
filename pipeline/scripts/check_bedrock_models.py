#!/usr/bin/env python3
"""Manual reference/smoke-check for every Bedrock model this app offers.

NOT a pytest test on purpose — it makes real Bedrock API calls, which cost
real money and require real AWS credentials. It lives outside tests/ (which
pyproject.toml's testpaths points at) specifically so a routine `pytest` run
never invokes it by accident.

Exists as a saved reference for re-verifying "do all the Bedrock models
still work, and does the response shape still look like we expect" without
having to reconstruct the check from scratch each time — e.g. after a
model's default version changes, after touching bedrock.py/converse(), or
when adding a new curated model to Config.swift's BedrockModelOption list.

Checks two things per model, both through the app's actual code path
(mac_transcribe.bedrock.converse/get_client, not raw boto3), matching what
prompted this script: a bug where Claude Sonnet 5's extended thinking put a
reasoningContent block before the text block, and code that assumed
content[0] was always text raised a bare KeyError:
  1. A trivial prompt — establishes the baseline response shape.
  2. A prompt that invites step-by-step reasoning (a word problem) — the
     more realistic trigger for a model to emit non-text content blocks
     (reasoningContent, etc.) ahead of the text block, the exact failure
     mode converse()'s block-scanning exists to handle.

Usage:
    cd pipeline
    source ~/.venv/bin/activate
    python3 scripts/check_bedrock_models.py                  # all curated models
    python3 scripts/check_bedrock_models.py zai.glm-5         # just one

Last run (2026-09-04, us-east-1, profile "default"):
    deepseek.v3.2            OK  (trivial + reasoning prompt, text-only blocks both times)
    qwen.qwen3-vl-235b-a22b  OK  (trivial + reasoning prompt, text-only blocks both times)
    zai.glm-5                OK  (trivial + reasoning prompt, text-only blocks both times)
    global.anthropic.claude-sonnet-5   BLOCKED — model access not enabled on this AWS
        account (AccessDeniedException). The original bug report (reasoningContent
        block before text) was observed on an account that DOES have Sonnet 5
        access — could not personally reproduce/re-verify the raw response shape
        for this model from here. converse()'s block-scanning + thinking-disabled
        fix should still cover it (the scan is provider-agnostic; the
        thinking-disable is applied whenever "anthropic" is in the model ID,
        regardless of which Claude model), but this specific model is the one
        real gap in this script's coverage until Bedrock console access is granted.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mac_transcribe.bedrock import converse, get_client  # noqa: E402

# Keep this in sync with RecorderApp/Sources/RecorderApp/Config.swift's
# BedrockModelOption.recommended list.
CURATED_MODELS = [
    "zai.glm-5",
    "global.anthropic.claude-sonnet-5",
    "deepseek.v3.2",
    "qwen.qwen3-vl-235b-a22b",
]

TRIVIAL_PROMPT = "What is the capital of France? Answer in one word."

# A word problem, not a trivia question — more likely than a trivial prompt
# to induce a model to reason step by step, which is what's most likely to
# surface a reasoning/thinking content block ahead of the text block.
REASONING_PROMPT = (
    "A train leaves station A at 60mph. Another leaves station B, 300 miles "
    "away, at 40mph toward A, 30 minutes later. When do they meet? Show "
    "your reasoning step by step."
)


def check_model(client, model: str, region: str, profile: str) -> None:
    print(f"=== {model} ===")
    for label, prompt, max_tokens in [
        ("trivial", TRIVIAL_PROMPT, 100),
        ("reasoning", REASONING_PROMPT, 1500),
    ]:
        try:
            result = converse(client, model, prompt, max_tokens=max_tokens)
            print(f"  {label}: OK ({len(result)} chars)")
        except Exception as e:
            print(f"  {label}: FAILED — {e!r}")
    print()


def main():
    region = "us-east-1"
    profile = "default"
    client = get_client(region, profile)

    models = sys.argv[1:] or CURATED_MODELS
    for model in models:
        check_model(client, model, region, profile)


if __name__ == "__main__":
    main()
