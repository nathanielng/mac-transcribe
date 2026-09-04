#!/usr/bin/env python3
"""
Transcript + Outline -> HTML merger.

Combines a `{id}-{slug}-claude-transcript.md` file and its matching
`{id}-{slug}-claude-outline.md` file into a single self-contained HTML page,
styled per the `html-guide-style` skill (dark theme, rail-collapsing sidebar
with active-section highlighting). The transcript's title and URL go in the
page header. The body is an Overview section, one block per outline section
(each with its own Summary / Transcript toggle, using each section's
`<!-- anchor: "..." -->` snippet to locate its boundary in the transcript),
and a Key Takeaways section.

Usage:
    python merge-html.py <transcript.md> [outline.md] [--path-only]

If outline.md is omitted, it's derived from the transcript filename using the
`-claude-transcript.md` -> `-claude-outline.md` naming convention.
"""

import base64
import re
import sys
from pathlib import Path
from html import escape
from string import Template


def resolve_outline_path(transcript: Path) -> Path:
    stem = transcript.stem
    if stem.endswith("-claude-transcript"):
        stem = stem[: -len("-claude-transcript")]
        return transcript.parent / f"{stem}-claude-outline.md"
    return transcript.parent / f"{stem}-outline.md"


def resolve_output_path(transcript: Path) -> Path:
    stem = re.sub(r"-claude-transcript$", "", transcript.stem)
    return transcript.parent / f"{stem}-claude.html"


def parse_transcript(text: str):
    lines = text.splitlines()
    title, date, sources, body_start = "Untitled", "", "", 0

    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
        m = re.match(r"-\s*\*\*Date:\*\*\s*(.+)", line)
        if m:
            date = m.group(1).strip()
        m = re.match(r"-\s*\*\*Sources:\*\*\s*(.+)", line)
        if m:
            sources = m.group(1).strip()
        if line.strip() == "## Transcript":
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:]).strip()
    normalized = re.sub(r"\s+", " ", body).strip()
    return title, date, sources, normalized


# --- Minimal markdown -> HTML converter (headers, bold/italic, blockquotes, tables, hr, paragraphs) ---

def inline(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"\[\[(.+?)\]\]", r"\1", text)
    return text


def convert_markdown(md: str) -> str:
    lines = md.splitlines()
    html, i, para_buf = [], 0, []

    def flush_para():
        if para_buf:
            text = " ".join(para_buf).strip()
            if text:
                html.append(f"<p>{inline(text)}</p>")
            para_buf.clear()

    while i < len(lines):
        stripped = lines[i].strip()

        if stripped == "---":
            flush_para()
            html.append("<hr>")
            i += 1
        elif stripped.startswith("#"):
            flush_para()
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            html.append(f"<h{level}>{inline(stripped[level:].strip())}</h{level}>")
            i += 1
        elif stripped.startswith(">"):
            flush_para()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            html.append(f'<div class="callout">{inline(" ".join(quote))}</div>')
        elif stripped.startswith("|"):
            flush_para()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            html.append(render_table(table_lines))
        elif stripped == "":
            flush_para()
            i += 1
        else:
            para_buf.append(stripped)
            i += 1

    flush_para()
    return "\n".join(html)


