# Local Setup

This project keeps machine state, Obsidian notes, and bookmark exports separate.

## Obsidian Vault

Create a normal Obsidian vault first, then point `obsidian_vault_path` to that folder in `config/knowledge_sources.json`.

Example:

```json
{
  "obsidian_vault_path": "/Users/you/Obsidian/LinuxDo-AI-Knowledge"
}
```

For a quick local smoke test, the example config uses:

```json
{
  "obsidian_vault_path": "obsidian/linuxdo"
}
```

That creates a project-local vault folder. It is useful for testing, but a real personal vault should usually live in your normal Obsidian sync folder.

Do not store WebDAV usernames, passwords, tokens, or sync secrets in `knowledge_sources.json`.

## Bookmark Export

`bookmark-sync` reads a local LinuxDo Scripts bookmark export JSON. It does not log into WebDAV and does not need the WebDAV account.

Configure either path:

```json
{
  "linuxdo_scripts_bookmarks": {
    "enabled": true,
    "path": "data/linuxdo/bookmarks.json",
    "fallback_download_path": "data/linuxdo/bookmarkData.json"
  }
}
```

If neither file exists, `bookmark-sync` exits safely with zero changes. This lets you run the knowledge workflow before bookmark sync is fully set up.

## First Smoke Test

```bash
cp config/knowledge_sources.example.json config/knowledge_sources.json
python3 tools/linuxdo_surf.py knowledge-init --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py feedback-sync --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py bookmark-sync --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 3
```

If `knowledge-plan` has no items, that is expected before bookmarks, browser-selected topics, or manual frontier entries exist.
