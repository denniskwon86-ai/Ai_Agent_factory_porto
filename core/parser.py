import re

def extract_summary(text: str) -> str:
    """Extracts content inside <summary> tags. Returns empty string if not found."""
    if not text:
        return ""
    match = re.search(r"<summary>(.*?)</summary>", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""

def extract_artifact(text: str) -> str:
    """Extracts content inside <artifact> tags. Fallbacks to full text if not found."""
    if not text:
        return ""
    match = re.search(r"<artifact>(.*?)</artifact>", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Fallback: remove <summary> tag if it exists so we don't duplicate it in the raw artifact
    text_without_summary = re.sub(r"<summary>.*?</summary>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text_without_summary.strip()
