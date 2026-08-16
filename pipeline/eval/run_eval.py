#!/usr/bin/env python3
"""Outline-quality eval harness: generates outlines for each synthetic
transcript under eval/transcripts/ with several candidate backends/models,
then uses Claude Sonnet 5 (the "ground truth" model) as an LLM judge to score
each candidate's outline against its own ground-truth outline for the same
transcript.

Usage (from pipeline/):
    python3 -m eval.run_eval
    python3 -m eval.run_eval --transcript sales-discovery-call
    python3 -m eval.run_eval --skip-judge   # just generate outlines, no scoring

Requires the same credentials/deps as the main pipeline: AWS Bedrock access
for the "bedrock-*" candidates and ground truth, mlx-lm installed for the
"mlx-*" candidates (uv pip install -e ".[mlx_lm]").

Results land in eval/results/<transcript-stem>/<candidate>.md (outlines) and
eval/results/report.md (scores + rationale, generated after all candidates
for a transcript have run).
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mac_transcribe.config import load_config  # noqa: E402
from mac_transcribe.html import parse_transcript  # noqa: E402
from mac_transcribe.llm_backend import OutlineAuthError, generate_text  # noqa: E402
from mac_transcribe.outline import OUTLINE_PROMPT  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
TRANSCRIPTS_DIR = EVAL_DIR / "transcripts"
RESULTS_DIR = EVAL_DIR / "results"

GROUND_TRUTH_NAME = "ground-truth-sonnet-5"


@dataclass
class Candidate:
    name: str
    cfg_overrides: dict = field(default_factory=dict)


# Ground truth is Claude Sonnet 5 via Bedrock — the base config default.
# Candidates being evaluated against it: the open-weight Bedrock models and
# the local MLX options offered in Settings.
CANDIDATES = [
    Candidate(GROUND_TRUTH_NAME, {"outline_backend": "bedrock", "bedrock_model": "global.anthropic.claude-sonnet-5"}),
    Candidate("bedrock-deepseek-v3.2", {"outline_backend": "bedrock", "bedrock_model": "deepseek.v3.2"}),
    Candidate("bedrock-qwen3-235b", {"outline_backend": "bedrock", "bedrock_model": "qwen.qwen3-vl-235b-a22b"}),
    Candidate("mlx-qwen3.5-4b", {"outline_backend": "mlx_lm", "mlx_outline_model": "mlx-community/Qwen3.5-4B-MLX-4bit"}),
    Candidate("mlx-qwen3.5-9b", {"outline_backend": "mlx_lm", "mlx_outline_model": "mlx-community/Qwen3.5-9B-MLX-4bit"}),
]

JUDGE_PROMPT = """You are evaluating an AI-generated outline of a transcript against a \
trusted ground-truth outline of the same transcript.

Score the CANDIDATE outline from 1-10 on how well it matches the GROUND TRUTH outline's \
coverage, factual accuracy, and structure — not on writing style. A candidate that covers \
the same key points and takeaways as the ground truth, even with different wording or \
section boundaries, should score highly. Penalize missing key points, factual errors \
relative to the transcript, or fabricated content not in the transcript.

Respond in EXACTLY this format, nothing else:

SCORE: <integer 1-10>
RATIONALE: <2-3 sentences>

TRANSCRIPT:
{transcript}

GROUND TRUTH OUTLINE:
{ground_truth}

