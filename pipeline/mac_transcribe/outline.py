"""Stage 3a: generate outline.md from transcript.md — backend selected by
config's outline_backend (Bedrock or fully-local mlx_lm, see llm_backend.py).
No dependency on Claude Code being installed/running either way.

Format mirrors the ~/.claude/skills/outline skill's output, which
mac_transcribe/html.py's merge logic expects: an overview, '## N. Title'
sections each with an <!-- anchor: "..." --> snippet, and a Key Takeaways table.
"""

from pathlib import Path

from .llm_backend import OutlineAuthError, generate_text

OUTLINE_PROMPT = """You will be given a transcript of a recorded conversation or meeting. \
Produce a structured outline of it in EXACTLY this markdown format (nothing before or after):

# Outline: {title}
- **Source:** local recording
---
<2-4 sentence overview of what this recording covers>
---
## 1. <Section title>
<!-- anchor: "<a short verbatim snippet (8-15 words) copied EXACTLY from the transcript, marking where this section begins>" -->
**Summary:** <2-4 sentence summary of this section>
---
## 2. <Section title>
<!-- anchor: "..." -->
**Summary:** ...
---
(add as many numbered sections as make sense to cover the whole transcript)
---
## Key Takeaways
| Point | Detail |
|---|---|
| <short takeaway> | <one-sentence elaboration> |
(3-6 rows)

Rules:
- Anchor snippets MUST be copied verbatim from the transcript text (they are used to \
locate each section programmatically) — do not paraphrase them.
- Cover the entire transcript across your sections, in chronological order.
- Keep section titles short (3-8 words).

Transcript:

{transcript}
"""

# Re-exported so existing `from .outline import OutlineAuthError` call sites
# (process.py) keep working unchanged.
__all__ = ["OutlineAuthError", "generate_outline", "run"]


def generate_outline(transcript_md: str, title: str, cfg: dict) -> str:
    prompt = OUTLINE_PROMPT.format(title=title, transcript=transcript_md)
    # 4096 was too tight even without extended thinking for a long
    # transcript with many sections; bedrock.converse() now disables
    # thinking for Claude models outright (outline generation doesn't need
    # step-by-step reasoning), but keep real headroom regardless.
    return generate_text(prompt, cfg, max_tokens=8192)


def run(session_dir: Path, title: str, cfg: dict) -> Path:
    transcript_path = session_dir / "transcript.md"
    transcript_md = transcript_path.read_text()

    outline_md = generate_outline(transcript_md, title, cfg)

    out_path = session_dir / "outline.md"
    out_path.write_text(outline_md)
    return out_path
