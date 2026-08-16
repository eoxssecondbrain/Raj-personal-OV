# Raj Personal Vault

Personal, single-user second-brain vault. See `SPEC.md` (parent directory) for
the full authoritative spec. This README covers setup and operation.

**For the complete step-by-step manual setup (accounts, credentials,
dashboard clicks), see `MANUAL_SETUP.md`.** This README is the reference
summary; MANUAL_SETUP.md is the thing you actually follow in order.

## Architecture note: one combined service, not three

SPEC.md originally called for three independently-deployed services
(`ingestion`, `wiki_writer`, `mcp_server`) sharing one persistent disk.
Render disks are 1:1 per service, and `mcp_server` needs read access to
`raw/` (not just `vault/`), so all three run as one Render **web service**
(`services/combined/main.py`) instead:

- An HTTP server thread serves the MCP endpoint (`search_vault`, `read_page`,
  `list_pages`, `list_raw_files`, `read_raw_file`).
- A background scheduler thread runs `ingestion` and `wiki_writer` on
  independent intervals (staggered so `wiki_writer` runs after `ingestion`
  has had time to populate `raw/`).
- All three read/write the same disk, mounted at `VAULT_DATA_ROOT`.

The individual `services/ingestion/main.py` and `services/wiki_writer/main.py`
still work standalone (e.g. for local dev, or if you ever want to split them
back into separate Render services) — `services/combined/main.py` just
imports and schedules their existing `run()` functions rather than
duplicating logic.

The disk mount **is** the git working tree — `vault/`, `raw/`, `state.db`,
and `.git` all live together at `VAULT_DATA_ROOT`. On first boot against an
empty disk, the app clones `GIT_REMOTE_URL` into place automatically (see
`services/common/paths.py::bootstrap_git_repo`).

## Setup

Full detail in `MANUAL_SETUP.md`. Summary of what you'll create:

1. **Anthropic API key** (`ANTHROPIC_API_KEY`) — powers image vision
   extraction and wiki-filing decisions.
2. **Private GitHub repo** + fine-grained access token (`GIT_REMOTE_URL`) —
   backup/audit trail for the vault.
3. **Google Cloud service account** (`GOOGLE_SERVICE_ACCOUNT_JSON`,
   `DRIVE_FOLDER_ID`) — read-only access to Raj's upload folder.
4. **MCP endpoint token** (`MCP_URL_TOKEN`) — long random secret in the
   connector URL path.
5. **Render deployment** — one web service from `infra/vault.render.yaml`,
   with a persistent disk and all the above as env vars.
6. **ChatGPT custom connector** — registered once `mcp_server` is deployed
   and reachable.

## Operating

### Normal operation

Fully automated — no human in the loop. Raj drops files in Drive, ingestion
and wiki_writer run on schedule inside the combined service, ChatGPT queries
the vault (and raw source documents) via MCP.

### Triage (operator only)

Check `vault/_needs-review/` periodically for flagged entries (ambiguous
content or extraction failures). For each:

```
cd services/wiki_writer
python resolve.py approve <hash>   # apply the agent's draft as-is
python resolve.py reject <hash>    # discard, won't re-flag same source again
```

To edit before approving: open the review `.md` file, edit the
"What the agent would have done" section directly, save, then run `approve`.
Running `resolve.py` against the live Render disk means either exec'ing into
the running instance's shell (see Render's dashboard Shell tab) or running it
locally against a `git pull`ed copy and pushing the result — the former is
simpler since it operates on the same disk `wiki_writer` itself uses.

### Monitoring

- Render's built-in service-health notifications catch the process crashing.
- Each ingestion/wiki_writer run also writes to the `job_runs` table in
  `state.db` (`status`, `timestamp`, `files_processed`) — check this to catch
  silent failures (e.g. a stale Drive token causing zero files to process
  every run, while the service itself stays "up").

## Local development

```
pip install -r services/combined/requirements.txt
cp .env.example .env   # fill in at least ANTHROPIC_API_KEY to test wiki_writer's decision step
python dev/seed_fake_raw.py       # seed a fake successful extraction
python dev/seed_fake_review.py    # seed a fake extraction failure
python services/wiki_writer/main.py
python services/mcp_server/main.py   # standalone MCP server on :8000
```

`VAULT_DATA_ROOT` is unset locally, so everything defaults to this repo's
working tree — no separate disk/clone step needed for local testing.

## What's explicitly out of scope for V1

See SPEC.md Section 14 — Drive-side deletion handling and embeddings-based
retrieval are deferred to V2.
