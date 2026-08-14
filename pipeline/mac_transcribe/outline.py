"""Stage 3a: generate outline.md from transcript.md via Amazon Bedrock
(Claude Sonnet 4.6, Global cross-region inference profile) — no dependency on
Claude Code being installed/running.

Format mirrors the ~/.claude/skills/outline skill's output, which
mac_transcribe/html.py's merge logic expects: an overview, '## N. Title'
sections each with an <!-- anchor: "..." --> snippet, and a Key Takeaways table.
"""

from pathlib import Path

from .bedrock import get_client, is_auth_error

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


class OutlineAuthError(Exception):
    """Raised when the Bedrock call fails due to missing/expired AWS credentials."""


def generate_outline(transcript_md: str, title: str, model: str, region: str) -> str:
    client = get_client(region)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": OUTLINE_PROMPT.format(title=title, transcript=transcript_md),
                }
            ],
        )
    except Exception as e:
        if is_auth_error(e):
            raise OutlineAuthError(str(e)) from e
        raise

    return response.content[0].text.strip()


def run(session_dir: Path, title: str, model: str, region: str) -> Path:
    transcript_path = session_dir / "transcript.md"
    transcript_md = transcript_path.read_text()

    outline_md = generate_outline(transcript_md, title, model, region)

    out_path = session_dir / "outline.md"
    out_path.write_text(outline_md)
    return out_path
