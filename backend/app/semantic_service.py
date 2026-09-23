"""Semantic change detection + the workflow/intent/matcher classification agents.

The semantic-change feature compares the Current Project Context (persisted user
stories) with a new user message and classifies every requested change
(``NEW_REQUIREMENT``, ``MODIFY_REQUIREMENT``, ...) into a writer action
(``INSERT`` / ``UPDATE`` / ``ARCHIVE`` / ``NO_CHANGE``).

Because that classification is produced by a local LLM, the raw answer is
**never** trusted verbatim: :func:`detect_semantic_changes` pipes it through the
deterministic guardrails in :func:`normalize_semantic_changes`, which

- canonicalises the classification + action vocabulary (aliases such as ``ADD``
  / ``MODIFY`` / ``REMOVE`` and the prompt-only ``MERGE`` action are translated
  onto the four actions the persistence layer actually understands),
- clamps ``confidence`` into ``[0.0, 1.0]``,
- resolves every ``target_requirement_id`` against the real backlog (exact
  ticket code -> normalized title -> fuzzy title) and refuses to act on a
  hallucinated target,
- de-duplicates recommendations and resolves conflicting actions over one target
  with a deterministic priority.

An ambiguous or malformed model answer therefore degrades into a low-confidence
recommendation (which the Gatherer turns into a user-visible clarification
question) instead of silently mutating — or silently skipping — the wrong
requirement.
"""
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field, field_validator

from app.llm_factory import llm
from app.schemas import RequirementIntentDetectionResult, WorkflowRoutingResult, RequirementMatcherResult
from app.prompt_loader import load_prompt
from app.llm_utils import invoke_llm_structured
from app.merge_service import (
    format_story_context_lines,
    normalize_ticket_code,
    normalize_title,
    titles_match,
)

# ==========================================
# SEMANTIC CHANGE VOCABULARY (single source of truth)
# ==========================================
# What the model is asked to reason with (see prompts/semantic.md).
SEMANTIC_CHANGE_TYPES: Tuple[str, ...] = (
    "NEW_REQUIREMENT",
    "MODIFY_REQUIREMENT",
    "REMOVE_REQUIREMENT",
    "RENAME_REQUIREMENT",
    "NO_MEANINGFUL_CHANGE",
    "EXPAND_REQUIREMENT",
    "SPLIT_REQUIREMENT",
    "MERGE_REQUIREMENTS",
)

# What the WRITERS understand. ``merge_service.merge_user_stories_with_report``
# and ``RequirementStateRepository`` only act on these four actions; any other
# recommendation is silently ignored by both, which used to turn a detected
# change into a no-op.
SEMANTIC_ACTIONS: Tuple[str, ...] = ("INSERT", "UPDATE", "ARCHIVE", "NO_CHANGE")

# Canonical action per classification — must stay in sync with prompts/semantic.md.
DEFAULT_ACTION_BY_CHANGE_TYPE: Dict[str, str] = {
    "NEW_REQUIREMENT": "INSERT",
    "MODIFY_REQUIREMENT": "UPDATE",
    "REMOVE_REQUIREMENT": "ARCHIVE",
    "RENAME_REQUIREMENT": "UPDATE",
    "NO_MEANINGFUL_CHANGE": "NO_CHANGE",
    "EXPAND_REQUIREMENT": "UPDATE",
    "SPLIT_REQUIREMENT": "UPDATE",
    # A consolidation still has to be rewritten onto its surviving story, so the
    # writer action is UPDATE ("MERGE" is not a supported writer action).
    "MERGE_REQUIREMENTS": "UPDATE",
}

# Classifications that are meaningless without a concrete target story.
TARGET_REQUIRED_CHANGE_TYPES: Tuple[str, ...] = (
    "MODIFY_REQUIREMENT",
    "REMOVE_REQUIREMENT",
    "RENAME_REQUIREMENT",
    "EXPAND_REQUIREMENT",
    "SPLIT_REQUIREMENT",
    "MERGE_REQUIREMENTS",
)

# Confidence ceilings that force the Gatherer's clarification branch.
SEMANTIC_LOW_CONFIDENCE_THRESHOLD = 0.70   # gatherer halts below this
UNRESOLVED_TARGET_CONFIDENCE = 0.50        # target could not be resolved
CONFLICTING_ACTIONS_CONFIDENCE = 0.60      # entries disagree over one target
DEFAULT_NO_CHANGE_CONFIDENCE = 0.90        # explicit "nothing changed" signal

# Placeholder ticket code that must never be treated as a resolvable target.
_PLACEHOLDER_TICKET_CODE = "US-000"

# Values that mean "no target" rather than a ticket code.
_NULL_TARGET_TOKENS = frozenset(
    {"", "null", "none", "n/a", "na", "nil", "unknown", "unset", "-", "--", "tbd"}
)

# Deterministic precedence when two recommendations fight over one target: an
# explicit removal outranks a rewrite, which outranks a fresh insert.
_ACTION_PRIORITY: Dict[str, int] = {
    "ARCHIVE": 3,
    "UPDATE": 2,
    "INSERT": 1,
    "NO_CHANGE": 0,
}

