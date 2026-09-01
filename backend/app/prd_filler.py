"""Deterministic filler for the official Krungsri Nimble PRD template.

The previous approach asked the LLM to reproduce the WHOLE LaTeX body. Small
local models routinely corrupt it (drop ``\\\\`` row terminators, unbalance
braces, over-escape) which made PDF/DOCX export fail. This module instead
FILLS the official template's blank fields from the project's (AI-gathered
and AI-validated) structured data: the skeleton - every table, merged-cell
structure and ``\\newpage`` marker - is always the untouched official
template, so the result is PDF-exact and always compiles.

``fill_template_body`` is deterministic and data-driven. Optional narrative
snippets (AI-written prose) can be supplied per-section; anything absent is
left as an honest placeholder (TBD) instead of invented content.
"""
from __future__ import annotations

import re
from datetime import date as _date
from typing import Any, Dict, List, Optional

from app.prompt_loader import load_prd_latex_template_body

# ---------------------------------------------------------------------------
# LaTeX escaping for inserted values
# ---------------------------------------------------------------------------
_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "_": r"\_",
    "$": r"\$",
    "#": r"\#",
    "{": r"\{",
    "}": r"\}",
    "^": r"\^{}",
    "~": r"\~{}",
}


def escape_latex(value: Any) -> str:
    """Escape a plain-text value for safe insertion into a LaTeX cell."""
    s = str(value or "").strip()
    return "".join(_ESCAPE_MAP.get(ch, ch) for ch in s)




def _clean(value: Any) -> str:
    """Squash newlines in a plain-text value so it fills exactly one cell.

    Values are deliberately NOT truncated: the exported tables use wrapping
    paragraph columns and ``longtable`` rows that grow (and break across
    pages) with the content, mirroring the DOCX export behaviour.
    """
    return str(value or "").strip().replace("\r", " ").replace("\n", " ")


# ---------------------------------------------------------------------------
# Section fillers - each replaces the blank/marker inside the SAME skeleton
# ---------------------------------------------------------------------------
def _fill_cover(body: str, project_id: str, project_name: str, version: int,
                author: str, today: str) -> str:
    body = body.replace(r"\prdfield{PMO\_NO}", escape_latex(project_id[:8].upper()), 1)
    body = body.replace(r"\prdfield{PMO\_NAME}", escape_latex(project_name), 1)
    body = body.replace(r"\prdfield{VERSION}", escape_latex(f"V{version}.0"), 1)
    body = body.replace(r"\prdfield{STATUS}", "Draft", 1)
    body = body.replace(r"\prdfield{LAST\_UPDATE}", escape_latex(today), 1)
    body = body.replace(r"\prdfield{AUTHOR}", escape_latex(author or "Product Owner"), 1)
    return body


def _fill_stakeholders(body: str, actors: List[Any]) -> str:
    names = [str(a.get("name", a)) if isinstance(a, dict) else str(a)
             for a in (actors or [])]

    def _match(role: str) -> str:
        for n in names:
            if role.lower() in n.lower() or n.lower() in role.lower():
                return n
        return ""

    for role in (
        "Product Owner", "Technical Product Owner", "Solution Architecture",
        "System Analyst", "Engineering Manager", "Project Manager",
        "Quality Assurance Lead", "Performance QA Lead",
    ):
        name = _match(role)
        body = body.replace(f"{role} & \\\\", f"{role} & {escape_latex(name)} \\\\", 1)
    return body


def _fill_version_history(body: str, version: int, author: str, today: str,
                          version_summary: str) -> str:
    desc = escape_latex(version_summary or "Initial approved version")
    body = body.replace(
        "V1.0 & & & \\\\",
        f"V{version}.0 & {escape_latex(today)} & {escape_latex(author or 'Product Owner')} & {desc} \\\\",
        1,
    )
    return body


def _fill_reviews(body: str, actors: List[Any]) -> str:
    names = [str(a.get("name", a)) if isinstance(a, dict) else str(a)
             for a in (actors or [])]
    for role in ("Product Owner", "Head of Product Management"):
        name = next((n for n in names if role.lower() in n.lower()), "")
        body = body.replace(
            f"{role} & & & \\\\",
            f"{role} & {escape_latex(name)} & & \\\\",
            1,
        )
    return body


