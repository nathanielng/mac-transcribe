"""Shared Bedrock client + auth-error classification for outline.py and title.py.

Uses the AnthropicBedrock client (Claude Sonnet 5 via the Global cross-region
inference profile) instead of the direct Anthropic API, so this reuses whatever
AWS credentials are already configured (profile, SSO, env vars) rather than
requiring a separate ANTHROPIC_API_KEY.
"""

import os

import anthropic
import botocore.exceptions

# Credential/auth failures can surface either as botocore exceptions (raised
# before any HTTP call, e.g. no credentials or expired SSO token) or as
# anthropic SDK exceptions (raised from the HTTP response, e.g. AccessDenied
# on the Bedrock API itself). Both mean "the user needs to re-authenticate".
AUTH_ERROR_TYPES = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
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


def get_client(region: str, profile: str | None = None) -> anthropic.AnthropicBedrock:
    # AnthropicBedrock reads AWS_BEARER_TOKEN_BEDROCK from the environment by
    # default (api_key = os.environ.get(...) happens unconditionally before any
    # of our args are considered). If that var AND SigV4 credentials (profile,
    # explicit keys) are both present, the SDK raises ValueError rather than
    # picking one — it never silently prefers SigV4. Since we always want
    # IAM/SigV4 auth here, clear the bearer token in this process first.
    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    return anthropic.AnthropicBedrock(aws_region=region, aws_profile=profile or "default")