# Tolerated synonyms the model may emit instead of the canonical vocabulary.
_CHANGE_TYPE_ALIASES: Dict[str, str] = {
    "NEW": "NEW_REQUIREMENT",
    "ADD": "NEW_REQUIREMENT",
    "ADD_REQUIREMENT": "NEW_REQUIREMENT",
    "CREATE_REQUIREMENT": "NEW_REQUIREMENT",
    "MODIFY": "MODIFY_REQUIREMENT",
    "UPDATE": "MODIFY_REQUIREMENT",
    "UPDATE_REQUIREMENT": "MODIFY_REQUIREMENT",
    "CHANGE_REQUIREMENT": "MODIFY_REQUIREMENT",
    "REMOVE": "REMOVE_REQUIREMENT",
    "DELETE": "REMOVE_REQUIREMENT",
    "DELETE_REQUIREMENT": "REMOVE_REQUIREMENT",
    "DROP_REQUIREMENT": "REMOVE_REQUIREMENT",
    "ARCHIVE_REQUIREMENT": "REMOVE_REQUIREMENT",
    "RENAME": "RENAME_REQUIREMENT",
    "REWORD_REQUIREMENT": "RENAME_REQUIREMENT",
    "NO_CHANGE": "NO_MEANINGFUL_CHANGE",
    "NO CHANGE": "NO_MEANINGFUL_CHANGE",
    "UNCHANGED": "NO_MEANINGFUL_CHANGE",
    "NONE": "NO_MEANINGFUL_CHANGE",
    "EXPAND": "EXPAND_REQUIREMENT",
    "EXTEND_REQUIREMENT": "EXPAND_REQUIREMENT",
    "ENHANCE_REQUIREMENT": "EXPAND_REQUIREMENT",
    "SPLIT": "SPLIT_REQUIREMENT",
    "SPLIT_REQUIREMENT_INTO_STORIES": "SPLIT_REQUIREMENT",
    "MERGE": "MERGE_REQUIREMENTS",
    "MERGE_REQUIREMENT": "MERGE_REQUIREMENTS",
    "CONSOLIDATE_REQUIREMENTS": "MERGE_REQUIREMENTS",
}

_ACTION_ALIASES: Dict[str, str] = {
    "ADD": "INSERT",
    "CREATE": "INSERT",
    "NEW": "INSERT",
    "INSERT_NEW": "INSERT",
    "MODIFY": "UPDATE",
    "MODIFIED": "UPDATE",
    "EDIT": "UPDATE",
    "REVISE": "UPDATE",
    "CHANGE": "UPDATE",
    "REMOVE": "ARCHIVE",
    "DELETE": "ARCHIVE",
    "DELETED": "ARCHIVE",
    "DROP": "ARCHIVE",
    "RETIRE": "ARCHIVE",
    "NONE": "NO_CHANGE",
    "NOCHANGE": "NO_CHANGE",
    "UNCHANGED": "NO_CHANGE",
    "SKIP": "NO_CHANGE",
    "KEEP": "NO_CHANGE",
    # ``MERGE`` is a classification, not a writer action: the surviving story is
    # rewritten (UPDATE) while absorbed stories get their own ARCHIVE entry.
    "MERGE": "UPDATE",
    "CONSOLIDATE": "UPDATE",
}



logger = logging.getLogger("app.semantic_service")

