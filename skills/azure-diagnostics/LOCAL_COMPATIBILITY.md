# Local vendoring compatibility

> **This file is local to `~/.agents` and is not part of upstream `microsoft/azure-skills`.**

Upstream commit `50b0f1c0295d8580da49e815d8a1261f860559e6` includes a `scripts/` directory with PowerShell and Bash helpers referenced from `SKILL.md` companion docs (`references/`, `troubleshooting/`). Those executables were **omitted** here per local policy (no vendored scripts or hooks).

When a guide links to `scripts/*.sh` or `scripts/*.ps1`, use the **`az` / `kubectl` commands in the same section** as the manual equivalent, or retrieve the script from the pinned upstream tree:

https://github.com/microsoft/azure-skills/tree/50b0f1c0295d8580da49e815d8a1261f860559e6/skills/azure-diagnostics/scripts

MCP tool names in `SKILL.md` and `troubleshooting/aks/references/aks-mcp.md` assume an Azure MCP server in the client; this vendored copy does not ship MCP server configuration.
