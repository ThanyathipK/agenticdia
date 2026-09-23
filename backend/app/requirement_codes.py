"""
Canonical ``REQ-###`` requirement-code helpers — the SINGLE source of truth for
requirement numbering.

Nothing in the codebase should hardcode a literal code such as ``"REQ-001"``:

* A hardcoded code on a fresh board is what let a brand-new project start at
  ``REQ-002`` (a seeded/default requirement claimed ``REQ-001`` before the first
  requirement the user actually gathered) and it silently pinned numbering when
  the sequence legitimately needed to advance.
* The prefix, the number a fresh board starts at, the sentinel used for
  not-yet-numbered rows and the ``used codes -> next code`` rule all live here so
  every caller (agents, routes, document import, repositories) derives the same
  answer.
"""
import re
from typing import Any, Iterable

# ``REQ-001``: prefix + zero-padded 3-digit number.
REQUIREMENT_CODE_PREFIX = "REQ"
# Number of the FIRST requirement of any project — a fresh board always starts
# its sequence here instead of at an arbitrary hardcoded code.
FIRST_REQUIREMENT_NUMBER = 1

# A requirement code (``REQ-1`` / ``req_001`` / ``REQ-001``) — the canonical
# form is always rendered as ``REQ-NNN``.
_REQUIREMENT_CODE_RE = re.compile(r"^(?:REQ[-_ ]?)(\d+)$", re.IGNORECASE)


def format_requirement_code(number: int) -> str:
    """Render a requirement number as its canonical ``REQ-NNN`` code."""
    return f"{REQUIREMENT_CODE_PREFIX}-{number:03d}"


# The code every fresh board starts at (``REQ-001``).
FIRST_REQUIREMENT_CODE = format_requirement_code(FIRST_REQUIREMENT_NUMBER)
# Sentinel code for a requirement row that has no sequence number yet (legacy /
# anonymous rows created to satisfy a user-story or audit foreign key).
UNASSIGNED_REQUIREMENT_CODE = format_requirement_code(FIRST_REQUIREMENT_NUMBER - 1)


def normalize_requirement_code(code: Any) -> str:
    """Canonicalize an LLM/DB requirement code to ``REQ-NNN`` (``''`` if invalid)."""
    match = _REQUIREMENT_CODE_RE.match(str(code or "").strip())
    return format_requirement_code(int(match.group(1))) if match else ""


def default_requirement_code(index: int = 0) -> str:
    """Deterministic code for the requirement at 0-based ``index``.

    Index 0 is always the first code of the project (``REQ-001``), so callers
    never hardcode the first code themselves.
    """
    return format_requirement_code(FIRST_REQUIREMENT_NUMBER + index)


def next_requirement_code(used_codes: Iterable[Any]) -> str:
    """Return the code immediately after the highest already-used code.

    An empty/None sequence (a fresh board) yields the FIRST requirement code, so
    a brand-new project always starts at ``REQ-001``.
    """
    max_num = FIRST_REQUIREMENT_NUMBER - 1
    for code in used_codes or []:
        match = _REQUIREMENT_CODE_RE.match(str(code or "").strip())
        if match:
            max_num = max(max_num, int(match.group(1)))
    return format_requirement_code(max_num + 1)
