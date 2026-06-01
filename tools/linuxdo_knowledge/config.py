from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FORBIDDEN_CONFIG_KEYS = {
    "webdav_password",
    "webdav_token",
    "webdav_username",
    "webdav_account",
    "password",
    "token",
}


@dataclass(frozen=True)
class KnowledgeConfig:
    project_root: Path
    state_root: Path
    obsidian_vault_path: Path
    bookmark_path: Path | None
    fallback_bookmark_path: Path | None
    chrome_context_enabled: bool
    github_verification_enabled: bool


def load_config(path: Path) -> KnowledgeConfig:
    config_path = path.expanduser().resolve()
    project_root = _infer_project_root(config_path)
    data = _read_json_object(config_path)
    _reject_secret_keys(data)

    bookmark_config = data.get("linuxdo_scripts_bookmarks", {})
    if not isinstance(bookmark_config, dict):
        bookmark_config = {}
    chrome_config = data.get("chrome_context", {})
    if not isinstance(chrome_config, dict):
        chrome_config = {}
    github_config = data.get("github_verification", {})
    if not isinstance(github_config, dict):
        github_config = {}

    return KnowledgeConfig(
        project_root=project_root,
        state_root=_resolve_path(data.get("state_root", Path("state") / "knowledge"), project_root),
        obsidian_vault_path=_resolve_path(data.get("obsidian_vault_path", Path("obsidian") / "linuxdo"), project_root),
        bookmark_path=_optional_path(bookmark_config.get("path"), project_root),
        fallback_bookmark_path=_optional_path(bookmark_config.get("fallback_download_path"), project_root),
        chrome_context_enabled=_optional_bool(chrome_config.get("enabled", True), "chrome_context.enabled"),
        github_verification_enabled=_optional_bool(
            github_config.get("enabled", True), "github_verification.enabled"
        ),
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("knowledge config must be a JSON object")
    return data


def _infer_project_root(config_path: Path) -> Path:
    if config_path.parent.name == "config":
        return config_path.parent.parent
    return config_path.parent


def _resolve_path(value: Any, project_root: Path) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


def _optional_path(value: Any, project_root: Path) -> Path | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _resolve_path(value, project_root)


def _optional_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean")


def _reject_secret_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_CONFIG_KEYS:
                raise ValueError("WebDAV credentials must not be stored in knowledge config")
            _reject_secret_keys(child)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_keys(item)
