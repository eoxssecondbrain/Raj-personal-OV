# Manual Setup Guide

Everything in this repo's code is built, tested, and ready to deploy.
Everything below is work only you can do — account creation, credential
generation, and dashboard configuration. Follow it in order; each section
produces a value the next section needs. Do this on personal/separate
accounts throughout (not EOXS company accounts/orgs/billing) — that isolation
is the whole point of the design.

Keep a scratch text file open while you go — you'll collect about 8 values
along the way (each marked **SAVE THIS**) that all get pasted into Render's
dashboard in Section 6.

---

## 1. Anthropic API key

Used for image vision extraction (ingestion) and wiki-filing decisions
(wiki_writer).

1. Go to https://console.anthropic.com and sign in or create an account —
   personal account, not EOXS-billed, unless you specifically want this
   billed to the company.
2. Left sidebar → **API Keys** → **Create Key**.
3. Name it `raj-vault`.
4. Copy the key (starts with `sk-ant-...`) — shown once.
5. **SAVE THIS** as `ANTHROPIC_API_KEY`.
6. Go to **Billing** and add a payment method / credits — the key won't work
   without billing configured. Cost is small and mostly proportional to
   *informational* images and documents processed (see SPEC.md Section 6 for
   the per-image cost breakdown, roughly $0.01–0.02 for an image worth full
   extraction, near-zero for everything screened out at the cheap triage
   pass).

---

## 2. GitHub — private repo for the vault backup

This is what the app pushes to after every automated wiki_writer commit, and
what it clones from to bootstrap the Render disk on first boot.

### Create the repo

1. Go to https://github.com and sign in with a personal account, separate
   from any EOXS-owned GitHub org.
2. **+** (top right) → **New repository**.
3. Name: `raj-personal-vault` (or your choice — just remember it).
4. Visibility: **Private**. Never public — this becomes Raj's full life
   record.
5. Do **not** check "Add a README" / "Add .gitignore" / "Choose a license" —
   this repo already has all of those locally; you're pushing existing
   history into an empty remote, not merging with a generated one.
6. **Create repository**. On the next page, copy the HTTPS clone URL shown,
   e.g. `https://github.com/<your-username>/raj-personal-vault.git`.
7. **SAVE THIS** as `GITHUB_REPO_URL`.

### Generate a scoped access token

1. Profile picture (top right) → **Settings**.
2. Left sidebar, scroll down → **Developer settings**.
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new
   token**.