CANDIDATE OUTLINE:
{candidate}
"""


def generate_for_candidate(transcript_md: str, title: str, candidate: Candidate) -> str:
    cfg = load_config()
    cfg.update(candidate.cfg_overrides)
    prompt = OUTLINE_PROMPT.format(title=title, transcript=transcript_md)
    return generate_text(prompt, cfg, max_tokens=4096)


def judge(transcript_md: str, ground_truth_outline: str, candidate_outline: str) -> tuple[int | None, str]:
    cfg = load_config()
    cfg["outline_backend"] = "bedrock"
    cfg["bedrock_model"] = "global.anthropic.claude-sonnet-5"
    prompt = JUDGE_PROMPT.format(transcript=transcript_md, ground_truth=ground_truth_outline, candidate=candidate_outline)
    response = generate_text(prompt, cfg, max_tokens=300)

    score_match = re.search(r"SCORE:\s*(\d+)", response)
    rationale_match = re.search(r"RATIONALE:\s*(.+)", response, re.DOTALL)
    score = int(score_match.group(1)) if score_match else None
    rationale = rationale_match.group(1).strip() if rationale_match else response.strip()
    return score, rationale


def run_transcript(transcript_path: Path, skip_judge: bool) -> dict:
    transcript_md = transcript_path.read_text()
    title, _date, _sources, _normalized = parse_transcript(transcript_md)
    stem = transcript_path.stem
    out_dir = RESULTS_DIR / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    outlines: dict[str, str] = {}
    errors: dict[str, str] = {}

    for candidate in CANDIDATES:
        print(f"  [{stem}] generating outline: {candidate.name} ...", flush=True)
        try:
            outline_md = generate_for_candidate(transcript_md, title, candidate)
            outlines[candidate.name] = outline_md
            (out_dir / f"{candidate.name}.md").write_text(outline_md)
        except OutlineAuthError as e:
            errors[candidate.name] = f"auth: {e}"
            print(f"    FAILED (auth): {e}")
        except Exception as e:
            errors[candidate.name] = str(e)
            print(f"    FAILED: {e}")

    scores: dict[str, tuple[int | None, str]] = {}
    if not skip_judge and GROUND_TRUTH_NAME in outlines:
        ground_truth_outline = outlines[GROUND_TRUTH_NAME]
        for candidate in CANDIDATES:
            if candidate.name == GROUND_TRUTH_NAME or candidate.name not in outlines:
                continue
            print(f"  [{stem}] judging: {candidate.name} ...", flush=True)
            try:
                scores[candidate.name] = judge(transcript_md, ground_truth_outline, outlines[candidate.name])
            except Exception as e:
                scores[candidate.name] = (None, f"judge failed: {e}")
    elif not skip_judge:
        print(f"  [{stem}] skipping judge pass — ground truth generation failed, nothing to score against")

    return {"title": title, "errors": errors, "scores": scores}


def write_report(results: dict[str, dict]) -> None:
    lines = ["# Outline Eval Report", ""]
    lines.append(f"Ground truth: Claude Sonnet 5 (Bedrock, `global.anthropic.claude-sonnet-5`)")
    lines.append("")

    for stem, result in results.items():
        lines.append(f"## {result['title']} (`{stem}`)")
        lines.append("")
        if result["errors"]:
            lines.append("**Generation failures:**")
            for name, err in result["errors"].items():
                lines.append(f"- `{name}`: {err}")
            lines.append("")
        if result["scores"]:
            lines.append("| Candidate | Score | Rationale |")
            lines.append("|---|---|---|")
            for name, (score, rationale) in result["scores"].items():
                score_str = str(score) if score is not None else "—"
                lines.append(f"| {name} | {score_str} | {rationale} |")
            lines.append("")

    # Aggregate averages across transcripts, per candidate.
    all_candidates = {c.name for c in CANDIDATES if c.name != GROUND_TRUTH_NAME}
    lines.append("## Averages across all transcripts")
    lines.append("")
    lines.append("| Candidate | Average Score | Transcripts Scored |")
    lines.append("|---|---|---|")
    for name in all_candidates:
        scored = [r["scores"][name][0] for r in results.values() if name in r["scores"] and r["scores"][name][0] is not None]
        avg = f"{sum(scored) / len(scored):.1f}" if scored else "—"
        lines.append(f"| {name} | {avg} | {len(scored)} |")

    report_path = RESULTS_DIR / "report.md"
    report_path.write_text("\n".join(lines))
    print(f"\nReport written to {report_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--transcript", help="Only run this transcript (by filename stem)")
    parser.add_argument("--skip-judge", action="store_true", help="Only generate outlines, skip LLM-judge scoring")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    transcript_paths = sorted(TRANSCRIPTS_DIR.glob("*.md"))
    if args.transcript:
        transcript_paths = [p for p in transcript_paths if p.stem == args.transcript]
        if not transcript_paths:
            print(f"No transcript found matching stem {args.transcript!r} in {TRANSCRIPTS_DIR}", file=sys.stderr)
            sys.exit(1)

    results = {}
    for path in transcript_paths:
        print(f"Transcript: {path.stem}")
        results[path.stem] = run_transcript(path, args.skip_judge)

    write_report(results)


if __name__ == "__main__":
    main()
