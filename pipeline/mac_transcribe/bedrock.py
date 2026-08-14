"""Shared Bedrock client + auth-error classification for outline.py and title.py.

Uses the AnthropicBedrock client (Claude Sonnet 4.6 via the Global cross-region
inference profile) instead of the direct Anthropic API, so this reuses whatever
AWS credentials are already configured (profile, SSO, env vars) rather than
requiring a separate ANTHROPIC_API_KEY.
"""

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


def get_client(region: str) -> anthropic.AnthropicBedrock:
    return anthropic.AnthropicBedrock(aws_region=region)