4. Token name: `raj-vault-push`.
5. Expiration: your choice (fine-grained tokens can't be set to "no
   expiration" — pick something like 1 year and set a reminder to rotate it).
6. **Repository access** → **Only select repositories** → choose
   `raj-personal-vault`.
7. **Permissions** → **Repository permissions** → **Contents** → **Read and
   write**. Leave everything else at "No access."
8. **Generate token**. Copy it (starts with `github_pat_...`) — shown once,
   cannot be viewed again.
9. **SAVE THIS** as `GITHUB_TOKEN`.

### Push the local repo from your machine

In the `raj-personal-vault/` folder on your machine (already git-initialized
and committed):

```powershell
git remote add origin https://github.com/<your-username>/raj-personal-vault.git
git branch -M main
git push -u origin main
```

When prompted for credentials, use your GitHub username and the
`GITHUB_TOKEN` value as the password (GitHub no longer accepts account
passwords for git operations over HTTPS).

### Build the GIT_REMOTE_URL value

This is the single value the deployed app uses both to bootstrap-clone the
persistent disk on first boot and to push after every wiki_writer commit.
Embed the token directly in the URL:

```
https://<GITHUB_TOKEN>@github.com/<your-username>/raj-personal-vault.git
```

**SAVE THIS** as `GIT_REMOTE_URL`.

---

## 3. Google Cloud — Drive service account

Used by `ingestion` to read files from Raj's upload folder, read-only. Full
background in SPEC.md Section 11 — this is the exact click-by-click version.

### Project + API

1. Go to https://console.cloud.google.com. Sign in with a personal Google
   account (not an EOXS Workspace account) — full isolation from company
   infra.
2. Top left, next to "Google Cloud" → project dropdown → **New Project**.
3. Name: `raj-vault`. Organization: "No organization" if you're given the
   choice. **Create**.
4. Confirm the new project is selected in the top dropdown (it can take a
   few seconds to appear after creation).
5. Left hamburger menu → **APIs & Services** → **Library**.
6. Search "Google Drive API" → click it → **Enable**.

### Service account

1. Left menu → **APIs & Services** → **Credentials**.
2. **+ Create Credentials** → **Service account**.
3. Name: `raj-vault-ingest`. **Create and Continue**.
4. On "Grant this service account access to project" — skip it, click
   **Continue**.
5. On "Grant users access to this service account" — skip it, click **Done**.
   (No IAM roles are needed; access comes entirely from sharing the Drive
   folder directly with this account, in the next section.)
6. You land back on the Credentials page. Under **Service Accounts**, click
   the one you just created.
7. Note the email at the top of the page, formatted like
   `raj-vault-ingest@raj-vault-123456.iam.gserviceaccount.com`.

### JSON key

1. On the service account's page, click the **Keys** tab.
2. **Add Key** → **Create new key** → **JSON** → **Create**.
3. A `.json` file downloads. This is your permanent credential — no expiry,
   and it cannot be re-downloaded if lost (only regenerated as a brand new
   key, invalidating the old one). Store the downloaded file somewhere safe
   until you've pasted its contents into Render.
4. Open the file in a plain text editor, select all, copy.
5. **SAVE THIS** (the entire JSON blob, as one value) as
   `GOOGLE_SERVICE_ACCOUNT_JSON`.

### Drive folder

1. Go to https://drive.google.com signed in as **Raj's normal Google
   account** — the one he'll actually use day to day to upload files. This
   does **not** need to be the same account you used for the Cloud project
   above.
2. Create a new folder — suggested name: `Raj Vault Uploads`.
3. Right-click the folder → **Share**.
4. In "Add people," paste the service account email from above.
5. Set its role to **Viewer** (not Editor — the pipeline only ever reads).
6. Uncheck "Notify people" (it's a service account, sending it an email
   notification does nothing useful) → **Share**.
7. Open the folder and look at the browser URL:
   `https://drive.google.com/drive/folders/<FOLDER_ID>`. Copy the
   `<FOLDER_ID>` segment.
8. **SAVE THIS** as `DRIVE_FOLDER_ID`.

---

## 4. MCP endpoint token

A long random secret embedded in the MCP server's URL path so the endpoint
isn't guessable (SPEC.md Section 13 — treat it as internet-facing regardless
of obscurity, hence the rate limiting already built into `mcp_server`).

On your machine, run:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**SAVE THIS** output as `MCP_URL_TOKEN`.

---

## 5. Architecture note before you deploy

The app runs as **one combined Render web service**, not three separate
services. Reason: Render's persistent disks are 1:1 with a single service,
but ingestion, wiki_writer, and mcp_server all need to read/write the same
`vault/`, `raw/`, and `state.db` — and you specifically want `mcp_server` to
be able to pull raw source documents too, not just finished vault pages, so
a git-pull-only sync for `mcp_server` wasn't sufficient. `services/combined/main.py`
runs an HTTP server (the MCP endpoint) plus a background scheduler
(ingestion + wiki_writer on their own intervals) in one process, on one disk.
No further decision needed here — just context for what you're about to
deploy.

---

## 6. Render deployment

1. Go to https://render.com and sign up with a personal account, separate
   from any company Render usage.
2. You'll land in your personal team/workspace by default — that's fine, no
   separate team needed.
3. **New** (top right) → **Web Service**.
4. Connect your GitHub account if prompted, then select the
   `raj-personal-vault` repo you pushed in Section 2.
   - If you'd rather not grant Render access to GitHub, choose "Public Git
     repository" is not an option here since the repo is private — GitHub
     connection is required for a private repo source.
