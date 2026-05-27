# Personal Agent

A local extensible personal agent framework running in WSL.

Current features:

- CLI agent runtime
- DeepSeek-compatible LLM adapter
- Tool registry / planner / executor
- Obsidian + Thino schedule parser
- Schedule inbox and daily overview
- Git backup support
- Safe write operations with diff / confirmation

## Setup

```bash
uv sync
cp .env.example .env
cp configs/agent.example.yaml configs/agent.yaml
```

finally,
koishi is absolutely right!!