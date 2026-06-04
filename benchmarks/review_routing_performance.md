# Review Routing Benchmarks

This benchmark compares token usage, execution latency, and routing correctness across the supported review adapters.

| Reviewer Adapter | Closer Adapter | Reviewer Resolved | Closer Resolved | Total LLM Tokens | Latency | Status |
|---|---|---|---|---|---|---|
| agy | agy | agy | agy | 1530 | 0.90ms | succeeded |
| codex | codex | codex | codex | 800 | 0.20ms | succeeded |
| claude | claude | claude | claude | 800 | 0.17ms | succeeded |
| off | off | off | off | 800 | 0.17ms | succeeded |
| codex | agy | codex | agy | 1080 | 0.16ms | succeeded |

### Architectural Insights
- **`agy` Routing (Gemini Flash)**: Standard OAuth/Gemini transport for full agentic validation, pulling from `ScriptedAdapter` or live Gemini API.
- **`codex` Routing (Codex CLI)**: Intercepted in read-only mode by the conductor, emitting structured verification evidence containing route metadata with zero additional LLM token cost.
- **`claude` Routing (Claude CLI)**: Intercepted in read-only mode, serving as a future/optional CLI integration path with zero token cost.
- **`off` Routing**: Bypasses validation entirely, completing the nodes with zero tokens and clean metadata.