def render_table(table_lines) -> str:
    rows = [
        [c.strip() for c in row.strip("|").split("|")]
        for row in table_lines
        if not re.match(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$", row)
    ]
    if not rows:
        return ""
    header, *body = rows
    out = ['<div class="table-wrap"><table>', "<thead><tr>"]
    out += [f"<th>{inline(c)}</th>" for c in header]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


# --- Structural outline parsing ---

ANCHOR_RE = re.compile(r'<!--\s*anchor:\s*"(.*?)"\s*-->')


def strip_frontmatter(outline_md: str) -> str:
    parts = outline_md.split("\n---\n", 1)
    if len(parts) == 2 and (
        parts[0].lstrip().startswith("# Outline:") or "**Source:**" in parts[0]
    ):
        return parts[1].strip()
    return outline_md


def parse_outline(outline_md: str):
    """Returns (overview_html, sections, footer_html).

    sections: list of {title, anchor, html} in document order.
    footer_html: everything from the Key Takeaways heading onward (table + any conclusion).
    """
    body = strip_frontmatter(outline_md)
    chunks = body.split("\n---\n")
    overview_chunk = chunks[0] if chunks else ""
    rest = "\n---\n".join(chunks[1:]) if len(chunks) > 1 else ""

    kt_match = re.search(r"(?m)^## Key Takeaways", rest)
    sections_chunk = rest[: kt_match.start()] if kt_match else rest
    footer_chunk = rest[kt_match.start():] if kt_match else ""
    footer_chunk = re.sub(r"^## Key Takeaways\s*\n", "", footer_chunk)

    sections = []
    parts = re.split(r"(?m)^## ", sections_chunk)
    for part in parts:
        if not part.strip():
            continue
        lines = part.splitlines()
        title = lines[0].strip()
        rest_text = "\n".join(lines[1:])
        anchor_match = ANCHOR_RE.search(rest_text)
        anchor = anchor_match.group(1).strip() if anchor_match else None
        rest_text = ANCHOR_RE.sub("", rest_text)
        sections.append({
            "title": title,
            "anchor": anchor,
            "html": convert_markdown(rest_text),
        })

    overview_html = convert_markdown(overview_chunk)
    footer_html = convert_markdown(footer_chunk)
    return overview_html, sections, footer_html


def slice_transcript(normalized_transcript: str, sections):
    """Locate each section's anchor in the transcript and return a parallel list
    of transcript-slice strings (plain text, one per section). Falls back to an
    empty slice with a note when an anchor can't be found."""
    positions = []
    for s in sections:
        pos = None
        if s["anchor"]:
            anchor_norm = re.sub(r"\s+", " ", s["anchor"]).strip()
            pos = normalized_transcript.find(anchor_norm)
            if pos == -1:
                pos = normalized_transcript.lower().find(anchor_norm.lower())
        positions.append(pos)

    slices = [None] * len(sections)
    found = [(i, p) for i, p in enumerate(positions) if p is not None and p != -1]

    for k, (i, pos) in enumerate(found):
        start = pos
        if k == 0 and start > 0:
            start = 0  # capture any leading transcript text in the first found section
        end = found[k + 1][1] if k + 1 < len(found) else len(normalized_transcript)
        slices[i] = normalized_transcript[start:end].strip()

    for i, s in enumerate(slices):
        if s is None:
            sections[i]["anchor_missing"] = True
            slices[i] = "(Could not locate this section's transcript excerpt automatically.)"

    return slices


def build_blocks(sections, transcript_slices) -> str:
    blocks = []
    for idx, (sec, slice_text) in enumerate(zip(sections, transcript_slices)):
        transcript_html = "".join(f"<p>{inline(p)}</p>" for p in [slice_text] if p)
        blocks.append(f"""
<section id="outline-h2-{idx}">
  <div class="block-header">
    <h2><span class="icon">📄</span> {inline(sec['title'])}</h2>
    <div class="toggle" role="tablist">
      <button class="toggle-btn active" data-view="summary" role="tab" aria-selected="true">Summary</button>
      <button class="toggle-btn" data-view="transcript" role="tab" aria-selected="false">Transcript</button>
    </div>
  </div>
  <div class="view view-summary active">
    {sec['html']}
  </div>
  <div class="view view-transcript">
    {transcript_html}
  </div>
</section>""")
    return "\n".join(blocks)


def build_nav(sections) -> str:
    items = ['<li><a href="#overview">Overview</a></li>']
    items += [f'<li><a href="#outline-h2-{i}">{inline(s["title"])}</a></li>' for i, s in enumerate(sections)]
    items.append('<li><a href="#key-takeaways">Key Takeaways</a></li>')
    return "".join(items)


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
  :root {
    --bg: #1B1B2F; --surface: #22223A; --surface2: #2A2A45;
    --accent: #00B4D8; --accent2: #48CAE4; --text: #E0E0E0;
    --muted: #999999; --light: #CCCCCC; --border: #3a3a5c;
    --table-header: #00769E; --table-even: #2A2A45; --table-odd: #22223A;
    --btn-active-fg: #10131c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; }
  body {
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 16px; line-height: 1.7; display: flex; min-height: 100vh;
  }

  nav {
    width: 260px; min-width: 260px; background: var(--surface); border-right: 1px solid var(--border);
    padding: 1.2rem 1rem 2rem; position: sticky; top: 0; height: 100vh;
    overflow-y: auto; overflow-x: hidden;
    transition: width 0.22s ease, min-width 0.22s ease, padding 0.22s ease;
  }
  nav.collapsed { width: 48px; min-width: 48px; padding: 1.2rem 0.4rem 2rem; }
  nav.collapsed .nav-inner { opacity: 0; pointer-events: none; }
  .nav-inner { transition: opacity 0.15s ease; }
  .nav-toggle { display: flex; align-items: center; justify-content: flex-end; margin-bottom: 1rem; }
  .nav-toggle button, .nav-expand {
    background: var(--surface2); border: 1px solid var(--border); border-radius: 6px;
    color: var(--muted); cursor: pointer; padding: 0.3rem 0.45rem; line-height: 1;
    font-size: 0.9rem; transition: color 0.15s, background 0.15s;
  }
  .nav-toggle button:hover, .nav-expand:hover { color: var(--accent); background: #2e2e4a; }
  .nav-expand { display: none; position: absolute; top: 1.2rem; left: 50%; transform: translateX(-50%); }
  nav.collapsed .nav-expand { display: block; }
  nav.collapsed .nav-toggle { display: none; }
  nav .logo { font-size: 1.05rem; font-weight: 700; color: var(--accent); margin-bottom: 0.3rem; }
  nav .subtitle { font-size: 0.75rem; color: var(--muted); margin-bottom: 1.5rem; word-break: break-all; }
  nav ul { list-style: none; }
  nav ul li { margin: 0.15rem 0; }
  nav ul li a {
    display: block; padding: 0.35rem 0.6rem; border-radius: 6px; color: var(--light);
    text-decoration: none; font-size: 0.85rem; transition: background 0.15s, color 0.15s;
    border-left: 3px solid transparent;
  }
  nav ul li a:hover { background: var(--surface2); color: var(--accent2); }
  nav ul li a.active { background: #1e3a42; color: var(--accent); border-left-color: var(--accent); font-weight: 600; }

  main { flex: 1; max-width: 860px; padding: 3rem 3rem 5rem; overflow-x: hidden; }

  .page-header { margin-bottom: 3rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); }
  .page-header h1 { font-size: 2rem; color: var(--accent); font-weight: 800; margin-bottom: 0.5rem; }
  .page-header .meta { display: flex; gap: 1rem; flex-wrap: wrap; }
  .badge {
    display: inline-flex; align-items: center; gap: 0.3rem; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 20px; padding: 0.2rem 0.7rem;
    font-size: 0.78rem; color: var(--light);
  }
  .badge a { color: var(--accent2); text-decoration: none; }
  .badge a:hover { text-decoration: underline; }

  section { margin-bottom: 3rem; scroll-margin-top: 1rem; }
  h2 {
    font-size: 1.4rem; color: var(--accent); font-weight: 700; margin-bottom: 1rem;
    padding-bottom: 0.4rem; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 0.5rem;
  }
  h2 .icon { font-size: 1.1rem; }
  p { margin-bottom: 0.8rem; color: var(--light); }

  .table-wrap { overflow-x: auto; margin: 0.8rem 0 1rem; border-radius: 8px; border: 1px solid var(--border); }
  table { width: 100%; border-collapse: collapse; }
  thead th { background: var(--table-header); color: #fff; padding: 0.6rem 1rem; text-align: left; font-size: 0.85rem; font-weight: 600; }
  tbody tr:nth-child(even) td { background: var(--table-even); }
  tbody tr:nth-child(odd) td { background: var(--table-odd); }
  tbody tr:hover td { background: #323255; }
  td { padding: 0.5rem 1rem; font-size: 0.875rem; border-top: 1px solid var(--border); color: var(--light); vertical-align: top; }

  .callout {
    background: var(--surface2); border-left: 3px solid var(--accent); border-radius: 0 8px 8px 0;
    padding: 0.8rem 1.1rem; margin: 0.8rem 0 1rem; font-size: 0.9rem; color: var(--light); font-style: italic;
  }

  .badge-btn {
    all: unset; display: inline-flex; align-items: center; gap: 0.3rem; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 20px; padding: 0.2rem 0.7rem;
    font-size: 0.78rem; color: var(--light); cursor: pointer; box-sizing: border-box;
  }
  .badge-btn:hover { background: #2e2e4a; color: var(--accent2); }

  .block-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .block-header h2 { margin: 0; border-bottom: none; padding-bottom: 0; flex: 1; }
  .toggle { display: inline-flex; background: var(--surface2); border: 1px solid var(--border); border-radius: 999px; padding: 2px; }
  .toggle-btn {
    border: none; background: transparent; color: var(--light); font-size: 0.82rem;
    padding: 0.3rem 0.9rem; border-radius: 999px; cursor: pointer;
  }
  .toggle-btn.active { background: var(--accent); color: var(--btn-active-fg); font-weight: 600; }
  .view { display: none; }
  .view.active { display: block; }

  @media (max-width: 900px) {
    nav { display: none; }
    main { padding: 2rem 1.5rem 4rem; max-width: 100%; }
  }
</style>
</head>
<body>

<nav id="sidebar">
  <button class="nav-expand" id="navExpand" title="Expand sidebar">&#x276F;</button>
  <div class="nav-inner">
    <div class="nav-toggle">
      <button id="navCollapse" title="Collapse sidebar">&#x276E;</button>
    </div>
    <div class="logo">Contents</div>
    <div class="subtitle">$title</div>
    <ul id="navLinks">
      $nav_html
    </ul>
  </div>
</nav>

<main>
  <div class="page-header">
    <h1>$title</h1>
    <div class="meta">
      <span class="badge">📅 $date</span>
      <span class="badge">🎙️ $sources</span>
      <button class="badge-btn" id="downloadTranscriptBtn">⬇️ Download Transcript</button>
    </div>
  </div>

  <section id="overview">
    <h2><span class="icon">📝</span> Overview</h2>
    $overview_html
  </section>

  $blocks_html

  <section id="key-takeaways">
    <h2><span class="icon">✅</span> Key Takeaways</h2>
    $footer_html
  </section>
</main>

<script>
  // The original transcript.md, base64-encoded, embedded so the "Download
  // Transcript" button works even if transcript.md itself has since been
  // deleted from disk — this HTML page is meant to be the thing that
  // survives after mp3/transcript cleanup. Base64 (rather than a plain JS
  // string literal) sidesteps needing to escape quotes/backslashes/
  // "</script>" sequences that might appear in real transcript text.
  const TRANSCRIPT_B64 = "$transcript_b64";
  const TRANSCRIPT_FILENAME = "$transcript_filename";
  document.getElementById('downloadTranscriptBtn').addEventListener('click', () => {
    const binary = atob(TRANSCRIPT_B64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const text = new TextDecoder('utf-8').decode(bytes);
    const blob = new Blob([text], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = TRANSCRIPT_FILENAME;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  const sidebar = document.getElementById('sidebar');
  document.getElementById('navCollapse').addEventListener('click', () => sidebar.classList.add('collapsed'));
  document.getElementById('navExpand').addEventListener('click', () => sidebar.classList.remove('collapsed'));

  const sections = document.querySelectorAll('main section[id]');
  const navLinks = document.querySelectorAll('#navLinks a');

  function setActive(id) {
    navLinks.forEach(a => {
      const isActive = a.getAttribute('href') === '#' + id;
      a.classList.toggle('active', isActive);
      if (isActive) a.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
  }

  const visible = new Map();
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => visible.set(e.target.id, e.isIntersecting));
    for (const section of sections) {
      if (visible.get(section.id)) { setActive(section.id); return; }
    }
  }, { rootMargin: '0px 0px -60% 0px', threshold: 0 });
  sections.forEach(s => observer.observe(s));

  document.querySelectorAll('section').forEach(function (block) {
    block.querySelectorAll('.toggle-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var view = btn.dataset.view;
        block.querySelectorAll('.toggle-btn').forEach(function (b) {
          b.classList.toggle('active', b === btn);
          b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
        });
        block.querySelectorAll('.view').forEach(function (v) {
          v.classList.toggle('active', v.classList.contains('view-' + view));
        });
      });
    });
  });
</script>
</body>
</html>
"""


def build_html(transcript_path: Path, outline_path: Path, output_path: Path) -> list[str]:
    """Builds the merged HTML page. Returns a list of warning strings (non-fatal)."""
    warnings = []

    raw_transcript_text = transcript_path.read_text()
    title, date, sources, normalized_transcript = parse_transcript(raw_transcript_text)
    overview_html, sections, footer_html = parse_outline(outline_path.read_text())

    if not sections:
        raise ValueError("no sections found in outline (expected '## N. Title' headings)")

    missing = [s["title"] for s in sections if not s["anchor"]]
    if missing:
        warnings.append(f"{len(missing)} section(s) missing an <!-- anchor: ... --> comment: {missing}")

    transcript_slices = slice_transcript(normalized_transcript, sections)
    blocks_html = build_blocks(sections, transcript_slices)
    nav_html = build_nav(sections)

    transcript_b64 = base64.b64encode(raw_transcript_text.encode("utf-8")).decode("ascii")
    title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "transcript"

    # Template (stdlib string.Template, $-style) rather than str.format():
    # PAGE_TEMPLATE is mostly literal CSS/JS, which uses { and } constantly.
    # .format() required doubling every single one of those as {{ }} to
    # keep them literal — easy to get wrong when editing the template, and
    # the kind of mistake that only surfaces as a KeyError/mangled page at
    # render time. Template's $name placeholders don't collide with CSS/JS
    # syntax at all, so the template body is just normal CSS/JS with no
    # escaping anywhere. (Substituted values are inserted verbatim and are
    # never re-scanned for $ or { — confirmed directly — so this is about
    # template maintainability, not a live substitution-safety bug.)
    page = Template(PAGE_TEMPLATE).substitute(
        title=escape(title),
        date=escape(date),
        sources=escape(sources),
        overview_html=overview_html,
        nav_html=nav_html,
        footer_html=footer_html,
        blocks_html=blocks_html,
        transcript_b64=transcript_b64,
        transcript_filename=f"{title_slug}-transcript.md",
    )

    output_path.write_text(page)

    unresolved = [s["title"] for s in sections if s.get("anchor_missing")]
    if unresolved:
        warnings.append(f"{len(unresolved)} section(s) could not be matched to a transcript slice: {unresolved}")

    return warnings


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)

    transcript_path = Path(args[0]).expanduser().resolve()
    if not transcript_path.exists():
        print(f"Error: transcript file not found: {transcript_path}", file=sys.stderr)
        sys.exit(1)

    outline_path = (
        Path(args[1]).expanduser().resolve() if len(args) > 1
        else resolve_outline_path(transcript_path)
    )
    if not outline_path.exists():
        print(f"Error: outline file not found: {outline_path}", file=sys.stderr)
        sys.exit(1)

    output_path = resolve_output_path(transcript_path)
    if "--path-only" in sys.argv:
        print(output_path)
        return

    try:
        warnings = build_html(transcript_path, outline_path, output_path)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Saved: {output_path}")
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
