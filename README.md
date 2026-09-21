# Jasine

A private, persistent digital brain with cross-conversation memory, correction,
forgetting, semantic retrieval, a lightweight knowledge graph, feedback capture,
model-run observability, and a responsive chat interface.

## Run

Jasine has no third-party runtime dependencies; Python 3.11+ is sufficient.

```bash
python server.py
# open http://localhost:8000
```

Data is persisted in `jasine.db` (override with `JASINE_DB`). Set
`OPENAI_API_KEY` to use an OpenAI-compatible reasoning model and optionally set
`JASINE_MODEL`; without it, Jasine uses its private local grounded responder so
the complete memory lifecycle remains usable offline. Set `JASINE_DEV_EMAIL`
before registering an account to enable its developer-only brain inspector.

## Test

```bash
python -m unittest discover -v
```

The API is under `/api`: authentication, conversations, chat, memories/search,
memories/forget, feedback, entities, reflections, and developer inspection are
all server-backed. Chat responses use incrementally readable NDJSON. Passwords
are PBKDF2 hashed, sessions expire, and every conversation and memory query is
owner-scoped.