def _fill_business_overview(body: str, data: Dict[str, Any],
                            narrative: Optional[Dict[str, str]]) -> str:
    goals = [g.get("description", g) if isinstance(g, dict) else g
             for g in (data.get("business_goals") or [])]
    actors = data.get("actors") or []

    def _narr(key: str, fallback: str) -> str:
        if narrative and narrative.get(key):
            return r"\prdfield{" + escape_latex(_clean(narrative[key])) + "}"
        return fallback

    epic = _narr("exec_summary", r"\prdfield{TBD}")

    problems = [_clean(p) for p in (data.get("problem_statement") or [])
                if str(p or "").strip()] or ["TBD"]
    problem_cell = r"\prdfield{" + "".join(
        f"{i + 1}. {escape_latex(p)}\\\\{'[0.15cm]' if i == 0 else ''}"
        for i, p in enumerate(problems)
    ) + "}"

    def _num(items: List[str]) -> str:
        # No caps: the longtable rows wrap and grow with the content.
        cleaned = [escape_latex(_clean(i))
                   for i in items if str(i or "").strip()]
        if not cleaned:
            return r"\prdfield{TBD}"
        parts = []
        for idx, item in enumerate(cleaned):
            gap = "[0.15cm]" if idx == 0 else ""
            parts.append(f"{idx + 1}. {item}\\\\{gap}")
        return r"\prdfield{" + "".join(parts) + "}"

    target = [
        (a.get("name", a) if isinstance(a, dict) else a) for a in (actors or [])
    ]
    target = [n for n in target if str(n or "").strip()]
    target_cell = r"\prdfield{" + escape_latex(", ".join(str(n) for n in target)) + "}"
    if target_cell == r"\prdfield{":
        target_cell = r"\prdfield{TBD}"

    rows = [
        (
            r"^  Introduction",
            f"  Introduction \\&\\\\ Executive Summary & {epic} \\\\",
        ),
        (
            r"^  Problem Statement",
            f"  Problem Statement & {problem_cell} \\\\",
        ),
        (
            r"^  Business Objectives",
            f"  Business Objectives & {_num(goals)} \\\\",
        ),
        (
            r"^  Expected Benefit",
            f"  Expected Benefit & {_narr('expected_benefit', r'\prdfield{TBD}')} \\\\",
        ),
        (
            r"^  Success Metrics",
            f"  Success Metrics & {_narr('success_metrics', r'\prdfield{TBD}')} \\\\",
        ),
        (
            r"^  Target Audience",
            f"  Target Audience \\&\\\\ user Personas & {target_cell} \\\\",
        ),
    ]
    return _rewrite_rows(body, rows)


def _rewrite_rows(body: str, rows: List[Tuple[str, str]]) -> str:
    """Replace tabular rows whose leading label matches a regex.

    The Krungsri template rows are one physical line each; rewriting by line
    keeps the exact template row structure while making the fill resilient to
    incidental whitespace/escaping drift in the label text.
    """
    lines = body.splitlines()
    for prefix, new_line in rows:
        done = False
        for idx, ln in enumerate(lines):
            if re.search(prefix, ln):
                lines[idx] = new_line
                done = True
                break
        if not done:
            raise ValueError(f"Template row not found for fill pattern {prefix!r}")
    return "\n".join(lines)



