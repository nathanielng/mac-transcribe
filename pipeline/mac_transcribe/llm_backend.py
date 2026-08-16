"""Dispatches a single "generate text from this prompt" call to whichever
backend outline_backend selects, so outline.py and title.py don't each
duplicate the Bedrock-vs-local-MLX branching.

Bedrock path: Amazon Bedrock (Claude Sonnet 5 by default; any Bedrock-hosted
model works via config, including open-weight alternatives like DeepSeek V3.2
or Qwen3-235B). Requires AWS credentials.

mlx_lm path: fully local generation via the mlx-lm package (a separate
optional dependency — this app only requires it if outline_backend is set to
"mlx_lm", so a Bedrock-only install never needs to download an LLM). Runs
entirely on-device, same as mlx-whisper's transcription.
"""

import threading

from .bedrock import get_client, is_auth_error

# process.py runs outline + title generation concurrently; without this,
# choosing outline_backend = "mlx_lm" would load the (multi-GB) model twice
# in parallel and waste memory/time. Cache + lock together (not lru_cache
# alone) so a cache-miss in one thread blocks a concurrent cache-miss in the
# other rather than both racing into load().
_model_cache: dict[str, tuple] = {}
_load_lock = threading.Lock()


def _load_mlx_model(model: str):
    with _load_lock:
        if model not in _model_cache:
            from mlx_lm import load

            _model_cache[model] = load(model)
        return _model_cache[model]


class OutlineAuthError(Exception):
    """Raised when the Bedrock call fails due to missing/expired AWS credentials."""


def generate_text(prompt: str, cfg: dict, max_tokens: int) -> str:
    backend = cfg.get("outline_backend", "bedrock")
    if backend == "mlx_lm":
        return _generate_mlx_lm(prompt, cfg["mlx_outline_model"], max_tokens)
    if backend == "bedrock":
        return _generate_bedrock(prompt, cfg["bedrock_model"], cfg["bedrock_region"], cfg["bedrock_profile"], max_tokens)
    raise ValueError(f"Unknown outline_backend: {backend!r} (expected 'bedrock' or 'mlx_lm')")


def _generate_bedrock(prompt: str, model: str, region: str, profile: str, max_tokens: int) -> str:
    client = get_client(region, profile)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        if is_auth_error(e):
            raise OutlineAuthError(str(e)) from e
        raise

    return response.content[0].text.strip()


def _generate_mlx_lm(prompt: str, model: str, max_tokens: int) -> str:
    try:
        from mlx_lm import generate
    except ImportError as e:
        raise RuntimeError(
            "outline_backend is 'mlx_lm' but the mlx-lm package isn't installed. "
            "Install it with: uv pip install -e '.[mlx_lm]'"
        ) from e

    model_obj, tokenizer = _load_mlx_model(model)
    messages = [{"role": "user", "content": prompt}]
    formatted = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
    return generate(model_obj, tokenizer, prompt=formatted, max_tokens=max_tokens).strip()
