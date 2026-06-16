from __future__ import annotations


ALIASES = {
    "vibe-coding": "Vibecoding",
    "vibe coding": "Vibecoding",
    "vibecoding": "Vibecoding",
    "cli proxy api": "CPA",
    "cliproxyapi": "CPA",
    "cpa": "CPA",
    "opencode": "OpenCode",
    "open code": "OpenCode",
    "ccswitch": "CC-Switch",
    "cc-switch": "CC-Switch",
    "cc switch": "CC-Switch",
    "vs code": "VS Code",
    "vscode": "VS Code",
    "new-api": "New API",
    "new api": "New API",
    "oneapi": "OneAPI",
    "one api": "OneAPI",
}


def canonicalize_name(name: str) -> str:
    cleaned = str(name).strip()
    normalized = " ".join(cleaned.replace("_", " ").replace("-", " ").lower().split())
    compact = normalized.replace(" ", "")
    hyphenated = normalized.replace(" ", "-")
    if normalized in ALIASES:
        return ALIASES[normalized]
    if compact in ALIASES:
        return ALIASES[compact]
    if hyphenated in ALIASES:
        return ALIASES[hyphenated]
    return cleaned