5. Configure:
   - **Name**: `raj-vault`
   - **Region**: your choice (pick something geographically close to you)
   - **Branch**: `main`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r services/combined/requirements.txt`
   - **Start Command**: `python services/combined/main.py`
   - **Instance Type**: Starter is enough to begin with.
6. Before clicking create, scroll to **Add Disk**:
   - **Name**: `raj-vault-disk`
   - **Mount Path**: `/var/data`
   - **Size**: 5 GB (plenty of headroom for documents + extracted text +
     vault markdown; increase later if needed, Render allows resizing)
7. Scroll to **Environment Variables** and add every value you saved above:

   | Key | Value |
   |---|---|
   | `VAULT_DATA_ROOT` | `/var/data` (must exactly match the mount path above) |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | the full JSON blob from Section 3 |
   | `DRIVE_FOLDER_ID` | from Section 3 |
   | `ANTHROPIC_API_KEY` | from Section 1 |
   | `GIT_REMOTE_URL` | from Section 2 |
   | `MCP_URL_TOKEN` | from Section 4 |
   | `PORT` | `8000` |
   | `INGESTION_MAX_ITEMS` | `20` |
   | `INGESTION_MAX_SECONDS` | `600` |
   | `WIKI_WRITER_MAX_ITEMS` | `20` |
   | `WIKI_WRITER_MAX_SECONDS` | `600` |
   | `INGESTION_INTERVAL_MINUTES` | `240` |
   | `WIKI_WRITER_INTERVAL_MINUTES` | `240` |
   | `WIKI_WRITER_OFFSET_MINUTES` | `30` |

   (This matches `infra/vault.render.yaml` exactly — you can also use
   Render's "Blueprint" deploy flow pointing at that file instead of manual
   entry, if you prefer; the manual dashboard steps above achieve the same
   result.)
8. **Create Web Service**. Render will build and deploy. Watch the deploy
   log — on first boot you should see a `git clone` of your GitHub repo into
   `/var/data` (the `bootstrap_git_repo` step), then the scheduler starting,
   then the HTTP server coming up.
9. Once live, note the service's public URL, e.g.
   `https://raj-vault.onrender.com`.

### Verify it's working

- Visit `https://raj-vault.onrender.com/<MCP_URL_TOKEN>/mcp` — a bare GET
  won't return a friendly page (it's an MCP protocol endpoint, not a
  browser page), but it shouldn't 404 or show a server error either.
- In Render's dashboard, check the service **Logs** tab for the first
  scheduled `ingestion` run (default: fires ~10 seconds after boot in the
  current config, then every `INGESTION_INTERVAL_MINUTES`). If
  `DRIVE_FOLDER_ID` or `GOOGLE_SERVICE_ACCOUNT_JSON` are wrong, you'll see
  the error there immediately rather than waiting hours to notice nothing's
  happening.
- Also enable Render's built-in failure notifications: service → **Settings**
  → **Notifications**, turn on deploy/health failure alerts to your email.

---

## 7. ChatGPT custom connector

Only do this after Section 6 is deployed and verified reachable.

1. In ChatGPT, go to **Settings** → **Connectors**.
2. Enable **Developer mode** if it's not already on.
3. **Add custom connector** (exact wording may vary by ChatGPT version).
4. Paste the URL: `https://<your-render-host>/<MCP_URL_TOKEN>/mcp`
   (e.g. `https://raj-vault.onrender.com/AbCdEf.../mcp`).
5. Save. Test by asking ChatGPT something like "list the pages in my vault"
   or "what's in my vault about insurance" — it should call `list_pages` or
   `search_vault` and return real (or currently empty) results.

---

## After setup: day-to-day

- **Raj's job**: drop files into the shared Drive folder. Nothing else.
- **Your job (operator)**: periodically check `vault/_needs-review/` on the
  deployed disk (via Render's dashboard **Shell** tab, or by pulling the
  GitHub repo locally after a wiki_writer push) and run
  `python services/wiki_writer/resolve.py approve <hash>` or `reject <hash>`
  for anything flagged. See README.md's "Triage" section for the full
  command reference.