def _fr_rows_for(stories: List[Dict[str, Any]]) -> str:
    """Build FR/AC rows that GROW with the project data.

    Every user story becomes one ``longtable`` row and nothing is truncated
    or dropped: the cells are plain text inside wrapping ``L{4cm}`` paragraph
    columns, so long titles / acceptance criteria wrap (and the table breaks
    across pages) instead of being stamped into fixed ``\\shortstack`` line
    boxes.  ``\\\\`` between the AC entries is an in-cell line break - the
    same construct the template itself uses for ``Introduction \\\\ Executive
    Summary`` label cells.
    """
    if not stories:
        return r"""    & & \shortstack{FR 1.1: The system\\
must\ldots} & \shortstack{AC 1.1:\\
AC 1.2:} \\"""
    rows = []
    for idx, story in enumerate(stories, start=1):
        code = story.get("ticket_code") or f"US-{idx:03d}"
        title = story.get("story_title") or story.get("i_want_to") or f"Story {idx}"
        fr_block = f"FR {idx}.1: {escape_latex(_clean(f'{code}: {title}'))}"
        acs = [escape_latex(_clean(a)) for a in (story.get("acceptance_criteria") or [])
               if str(a or "").strip()] or [r"\prdfield{TBD}"]
        ac_block = "\\\\".join(f"AC {idx}.{j}: {ac}" for j, ac in enumerate(acs, start=1))
        rows.append(f"    & & {fr_block} & {ac_block} \\\\")
    # Each row already ends with a complete ``\\`` terminator; rows are
    # separated by a plain newline.  Joining with ``'\<newline>'`` used to
    # emit ``\\\<newline>`` between rows - the stray odd backslash leaked
    # into the next row's first cell in the DOCX export.
    return "\n".join(rows)



def _fill_product_scope(body: str, data: Dict[str, Any]) -> str:
    epic = data.get("epic_name") or (
        data.get("requirements") or [{}]
    )[0].get("title", "") or ""
    body = body.replace(
        "{Epic Name:}",
        "{Epic Name: " + escape_latex(epic) + "}",
        1,
    )

    stories: List[Dict[str, Any]] = []
    for req in (data.get("requirements") or []):
        if isinstance(req, dict):
            stories.extend(req.get("user_stories") or [])
    stories.extend(data.get("user_stories") or [])

    # The template's label column is a \multirow spanning the epic row, the
    # column-header row and the FR rows; grow the span with the story count
    # so the merged label covers every generated row.  (\multirow{3}{*} is
    # unique in the template - the Scope Definition label uses \multirow{2}.)
    span = max(1, len(stories)) + 2
    body = re.sub(
        r"\\multirow\{3\}\{\*\}",
        lambda _m: "\\multirow{" + str(span) + "}{*}",
        body,
        count=1,
    )

    _ANCHOR_FR_ROW = (
        r"""    & & \shortstack{FR 1.1: The system\\"""
        + "\n"
        + r"""must\ldots} & \shortstack{AC 1.1:\\"""
        + "\n"
        + r"""AC 1.2:} \\"""
    )
    rows = _fr_rows_for(stories)
    if _ANCHOR_FR_ROW in body:
        body = body.replace(_ANCHOR_FR_ROW, rows, 1)

    scope_in = [escape_latex(s) for s in (data.get("scope_in") or [])
                if str(s or "").strip()]
    scope_out = [escape_latex(s) for s in (data.get("scope_out") or [])
                 if str(s or "").strip()]

    BS = chr(92)  # backslash - plain concatenation avoids f-string brace bugs
    NL = "\n"

    def _nums(items: List[str], *, last_gap: bool) -> str:
        """Numbered lines mirroring the template's Scope cell:
        entries separated by '\\\\'; the LAST entry carries '[0.15cm]' only
        when ``last_gap`` and never a trailing '\\\\' (a row break directly
        before '}}}' makes \\shortstack die with 'Misplaced \\cr')."""
        if not items:
            return f"1. {BS}prdfield{{TBD}}"
        lines = []
        n = len(items)
        for i, item in enumerate(items):
            if i == n - 1:
                if last_gap:
                    lines.append(f"{i + 1}. {item}{BS}{BS}[0.15cm]")
                else:
                    lines.append(f"{i + 1}. {item}")
            else:
                lines.append(f"{i + 1}. {item}{BS}{BS}")
        return NL.join(lines)

    in_lines = _nums(scope_in, last_gap=True)
    out_lines = _nums(scope_out, last_gap=False)

    inner = (
        BS + "prdlbl{Scope In}" + BS + BS + NL
        + in_lines + NL
        + BS + "prdlbl{Scope out}" + BS + BS + NL
        + out_lines + NL
        + "}}"
    )
    scope_block = (
        BS + "multicolumn{3}{c}{" + BS + "parbox{11.5cm}{%" + NL
        + "        " + inner + " " + BS + BS
    )

    _SCOPE_ROW_RE = re.compile(
        r"\\multicolumn\{3\}\{c\}\{\\parbox\{11\.5cm\}\{%\s*\\shortstack\{.*?\}\}\} \\\\",
        re.S,
    )
    if _SCOPE_ROW_RE.search(body):
        body = _SCOPE_ROW_RE.sub(lambda _m: scope_block, body, count=1)
    return body