class SemanticChange(BaseModel):
    change_type: str = Field(..., description="Classification: " + ", ".join(SEMANTIC_CHANGE_TYPES))
    target_requirement_id: Optional[str] = Field(None, description="The ticket_code (e.g. US-001) of the affected user story, if any. Return null if it does not apply.")
    confidence: float = Field(..., description="Confidence score from 0.0 to 1.0")
    reason: str = Field(..., description="Detailed reasoning explaining why this change is classified this way.")
    recommended_action: str = Field(..., description="Action recommendation: " + ", ".join(SEMANTIC_ACTIONS))

    # The validators COERCE instead of raising: a sloppy model reply should be
    # repaired at the parse boundary, not turned into a failed workflow turn.
    @field_validator("change_type", mode="before")
    @classmethod
    def _validate_change_type(cls, value: Any) -> str:
        return normalize_change_type(value) or _clean_str(value).upper()

    @field_validator("recommended_action", mode="before")
    @classmethod
    def _validate_action(cls, value: Any, info) -> str:
        # ``info.data`` already holds the validated ``change_type`` (declared
        # first), so an omitted/unknown action can still be derived correctly.
        change_type = (getattr(info, "data", None) or {}).get("change_type", "")
        return normalize_recommended_action(value, change_type)

    @field_validator("target_requirement_id", mode="before")
    @classmethod
    def _validate_target(cls, value: Any) -> Optional[str]:
        return normalize_target_reference(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def _validate_confidence(cls, value: Any) -> float:
        return coerce_confidence(value, default=0.5)

    @field_validator("reason", mode="before")
    @classmethod
    def _validate_reason(cls, value: Any) -> str:
        return _clean_str(value)


class SemanticChangeDetectionResult(BaseModel):
    changes: List[SemanticChange] = Field(
        ...,
        description=(
            "List of all detected changes: ONE entry per affected user story, plus a "
            "single NO_MEANINGFUL_CHANGE entry when the message changes nothing."
        ),
    )


# ==========================================
# NORMALIZATION / RESOLUTION GUARDRAILS
# ==========================================
def _clean_str(value: Any) -> str:
    """Stringify and strip a possibly-``None`` LLM value."""
    return str(value).strip() if value is not None else ""


def normalize_change_type(value: Any) -> str:
    """Map a raw classification onto the canonical vocabulary (``""`` if unknown)."""
    text = " ".join(_clean_str(value).upper().replace("-", "_").split())
    if text in SEMANTIC_CHANGE_TYPES:
        return text
    return _CHANGE_TYPE_ALIASES.get(text, "")


def normalize_recommended_action(value: Any, change_type: str = "") -> str:
    """Canonical writer action, derived from the classification when needed.

    Handles the three failure modes seen in practice: an alias instead of the
    canonical action (``ADD`` -> ``INSERT``), the classification echoed into the
    action field (``MERGE_REQUIREMENTS`` -> ``UPDATE``), and a missing/garbage
    action (derived from ``change_type``, finally ``NO_CHANGE``). The return value
    is therefore always one of :data:`SEMANTIC_ACTIONS`.
    """
    text = " ".join(_clean_str(value).upper().replace("-", "_").split())
    action = text if text in SEMANTIC_ACTIONS else _ACTION_ALIASES.get(text, "")
    if not action:
        # The model sometimes echoes the classification into the action field.
        action = DEFAULT_ACTION_BY_CHANGE_TYPE.get(normalize_change_type(text), "")
    if not action:
        action = DEFAULT_ACTION_BY_CHANGE_TYPE.get(normalize_change_type(change_type) or change_type, "")
    if not action:
        logger.warning(
            "Unknown semantic action '%s' (change_type='%s'); defaulting to NO_CHANGE.", value, change_type
        )
        return "NO_CHANGE"
    return action


def coerce_confidence(value: Any, default: float = 0.5) -> float:
    """Clamp a raw confidence into ``[0.0, 1.0]`` (accepts numbers and ``"85%"``)."""
    text = _clean_str(value)
    try:
        parsed = float(text.rstrip("%")) if text else float(default)
    except (TypeError, ValueError):
        parsed = float(default)
    if text.endswith("%"):
        parsed = parsed / 100.0
    if parsed != parsed:  # NaN
        parsed = float(default)
    return min(1.0, max(0.0, parsed))


def normalize_target_reference(value: Any) -> Optional[str]:
    """Normalize an LLM target reference, or ``None`` when it means "no target"."""
    text = _clean_str(value)
    if text.lower() in _NULL_TARGET_TOKENS:
        return None
    code = normalize_ticket_code(text)
    if code.upper().startswith("US-"):
        return code.upper()
    # Not ticket-code shaped: keep it verbatim so it can still be matched as a
    # story title against the backlog.
    return text


def build_story_target_index(stories: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, str]:
    """Map every reasonable target reference to its canonical ticket code."""
    index: Dict[str, str] = {}
    for story in stories or []:
        if not isinstance(story, dict):
            continue
        code = normalize_ticket_code(story.get("ticket_code"))
        if not code or code == _PLACEHOLDER_TICKET_CODE:
            continue
        index[code] = code
        title = normalize_title(story.get("story_title"))
        if title:
            index.setdefault(title, code)
    return index


def resolve_target_story(
    target_reference: Any,
    stories: Optional[Iterable[Dict[str, Any]]] = None,
    index: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Resolve a reference to a canonical ticket code, or ``None`` when unknown.

    Mirrors the merge service's progressive identity resolution: exact ticket
    code -> normalized title -> fuzzy title (``titles_match``). A target that
    cannot be resolved is a hallucination and must never drive a mutation.
    """
    text = normalize_target_reference(target_reference) if isinstance(target_reference, str) else target_reference
    if not text:
        return None

    story_list = [s for s in (stories or []) if isinstance(s, dict)]
    lookup = index if index is not None else build_story_target_index(story_list)

    for key in (str(text), normalize_ticket_code(text), normalize_title(text)):
        if key and lookup.get(key):
            return lookup[key]

    for story in story_list:
        code = normalize_ticket_code(story.get("ticket_code"))
        if not code or code == _PLACEHOLDER_TICKET_CODE:
            continue
        if titles_match(text, story.get("story_title")):
            return code
    return None


def _coerce_change_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one raw change dict onto the canonical recommendation shape.

    Used on the raw-JSON parse path (``json.loads`` bypasses the Pydantic
    validators) as well as on already-validated payloads.
    """
    raw_change_type = _clean_str(raw.get("change_type"))
    change_type = normalize_change_type(raw_change_type) or raw_change_type.upper().replace("-", "_")
    return {
        "change_type": change_type,
        "target_requirement_id": normalize_target_reference(raw.get("target_requirement_id")),
        "confidence": coerce_confidence(raw.get("confidence"), default=0.5),
        "reason": _clean_str(raw.get("reason")),
        "recommended_action": normalize_recommended_action(raw.get("recommended_action"), change_type),
    }


def build_no_change_recommendation(reason: str, confidence: float = DEFAULT_NO_CHANGE_CONFIDENCE) -> Dict[str, Any]:
    """The explicit "nothing meaningful changed" recommendation."""
    return {
        "change_type": "NO_MEANINGFUL_CHANGE",
        "target_requirement_id": None,
        "confidence": coerce_confidence(confidence),
        "reason": reason,
        "recommended_action": "NO_CHANGE",
    }

def normalize_semantic_changes(
    raw_changes: Optional[Iterable[Any]],
    current_stories: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Deterministically repair/validate the LLM's detected semantic changes.

    Guarantees (each one covered by ``tests/test_semantic_service.py``):

    1. every returned ``change_type`` is canonical and every
       ``recommended_action`` is one the writers actually act on;
    2. ``confidence`` is clamped into ``[0.0, 1.0]`` and lowered whenever a
       recommendation could not be fully verified;
    3. an unresolved (or missing) target on a target-requiring classification is
       downgraded to ``NO_CHANGE`` below
       :data:`SEMANTIC_LOW_CONFIDENCE_THRESHOLD`, so the Gatherer asks the user
       instead of guessing;
    4. ``NEW_REQUIREMENT`` never carries a target story;
    5. there is at most one recommendation per target, with conflicting actions
       resolved by :data:`_ACTION_PRIORITY` and forced into the clarification
       band;
    6. the list always contains at least one entry (an empty model answer becomes
       an explicit ``NO_MEANINGFUL_CHANGE``).
    """
    stories = [s for s in (current_stories or []) if isinstance(s, dict)]
    index = build_story_target_index(stories)
    cleaned: List[Dict[str, Any]] = []

    for raw in raw_changes or []:
        if not isinstance(raw, dict):
            logger.warning("Ignoring malformed semantic change entry (not an object): %r", raw)
            continue

        entry = _coerce_change_entry(raw)
        change_type = entry["change_type"]
        if change_type not in SEMANTIC_CHANGE_TYPES:
            logger.warning("Ignoring semantic change with unknown classification: %r", raw.get("change_type"))
            continue

        target = entry["target_requirement_id"]
        if change_type == "NEW_REQUIREMENT":
            # A brand-new requirement cannot be attached to an existing story.
            if target is not None:
                logger.info(
                    "Dropping target '%s' from NEW_REQUIREMENT (a new requirement has no existing story).", target
                )
            entry["target_requirement_id"] = None
            entry["recommended_action"] = "INSERT"
        elif target is not None:
            resolved = resolve_target_story(target, stories, index)
            if resolved:
                entry["target_requirement_id"] = resolved
            else:
                entry = _downgrade_unverifiable_change(
                    entry, f"Target story '{target}' does not exist in the current backlog."
                )
        elif change_type in TARGET_REQUIRED_CHANGE_TYPES:
            entry = _downgrade_unverifiable_change(
                entry, f"'{change_type}' requires an existing ticket code but no target was provided."
            )

        cleaned.append(entry)

    deduped = _dedupe_changes(cleaned)
    meaningful = [c for c in deduped if c["change_type"] != "NO_MEANINGFUL_CHANGE"]
    if meaningful:
        # An explicit "nothing changed" alongside real changes is just noise.
        return meaningful
    if deduped:
        return deduped
    logger.warning("Semantic change detection produced no usable entries; emitting an explicit NO_CHANGE.")
    return [build_no_change_recommendation("The model reported no semantic change for this message.")]


def _downgrade_unverifiable_change(entry: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Turn an unverifiable recommendation into a low-confidence ``NO_CHANGE``.

    Keeping the (now un-actionable) recommendation would let the Gatherer invent
    a target; dropping it silently would hide the ambiguity. A ``NO_CHANGE``
    below the clarification threshold does neither: nothing is mutated and the
    user is asked which story was meant.
    """
    downgraded = dict(entry)
    downgraded["change_type"] = "NO_MEANINGFUL_CHANGE"
    downgraded["recommended_action"] = "NO_CHANGE"
    downgraded["confidence"] = min(entry["confidence"], UNRESOLVED_TARGET_CONFIDENCE)
    note = f"{reason} No change was applied; please confirm the ticket code."
    downgraded["reason"] = f"{entry['reason']} {note}".strip()
    logger.warning("Semantic change downgraded to NO_CHANGE: %s", note)
    return downgraded


def _resolve_action_conflict(first: Dict[str, Any], second: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Pick the winning recommendation out of two conflicting ones for one target."""
    first_rank = _ACTION_PRIORITY.get(first["recommended_action"], -1)
    second_rank = _ACTION_PRIORITY.get(second["recommended_action"], -1)
    if first_rank == second_rank:
        # Same priority (e.g. two classifications that both map to UPDATE)
        # -> the more confident one wins.
        return (first, second) if first["confidence"] >= second["confidence"] else (second, first)
    return (first, second) if first_rank > second_rank else (second, first)


def _dedupe_changes(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One recommendation per target, with deterministic conflict resolution."""
    by_key: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for entry in changes:
        key = entry.get("target_requirement_id") or "__project__"
        if key not in by_key:
            by_key[key] = entry
            order.append(key)
            continue

        kept = by_key[key]
        if kept["recommended_action"] == entry["recommended_action"]:
            # Same action twice: keep the more confident wording.
            if entry["confidence"] > kept["confidence"]:
                by_key[key] = entry
            continue

        winner, loser = _resolve_action_conflict(kept, entry)
        conflict_note = (
            f"Conflicting recommendations for {key}: "
            f"'{loser['change_type']}' ({loser['recommended_action']}) vs "
            f"'{winner['change_type']}' ({winner['recommended_action']}); "
            "the more conservative action was kept — please confirm the intent."
        )
        logger.warning(conflict_note)
        winner = dict(winner)
        winner["confidence"] = min(winner["confidence"], CONFLICTING_ACTIONS_CONFIDENCE)
        winner["reason"] = f"{winner['reason']} {conflict_note}".strip()
        by_key[key] = winner

    return [by_key[key] for key in order]

async def detect_semantic_changes(
    raw_input: str,
    current_stories: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Compare existing user stories with ``raw_input`` and classify every change.

    Returns normalized recommendation dicts (see
    :func:`normalize_semantic_changes`) whose ``recommended_action`` is always one
    of ``INSERT`` / ``UPDATE`` / ``ARCHIVE`` / ``NO_CHANGE`` and whose
    ``target_requirement_id`` is always a real ticket code from
    ``current_stories`` (or ``None`` for a brand-new requirement).
    """
    stories = [s for s in (current_stories or []) if isinstance(s, dict)]
    logger.info(
        "Running semantic change detection on new message: '%s' against %d existing user story(ies)",
        str(raw_input)[:100],
        len(stories),
    )

    if not str(raw_input or "").strip():
        # Nothing to compare: skip the LLM round-trip but still return an
        # explicit signal instead of an ambiguous empty list.
        return [build_no_change_recommendation("The message is empty; there is no semantic change to detect.")]

    # Format current stories into a clean visual summary for the prompt
    # (shared with the Gatherer/intent prompts via merge_service).
    context_lines = format_story_context_lines(stories)
    current_context = "\n".join(context_lines) if context_lines else "No existing user stories in this project."

    prompt_template = PromptTemplate(
        template=load_prompt("semantic"),
        input_variables=["current_context", "new_message", "format_instructions"]
    )

    pydantic_parser = JsonOutputParser(pydantic_object=SemanticChangeDetectionResult)
    format_instructions = pydantic_parser.get_format_instructions()

    def _is_valid_changes(result: Dict[str, Any]) -> bool:
        """Reject a payload without a usable ``changes`` list so the raw-JSON retry runs."""
        changes = result.get("changes")
        return isinstance(changes, list) and all(isinstance(c, dict) for c in changes)

    # Prefer .with_structured_output(), falling back to raw JSON parse
    try:
        result = await invoke_llm_structured(
            llm,
            prompt_template,
            SemanticChangeDetectionResult,
            variables={
                "current_context": current_context,
                "new_message": raw_input,
                "format_instructions": "Output ONLY raw JSON matching the schema.",
            },
            description="semantic change detection",
            format_instructions=format_instructions,
            validate=_is_valid_changes,
        )
        logger.info("Successfully obtained structured output for semantic changes.")
    except Exception as e2:
        logger.error(f"Semantic change detection parsing failed completely: {str(e2)}", exc_info=True)
        # FAIL LOUDLY instead of silently defaulting to a NEW_REQUIREMENT "INSERT"
        # recommendation. A parse/LLM failure would otherwise be masked as a
        # legitimate new requirement and drive a wrong workflow decision, so we
        # propagate the error to the caller (which surfaces it as HTTP 500).
        raise RuntimeError(f"Semantic change detection failed: {str(e2)}") from e2

    changes = normalize_semantic_changes(result.get("changes") or [], stories)
    logger.info(
        "Detected %d semantic change(s): %s",
        len(changes),
        [
            {
                "change_type": c["change_type"],
                "target": c["target_requirement_id"],
                "action": c["recommended_action"],
                "confidence": round(c["confidence"], 2),
            }
            for c in changes
        ],
    )
    return changes






async def detect_requirement_intent(raw_input: str, current_stories: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Uses LLM for semantic intent classification on user message.
    Returns a dict with: intent, confidence, reason.
    Supports intents: GENERAL_CHAT, CREATE_REQUIREMENT, UPDATE_REQUIREMENT, DELETE_REQUIREMENT, CLARIFY_REQUIREMENT.
    """
    VALID_INTENTS = ["GENERAL_CHAT", "CREATE_REQUIREMENT", "UPDATE_REQUIREMENT", "DELETE_REQUIREMENT", "CLARIFY_REQUIREMENT"]
    
    if not raw_input or not str(raw_input).strip():
        return {
            "intent": "GENERAL_CHAT",
            "confidence": 1.0,
            "reason": "Empty input defaulted to GENERAL_CHAT."
        }
        
    logger.info(f"Detecting requirement intent for message: '{raw_input[:100]}'")
    
    context_lines = format_story_context_lines(current_stories)
    current_context = "\n".join(context_lines) if context_lines else "No existing user stories in this project."

    prompt_template = PromptTemplate(
        template=load_prompt("intent"),
        input_variables=["current_context", "user_message", "format_instructions"]
    )
    
    pydantic_parser = JsonOutputParser(pydantic_object=RequirementIntentDetectionResult)
    format_instructions = pydantic_parser.get_format_instructions()
    
    # Prefer .with_structured_output(), falling back to raw JSON parse
    def _is_valid_intent(result: Dict[str, Any]) -> bool:
        return str(result.get("intent", "")).strip().upper() in VALID_INTENTS

    try:
        result = await invoke_llm_structured(
            llm,
            prompt_template,
            RequirementIntentDetectionResult,
            variables={
                "current_context": current_context,
                "user_message": raw_input,
                "format_instructions": "Output ONLY raw JSON matching the schema.",
            },
            description="intent detection",
            format_instructions=format_instructions,
            validate=_is_valid_intent,
        )
        intent = str(result.get("intent", "")).strip().upper()
        confidence = float(result.get("confidence", 0.90))
        reason = str(result.get("reason") or result.get("reasoning") or "")
        logger.info(f"Successfully detected requirement intent via LLM: {intent} (confidence: {confidence})")
        return {
            "intent": intent,
            "confidence": confidence,
            "reason": reason
        }
    except Exception as e2:
        logger.error(f"Intent detection parsing failed completely: {str(e2)}")

    # Fallback: heuristic classification
    lower_inp = raw_input.lower().strip()
    if lower_inp in ["hello", "hi", "thank you", "thanks", "good morning", "good afternoon", "good evening", "ok", "okay", "got it", "awesome", "great"]:
        return {
            "intent": "GENERAL_CHAT",
            "confidence": 0.95,
            "reason": "The user is providing a conversational greeting or pleasantry."
        }
    elif lower_inp.startswith("what") or lower_inp.startswith("explain") or lower_inp.startswith("how") or lower_inp.startswith("can you") or lower_inp.endswith("?"):
        return {
            "intent": "GENERAL_CHAT",
            "confidence": 0.90,
            "reason": "The user is asking a question or seeking an explanation."
        }
    elif any(kw in lower_inp for kw in ["run audit", "run auditor", "audit", "validate", "clarify", "review requirement"]):
        return {
            "intent": "CLARIFY_REQUIREMENT",
            "confidence": 0.85,
            "reason": "The user is requesting validation, audit, or clarification of requirements."
        }
    elif any(kw in lower_inp for kw in ["remove ", "delete ", "cancel ", "drop ", "no longer need", "discard ", "retire ", "archive "]):
        return {
            "intent": "DELETE_REQUIREMENT",
            "confidence": 0.85,
            "reason": "The user is requesting to remove or delete an existing requirement."
        }
    elif any(kw in lower_inp for kw in ["update ", "change ", "modify ", "adjust ", "revise ", "edit "]):
        return {
            "intent": "UPDATE_REQUIREMENT",
            "confidence": 0.85,
            "reason": "The user is requesting to modify or update an existing requirement."
        }
    elif any(kw in lower_inp for kw in ["add ", "create ", "new ", "implement ", "introduce "]):
        return {
            "intent": "CREATE_REQUIREMENT",
            "confidence": 0.85,
            "reason": "The user is requesting to add a new requirement or feature."
        }
    else:
        return {
            "intent": "GENERAL_CHAT",
            "confidence": 0.80,
            "reason": "Fallback: could not determine intent from input."
        }


async def generate_general_chat_response(
    raw_input: str,
    project_context: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Generates a conversational response for GENERAL_CHAT intents.
    Uses the same LLM client (no new agent or model).
    Provides full project context to the LLM for informed answers.
    Does NOT modify any project artifacts.
    """
    logger.info(f"Generating general chat response for: '{raw_input[:100]}'")
    
    # Build project context summary
    project_name = project_context.get("project_name", "Unnamed Project")
    reqs = project_context.get("requirements", {})
    if isinstance(reqs, list):
        epic_name = reqs[0].get("title", "") if reqs else ""
    elif isinstance(reqs, dict):
        epic_name = reqs.get("epic_name", "")
    else:
        epic_name = ""
    user_stories = project_context.get("user_stories", [])
    acceptance_criteria = project_context.get("acceptance_criteria", [])
    prd_markdown = project_context.get("generated_prd", "")
    
    context_parts = [f"Project Name: {project_name}"]
    if epic_name:
        context_parts.append(f"Epic: {epic_name}")
    
    if user_stories:
        story_lines = []
        for s in user_stories:
            ac_list = s.get("acceptance_criteria", [])
            ac_str = "; ".join(ac_list[:3])  # Limit to first 3 ACs to avoid token overflow
            story_lines.append(
                f"- {s.get('ticket_code', 'US')}: {s.get('story_title', '')}\n"
                f"  As a {s.get('as_a', '')}, I want to {s.get('i_want_to', '')}, So that {s.get('so_that', '')}\n"
                f"  Acceptance Criteria: {ac_str}"
            )
        context_parts.append("Current User Stories:\n" + "\n".join(story_lines))
    
    if acceptance_criteria:
        ac_summary = "\n".join([f"- {ac}" for ac in acceptance_criteria[:5]])
        context_parts.append(f"Acceptance Criteria:\n{ac_summary}")
    
    if prd_markdown:
        # Truncate PRD to avoid token overflow
        prd_preview = prd_markdown[:1500]
        context_parts.append(f"Current PRD (preview):\n{prd_preview}")
    
    # Build conversation history context (last 10 messages)
    if conversation_history:
        recent_msgs = conversation_history[-10:]
        history_lines = []
        for msg in recent_msgs:
            role = msg.get("role", "unknown")
            content = msg.get("message", msg.get("content", ""))
            if len(content) > 200:
                content = content[:200] + "..."
            history_lines.append(f"[{role}]: {content}")
        context_parts.append("Recent Conversation History:\n" + "\n".join(history_lines))
    
    full_context = "\n\n".join(context_parts)
    
    system_prompt = load_prompt("general_chat")
    
    try:
        from app.llm_factory import llm
        from langchain_core.messages import SystemMessage, HumanMessage
        
        messages = [
            SystemMessage(content=system_prompt + "\n\nCurrent Project Context:\n" + full_context),
            HumanMessage(content=raw_input)
        ]
        
        response = await llm.ainvoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)
        logger.info(f"Generated general chat response ({len(response_text)} chars)")
        return response_text
    except Exception as e:
        logger.error(f"Failed to generate general chat response: {str(e)}")
        return f"I understand you're asking about: '{raw_input}'. However, I encountered an issue generating a detailed response. Please try rephrasing your question."


async def match_requirement(raw_input: str, detected_intent: str, current_stories: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Requirement Matcher Agent between Intent Detection and Gatherer.
    Determines which existing requirement(s) the user's message refers to before any modification occurs.
    """
    if not raw_input or not str(raw_input).strip():
        return {
            "matched_requirement_id": None,
            "confidence": 1.0,
            "reason": "Empty input.",
            "action": "NEW",
            "status": "MATCHED",
            "candidates": None
        }

    logger.info(f"Running Requirement Matcher for input: '{raw_input[:100]}' with intent: {detected_intent}")

    # Same canonical backlog rendering as the semantic-change/intent/gatherer
    # prompts (previously this function kept its own copy-pasted format).
    context_lines = format_story_context_lines(
        [s for s in (current_stories or []) if isinstance(s, dict)]
    )
    current_context = "\n".join(context_lines) if context_lines else "No existing user stories in this project."

    prompt_template = PromptTemplate(
        template=load_prompt("matcher"),
        input_variables=["current_context", "detected_intent", "user_message", "format_instructions"]
    )

    pydantic_parser = JsonOutputParser(pydantic_object=RequirementMatcherResult)
    format_instructions = pydantic_parser.get_format_instructions()

    # Prefer .with_structured_output(), falling back to raw JSON parse
    def _is_valid_match(result: Dict[str, Any]) -> bool:
        """A match must carry a status and an action to be actionable."""
        return bool(_clean_str(result.get("action"))) and bool(_clean_str(result.get("status")))

    try:
        result = await invoke_llm_structured(
            llm,
            prompt_template,
            RequirementMatcherResult,
            variables={
                "current_context": current_context,
                "detected_intent": detected_intent,
                "user_message": raw_input,
                "format_instructions": "Output ONLY raw JSON matching the schema.",
            },
            description="requirement matcher",
            format_instructions=format_instructions,
            validate=_is_valid_match,
        )
        confidence = coerce_confidence(result.get("confidence", 0.85), default=0.85)
        status_val = _clean_str(result.get("status", "MATCHED")).upper() or "MATCHED"
        result["confidence"] = confidence
        result["status"] = status_val
        result["action"] = _clean_str(result.get("action")).upper() or "NEW"

        # Verify the reported target against the real backlog: a hallucinated or
        # mis-typed ticket code must not drive a mutation (same guardrail as the
        # semantic-change layer).
        matched_id = normalize_target_reference(result.get("matched_requirement_id"))
        if matched_id:
            resolved = resolve_target_story(matched_id, current_stories)
            if resolved:
                result["matched_requirement_id"] = resolved
            else:
                logger.warning(
                    "Requirement matcher returned target '%s' which is not in the backlog; "
                    "forcing clarification.", matched_id,
                )
                result["matched_requirement_id"] = None
                result["action"] = "NEW"
                result["status"] = "LOW_CONFIDENCE"
                result["confidence"] = min(confidence, UNRESOLVED_TARGET_CONFIDENCE)
                result["reason"] = (
                    f"{_clean_str(result.get('reason'))} Target '{matched_id}' does not exist in the "
                    "current backlog. Please confirm the ticket code."
                ).strip()
        elif str(result["action"]) in ("UPDATE", "DELETE") and current_stories:
            # UPDATE/DELETE without a resolvable target is not actionable.
            logger.warning("Requirement matcher returned action %s without a valid target.", result["action"])
            result["action"] = "NEW"
            result["status"] = "LOW_CONFIDENCE"
            result["confidence"] = min(confidence, UNRESOLVED_TARGET_CONFIDENCE)
            result["reason"] = (
                f"{_clean_str(result.get('reason'))} No existing story could be identified; "
                "please confirm the ticket code."
            ).strip()

        candidates = result.get("candidates")
        if isinstance(candidates, list):
            result["candidates"] = [
                resolve_target_story(c, current_stories) or normalize_target_reference(c)
                for c in candidates if _clean_str(c)
            ] or None

        if result["confidence"] < 0.75 and result["status"] == "MATCHED":
            result["status"] = "LOW_CONFIDENCE"
            result["reason"] = f"Confidence {result['confidence']} is below threshold (0.75). Clarification required."
        logger.info(f"Requirement matcher result: {result}")
        return result
    except Exception as e2:
        logger.error(f"Requirement matcher parsing failed completely: {str(e2)}")

    return {
        "matched_requirement_id": None,
        "confidence": 0.80,
        "reason": f"Fallback due to parsing failure",
        "action": "NEW",
        "status": "MATCHED",
        "candidates": None
    }



async def classify_workflow(raw_input: str) -> Dict[str, Any]:
    """
    Lightweight Workflow Router layer before the Gatherer Agent.
    Classifies every incoming user message into one of four workflow types:
    - CHAT
    - QUESTION
    - COMMAND
    - REQUIREMENT
    
    Returns structured JSON dict:
    {
        "workflow": "QUESTION",
        "confidence": 0.96,
        "reason": "The user is asking for an explanation rather than modifying project requirements."
    }
    """
    if not raw_input or not str(raw_input).strip():
        return {
            "workflow": "CHAT",
            "confidence": 1.0,
            "reason": "Empty input defaulted to CHAT."
        }

    clean_input = str(raw_input).strip()
    logger.info(f"Routing workflow classification for input: '{clean_input[:100]}'")

    prompt_template = PromptTemplate(
        template=load_prompt("router"),
        input_variables=["user_message", "format_instructions"]
    )

    pydantic_parser = JsonOutputParser(pydantic_object=WorkflowRoutingResult)
    format_instructions = pydantic_parser.get_format_instructions()

    # Prefer .with_structured_output(), falling back to raw JSON parse
    VALID_WORKFLOWS = ["CHAT", "QUESTION", "COMMAND", "REQUIREMENT"]

    def _is_valid_workflow(result: Dict[str, Any]) -> bool:
        return str(result.get("workflow", "")).strip().upper() in VALID_WORKFLOWS

    try:
        result = await invoke_llm_structured(
            llm,
            prompt_template,
            WorkflowRoutingResult,
            variables={
                "user_message": clean_input,
                "format_instructions": "Output ONLY raw JSON matching the schema.",
            },
            description="workflow routing",
            format_instructions=format_instructions,
            validate=_is_valid_workflow,
        )
        wf = str(result.get("workflow", "")).strip().upper()
        result["workflow"] = wf
        result["confidence"] = float(result.get("confidence", 0.90))
        result["reason"] = str(result.get("reason", ""))
        logger.info(f"Workflow router classified input via LLM: {result}")
        return result
    except Exception as e2:
        logger.error(f"Workflow router raw parsing failed: {str(e2)}")

    # Heuristic Fallback
    lower_inp = clean_input.lower()
    if lower_inp in ["hello", "hi", "thank you", "thanks", "good morning", "good afternoon", "good evening"]:
        return {
            "workflow": "CHAT",
            "confidence": 0.95,
            "reason": "The user is providing a conversational greeting or pleasantry."
        }
    elif lower_inp.startswith("what") or lower_inp.startswith("explain") or lower_inp.startswith("how") or lower_inp.startswith("can you explain") or lower_inp.endswith("?"):
        return {
            "workflow": "QUESTION",
            "confidence": 0.90,
            "reason": "The user is asking a direct question or seeking an explanation."
        }
    elif any(cmd in lower_inp for cmd in ["run auditor", "generate prd", "generate diagram", "export docx", "audit requirements"]):
        return {
            "workflow": "COMMAND",
            "confidence": 0.90,
            "reason": "The user is requesting an automated backend command execution."
        }
    else:
        return {
            "workflow": "REQUIREMENT",
            "confidence": 0.85,
            "reason": "The user input describes a software requirement or functional modification."
        }


