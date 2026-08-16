"""Shared Bedrock client + auth-error classification for llm_backend.py.

Uses boto3's bedrock-runtime Converse API rather than the `anthropic` SDK's
AnthropicBedrock client, because AnthropicBedrock only speaks Claude's wire
format — it silently fails against non-Anthropic models (confirmed with a
real call: DeepSeek/Qwen return an unhandled 'NoneType is not subscriptable'
error through that SDK). Converse is Bedrock's model-agnostic chat API and
works identically across Claude, DeepSeek, and Qwen, which is what this app
needs now that outline generation can target any of them.
"""

import os

import boto3
import botocore.exceptions

AUTH_ERROR_TYPES = (
    botocore.exceptions.NoCredentialsError,
    botocore.exceptions.UnauthorizedSSOTokenError,
    botocore.exceptions.TokenRetrievalError,
)


def is_auth_error(exc: Exception) -> bool:
    if isinstance(exc, AUTH_ERROR_TYPES):
        return True
    if isinstance(exc, botocore.exceptions.ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code in ("ExpiredTokenException", "UnrecognizedClientException", "AccessDeniedException")
    return False


def get_client(region: str, profile: str | None = None):
    # Same issue as when this used AnthropicBedrock: boto3's bedrock-runtime
    # client also resolves AWS_BEARER_TOKEN_BEDROCK if present, and it takes
    # priority over SigV4 (confirmed with a real call) rather than falling
    # back gracefully — surfaces as a confusing AccessDeniedException instead
    # of using valid IAM credentials that are also configured. Since this app
    # always intends IAM/SigV4, clear it before constructing the client.
    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    session = boto3.Session(profile_name=profile or "default", region_name=region)
    return session.client("bedrock-runtime")


def converse(client, model: str, prompt: str, max_tokens: int) -> str:
    response = client.converse(
        modelId=model,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens},
    )
    return response["output"]["message"]["content"][0]["text"]