def _fill_tech_appendix(body: str, narrative: Optional[Dict[str, str]]) -> str:
    def _cell(key: str, fallback: str) -> str:
        if narrative and narrative.get(key):
            return r"\prdfield{" + escape_latex(_clean(narrative[key])) + "}"
        return fallback

    rows = [
        (
            r"^  Non-Functional",
            f"  Non-Functional\\\\ Requirements & {_cell('non_functional', r'\prdfield{TBD}')} \\\\",
        ),
        (
            r"^  Expected\\",
            f"  Expected\\\\ TPS/Customer\\\\ volume & {_cell('tps_volume', r'\prdfield{TBD}')} \\\\",
        ),
        (
            r"^  Growth\\",
            f"  Growth\\\\ prediction\\\\ Y0Y\\% & {_cell('growth', r'\prdfield{TBD}')} \\\\",
        ),
        (
            r"^  Launch",
            f"  Launch \\&\\\\ Rollout Plan & {_cell('launch_plan', r'\prdfield{TBD}')} \\\\",
        ),
        (
            r"^  Open",
            f"  Open\\\\ Questions \\&\\\\ Risks & {_cell('open_questions', r'\prdfield{TBD}')} \\\\",
        ),
        (
            r"^  Assumptions",
            f"  Assumptions & {_cell('assumptions', r'\prdfield{TBD}')} \\\\",
        ),
    ]
    body = _rewrite_rows(body, rows)
    return _fill_glossary_rows(body, narrative)


#: The appendix template carries a nested Term/Definition sub-grid (two TBD
#: placeholder rows under the Glossary header). The regex matches both
#: placeholder rows so they can be replaced by real glossary entries.
_GLOSSARY_GRID_RE = re.compile(
    r"(?:\n\s*\\cline\{2-3\}\n\s*&\s*\\prdfield\{TBD\}\s*&\s*\\prdfield\{TBD\}\s*\\\\)+",
    re.S,
)


def _fill_glossary_rows(body: str, narrative: Optional[Dict[str, str]]) -> str:
    entries = (narrative or {}).get("glossary")
    if not entries:
        return body
    rows = []
    for term, definition in entries:
        rows.append(
            f"  \\cline{{2-3}}\n"
            f"  & {escape_latex(_clean(term))} & {escape_latex(_clean(definition))} \\\\"
        )
    block = "\n".join(rows)
    updated, count = _GLOSSARY_GRID_RE.subn(lambda _m: block, body, count=1)
    if count:
        return updated
    # No placeholder grid found: inject the block right after the glossary
    # header row so the terms still render as a nested Term/Definition table.
    glossary_line = re.search(r"^  Glossary[^\n]*\\\\$", body, re.M)
    if glossary_line:
        idx = glossary_line.end()
        return body[:idx] + "\n" + block + body[idx:]
    return body



def fill_template_body(
    *,
    project_id: str = "",
    project_name: str = "",
    version: int = 1,
    author: str = "Product Owner",
    today: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    narrative: Optional[Dict[str, str]] = None,
    version_summary: str = "",
) -> str:
    """Return the official Krungsri template BODY with its blanks filled from
    the project dataset. ``data`` maps: ``business_goals``, ``actors``,
    ``requirements`` (with nested ``user_stories`` + ``acceptance_criteria``)
    or flat ``user_stories`` / ``acceptance_criteria``, ``epic_name``,
    ``scope_in``, ``scope_out``, ``problem_statement``."""
    data = data or {}
    today = today or _date.today().isoformat()

    body = load_prd_latex_template_body()
    body = _fill_cover(body, project_id, project_name, version, author, today)
    body = _fill_stakeholders(body, data.get("actors") or [])
    body = _fill_version_history(body, version, author, today, version_summary)
    body = _fill_reviews(body, data.get("actors") or [])
    body = _fill_business_overview(body, data, narrative)
    body = _fill_product_scope(body, data)
    body = _fill_tech_appendix(body, narrative)
    return body
    return body