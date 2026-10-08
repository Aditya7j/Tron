# Tron — Known Architecture

## Core Runtime
Important known components include:
- `server.py`
- `build.py`
- `brain_live.mjs`
- `eyes_live.mjs`
- `focus.py`
- `hands.py`
- `preflight.py`
- `viewer/`
- `notes/`
- `tools/`
- `config.json`

## Runtime
Known local server:
- `127.0.0.1:4700`

Build:
- `python build.py`

Browser integration:
- Chrome remote debugging port `9222`

## Knowledge System
- Markdown notes are ingested/compiled.
- `build.py` acts as ingestion/indexing, not the actual Jarvis brain.
- Generates graph/knowledge artifacts such as `viewer/graph-data.js` and `notes-index.json`.
- Knowledge Galaxy visualizes relationships between notes/entities.

## AI / Routing
Architecture has included:
- Bedrock
- OpenAI
- OpenRouter
- multi-model routing
- direct AWS SigV4 support
- allowlisted runtime model switching

## Perception
- screen vision
- stale-frame protection
- browser live loops
- vision/eyes subsystem
- focus subsystem
- aggregate focus ledger

## APIs / Capabilities
Known routes/features include:
- `/chat`
- `/remember`
- `/see`
- `/model`
- `/brains`

## Testing
Existing foundation includes:
- unit tests
- live/preflight checks
- QA/privacy tests

## Important Architectural Guidance
The existing foundation was considered strong in:
- knowledge
- memory
- perception
- routing
- testing
- privacy

Major capability areas identified for expansion:
- tool execution
- tool router / agent loop
- verification
- semantic memory
- event-based continuous perception
- proactive behavior

Do not rewrite the architecture just because a new feature is being added.
