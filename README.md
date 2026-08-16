# Raj Personal Vault

Personal, single-user second-brain vault. See `SPEC.md` (parent directory) for
the full authoritative spec. This README covers setup and operation.

## Setup

### 1. Google Drive service account (SPEC.md Section 11)

1. Create a **new, dedicated Google Cloud project** (not the company's).
2. Enable the **Google Drive API** on that project (APIs & Services → Enable APIs).
3. IAM & Admin → Service Accounts → Create Service Account. Note the email,
   e.g. `raj-vault-ingest@<project>.iam.gserviceaccount.com`.
4. On that service account → Keys → Add Key → JSON. Download it once — this
   is the permanent credential, no expiry, no renewal.
5. In Google Drive, share the specific folder Raj uploads to with that
   service account's email, **Viewer** access only.
6. Paste the entire JSON key contents into the `GOOGLE_SERVICE_ACCOUNT_JSON`
   Render env var (as a single-line JSON string). Never commit the key file.
7. Set `DRIVE_FOLDER_ID` to the target folder's ID (from its Drive URL).

### 2. Anthropic API key

Set `ANTHROPIC_API_KEY` as a Render secret on `ingestion`, `wiki_writer`, and
anywhere the vision/decision calls run.

### 3. MCP endpoint token

Generate a long random token (`python -c "import secrets; print(secrets.token_urlsafe(32))"`)
and set it as `MCP_URL_TOKEN` on the `mcp_server` Render service. The
connector URL to register in ChatGPT is `https://<your-render-host>/<MCP_URL_TOKEN>/mcp`.

### 4. Git remote for vault backups — GitHub

Create a **private GitHub repo** under a personal/separate GitHub account —
not an EOXS-owned org or shared account, to keep this isolated per the
infra-isolation requirement (same principle as the fresh Render account).

- **Visibility: private.** Never public — this is Raj's full life record.
- **Collaborators: none** by default. Single-operator system, least privilege.
- **Auth: fine-grained personal access token** scoped to just this one repo
  (Contents: read/write only — no other permissions), or a repo-scoped
  deploy key with write access. Do not use a classic PAT with broad
  account-wide scope.
- GitHub's secret scanning / push protection is on by default for private
  repos on most plans — a useful extra safety net if a credential is ever
  accidentally staged for commit, though it's not a substitute for keeping
  secrets out of the repo in the first place (see `.gitignore`).

`wiki_writer` commits directly to this repo's working tree on Render's disk,
and pushes to GitHub after each commit (see `services/wiki_writer/git_ops.py`
and the `GIT_REMOTE_URL` / `GITHUB_TOKEN` env vars). Store the token as a
Render secret; never hardcode it into a committed remote URL.

### 5. Render deployment

Fresh Render account/team, separate from company usage. Create three
services from `infra/*.yaml`:
- `raj-vault-ingestion` (cron)
- `raj-vault-wiki-writer` (cron)
- `raj-vault-mcp` (web service, always-on)

All three should share the same persistent disk so `vault/`, `raw/`, and
`state.db` are visible to all of them.

## Operating

### Normal operation

Fully automated — no human in the loop. Raj drops files in Drive, ingestion
and wiki_writer run on schedule, ChatGPT queries the vault via MCP.

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

### Monitoring

- Render's built-in cron failure notifications are enabled on both cron jobs.
- Each run also writes to the `job_runs` table in `state.db`
  (`status`, `timestamp`, `files_processed`) — check this to catch silent
  failures (e.g. a stale Drive token causing zero files to process every run).

## What's explicitly out of scope for V1

See SPEC.md Section 14 — Drive-side deletion handling and embeddings-based
retrieval are deferred to V2.

## Full manual setup guide

Every step you need to do by hand (accounts, credentials, dashboard clicks)
is in `MANUAL_SETUP.md` at the repo root, in the order you should do them.
