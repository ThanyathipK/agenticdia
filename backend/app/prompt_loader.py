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
