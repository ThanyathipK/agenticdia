import os
import logging
from pathlib import Path

logger = logging.getLogger("app.prompt_loader")

# Default prompts directory located at workspace root or app directory
BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", str(BASE_DIR / "prompts")))

def load_prompt(prompt_name: str) -> str:
    """
    Dynamically loads prompt template text from a markdown file in the prompts directory.
    E.g. load_prompt("gatherer") -> reads prompts/gatherer.md
    """
    filename = f"{prompt_name}.md" if not prompt_name.endswith(".md") else prompt_name
    filepath = PROMPTS_DIR / filename
    
    if not filepath.exists():
        # Fallback check in app/prompts
        alt_path = Path(__file__).resolve().parent / "prompts" / filename
        if alt_path.exists():
            filepath = alt_path

    if not filepath.exists():
        logger.error(f"Prompt file not found at: {filepath}")
        raise FileNotFoundError(f"Prompt file '{filename}' not found in prompts directory '{PROMPTS_DIR}'.")
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
            logger.info(f"Dynamically loaded prompt '{prompt_name}' from {filepath} ({len(content)} chars)")
            return content
    except Exception as e:
        logger.error(f"Failed to read prompt file {filepath}: {str(e)}")
        raise e


class _PromptProxy:
    """
    Lazily resolves a prompt template when it is used in string context.
    Shared by agents.py and semantic_service.py to avoid duplicate definitions.
    """
    def __init__(self, name: str):
        self.name = name
    def __str__(self) -> str:
        return load_prompt(self.name)
    def __add__(self, other: str) -> str:
        return load_prompt(self.name) + str(other)
    def __radd__(self, other: str) -> str:
        return str(other) + load_prompt(self.name)


# ----------------------------------------------------------------------------
# Krungsri Nimble PRD template helpers
# ----------------------------------------------------------------------------

# Static page-furniture lines left over from the original Word/PDF conversion
# of the Krungsri Nimble template (matched case-insensitively after trimming).
# They must NOT be copied verbatim into generated documents or the on-screen
# skeleton: headers/footers/page numbers are applied dynamically at export
# time with live values instead.
_PRD_TEMPLATE_FURNITURE = {"product requirement", "krungsri nimble confidential"}


def load_prd_template() -> str:
    """
    Loads prompts/template.md with its static page furniture stripped.

    The document STRUCTURE is preserved 100% (headings, section order, tables,
    <br> line breaks inside cells). Only the per-page artifacts are removed:
      - "PRODUCT REQUIREMENT" running-header lines
      - "KRUNGSRI NIMBLE CONFIDENTIAL" running-footer lines
      - bare page-number lines ("1", "2", ...)

    Downstream consumers:
      - GET /api/prd/template  -> clean skeleton for the right-panel preview
      - prd_export / architect prompts -> <prd_template> generation block
    """
    raw = load_prompt("template")
    kept: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.lower() in _PRD_TEMPLATE_FURNITURE:
            continue
        if stripped.isdigit():
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def load_prd_latex_template() -> str:
    """
    Loads prompts/template-krungsrinimble.tex - the authoritative, PDF-exact
    LaTeX PRD template.

    Unlike the markdown skeleton, this template needs no furniture stripping:
    the running header ("PRODUCT REQUIREMENT") and footer ("KRUNGSRI NIMBLE
    CONFIDENTIAL" + page number) are applied by the fancyhdr package at
    compile time rather than as literal lines. The file is a fill-in-the-blank
    document (PMO_NO, PMO_NAME, VERSION, STATUS, LAST_UPDATE, AUTHOR markers)
    that generation should complete from per-project data.

    Downstream consumers:
      - architect / prd_export prompts -> <prd_template> generation block
      - GET /api/prd/template -> authoritative LaTeX skeleton
    """
    # load_prompt appends ".md", so read the .tex file directly.
    filepath = PROMPTS_DIR / "template-krungsrinimble.tex"
    if not filepath.exists():
        alt_path = Path(__file__).resolve().parent / "prompts" / "template-krungsrinimble.tex"
        if alt_path.exists():
            filepath = alt_path
    if not filepath.exists():
        raise FileNotFoundError(
            f"LaTeX PRD template not found: {filepath}"
        )
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_prd_latex_template_body() -> str:
    """Loads ONLY the document BODY of template-krungsrinimble.tex.

    Everything between \\\\begin{document} and \\\\end{document} is returned - i.e.
    the part generation actually fills in. The preamble (\\\\documentclass,
    packages, fancyhdr setup) stays server-side: `latex_service.ensure_full_document`
    splices generated bodies into the real template before compiling, which keeps
    the exported artifact PDF-exact while halving the LLM output size.
    """
    tex = load_prd_latex_template()
    start = tex.find("\\begin{document}")
    end = tex.rfind("\\end{document}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("Authoritative LaTeX template has an unrecognisable document body.")
    body_start = start + len("\\begin{document}")
    return tex[body_start:end].strip()
