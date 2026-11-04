## Go navigation (codenav-go)
Use the `codenav-go` MCP for Go symbols and type-aware edits when it is available.
- Find definitions, uses, callers and implementations with `symbol_info`, `references`, `callers`,
  `implementations`, `search_symbol` or `outline`. Use the position tools for exact locations.
- Prefer `rename_symbol`, `change_signature` and `move` for refactoring. Use `edit_symbol` or `edit` for Go edits
  and `quick_fix` for language-server fixes. These tools type-check changes; a rejected or previewed edit is not an
  applied change. Apply a reviewed preview with `apply_edit` and use `undo_edit` when appropriate.
- Review diagnostics and the diff, then run the project's quality gate. Go build tags, nested modules and generated
  files can limit what gopls sees; check the tool's warnings and the project's build configuration.
- If the MCP is unavailable or errors, report it under Friction and use appropriate fallback tools. Text search is
  suitable for docs, configuration and non-symbol text.
