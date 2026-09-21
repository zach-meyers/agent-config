# Third-party notices

This file records **externally sourced** material copied or adapted into `~/.agents` (for example pinned skills from upstream repositories). Locally authored content does not require an entry here.

## Format

Add one section per upstream source when content is imported:

```markdown
### <short name>

- **Source:** <URL> at commit `<full-sha>`
- **Path in this repo:** `skills/<name>/` (or other path)
- **License:** <SPDX or license name>
- **Reviewed:** <YYYY-MM-DD>
- **Notes:** <optional: scope restrictions, excerpts omitted, etc.>
```

## Current notices

### dotnet/skills (MSTest and performance skills)

- **Source:** https://github.com/dotnet/skills at commit `9beca0b0be339affea6420c2a2721293f2e9dcdb`
- **Paths in this repo:** `skills/writing-mstest-tests/`, `skills/test-anti-patterns/`, `skills/analyzing-dotnet-performance/`
- **Upstream paths:** `plugins/dotnet-test/skills/writing-mstest-tests`, `plugins/dotnet-test/skills/test-anti-patterns`, `plugins/dotnet-diag/skills/analyzing-dotnet-performance`
- **License:** MIT — full text in [`licenses/dotnet-skills-9beca0b0-LICENSE`](licenses/dotnet-skills-9beca0b0-LICENSE) (upstream [`LICENSE`](https://github.com/dotnet/skills/blob/9beca0b0be339affea6420c2a2721293f2e9dcdb/LICENSE))
- **Reviewed:** 2026-09-21
- **Notes:** Instruction and reference markdown only; no upstream scripts in these subtrees.

### microsoft/azure-skills (azure-diagnostics)

- **Source:** https://github.com/microsoft/azure-skills at commit `50b0f1c0295d8580da49e815d8a1261f860559e6`
- **Path in this repo:** `skills/azure-diagnostics/`
- **Upstream path:** `skills/azure-diagnostics`
- **License:** MIT — full text in [`licenses/microsoft-azure-skills-50b0f1c0-LICENSE`](licenses/microsoft-azure-skills-50b0f1c0-LICENSE) (upstream [`LICENSE`](https://github.com/microsoft/azure-skills/blob/50b0f1c0295d8580da49e815d8a1261f860559e6/LICENSE))
- **Reviewed:** 2026-09-21
- **Notes:** Vendored `SKILL.md`, `references/`, and `troubleshooting/`; omitted upstream `scripts/` (see `sources.lock.json`). Added local `LOCAL_COMPATIBILITY.md` for script/MCP server gaps. MCP tool names in docs assume a client Azure MCP integration.

### MicrosoftDocs/Agent-Skills (azure-well-architected)

- **Source:** https://github.com/MicrosoftDocs/Agent-Skills at commit `90ec55f3dc95837df8b9f7bd6265fb5935ccdca6`
- **Path in this repo:** `skills/azure-well-architected/`
- **Upstream path:** `skills/azure-well-architected`
- **License:** CC-BY-4.0 — full text in [`licenses/MicrosoftDocs-Agent-Skills-90ec55f3-LICENSE`](licenses/MicrosoftDocs-Agent-Skills-90ec55f3-LICENSE) (upstream [`LICENSE`](https://github.com/MicrosoftDocs/Agent-Skills/blob/90ec55f3dc95837df8b9f7bd6265fb5935ccdca6/LICENSE))
- **Copyright / legal notices:** [`licenses/MicrosoftDocs-Agent-Skills-90ec55f3-ThirdPartyNotices.md`](licenses/MicrosoftDocs-Agent-Skills-90ec55f3-ThirdPartyNotices.md) (upstream [`ThirdPartyNotices.md`](https://github.com/MicrosoftDocs/Agent-Skills/blob/90ec55f3dc95837df8b9f7bd6265fb5935ccdca6/ThirdPartyNotices.md)); repository code license [`licenses/MicrosoftDocs-Agent-Skills-90ec55f3-LICENSE-CODE`](licenses/MicrosoftDocs-Agent-Skills-90ec55f3-LICENSE-CODE) (upstream [`LICENSE-CODE`](https://github.com/MicrosoftDocs/Agent-Skills/blob/90ec55f3dc95837df8b9f7bd6265fb5935ccdca6/LICENSE-CODE))
- **Reviewed:** 2026-09-21
- **Notes:** `SKILL.md` only at this commit; no additional assets in upstream subtree. Vendored skill content is documentation under CC-BY-4.0 per upstream notices.
