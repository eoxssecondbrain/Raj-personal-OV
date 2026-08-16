"""mcp_server: vault/ -> ChatGPT

Exposes exactly three tools, per SPEC.md Section 3:
  search_vault(query), read_page(path), list_pages(section)

Reads directly off vault/ on disk at query time -- no DB dependency, so a
state.db issue never breaks Raj's ability to query.

Deliberately does NOT expose any review/triage/pending-review tool. Raj is a
pure end-user of the vault; all _needs-review/ triage is operator-only via
services/wiki_writer/resolve.py (see SPEC.md Section 5).
"""
import os
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VAULT_DIR = REPO_ROOT / "vault"
REVIEW_DIR_NAME = "_needs-review"

# Long random token in the URL path (SPEC.md Section 13) -- set via Render env var.
# The connector URL Raj registers in ChatGPT is https://<host>/<MCP_URL_TOKEN>/mcp
MCP_URL_TOKEN = os.environ.get("MCP_URL_TOKEN")
if not MCP_URL_TOKEN:
    raise RuntimeError("MCP_URL_TOKEN env var not set -- required so the endpoint isn't guessable")

mcp = FastMCP("raj-personal-vault", streamable_http_path=f"/{MCP_URL_TOKEN}/mcp")


def _is_visible(path: Path) -> bool:
    """Excludes the operator-only _needs-review/ folder from all query results."""
    return REVIEW_DIR_NAME not in path.parts


def _safe_resolve(rel_path: str) -> Path:
    """Resolve a vault-relative path and ensure it stays inside vault/."""
    candidate = (VAULT_DIR / rel_path).resolve()
    if VAULT_DIR.resolve() not in candidate.parents and candidate != VAULT_DIR.resolve():
        raise ValueError("path escapes vault directory")
    return candidate


@mcp.tool()
def search_vault(query: str) -> list[dict]:
    """Search the vault for pages matching a keyword query. Returns matches with a text snippet."""
    query_terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    if not query_terms:
        return []

    results = []
    for md_path in VAULT_DIR.rglob("*.md"):
        if not _is_visible(md_path):
            continue
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        lower = text.lower()
        score = sum(lower.count(t) for t in query_terms)
        if score == 0:
            continue

        first_hit = min((lower.find(t) for t in query_terms if t in lower), default=0)
        start = max(0, first_hit - 100)
        snippet = text[start:start + 300].strip()

        results.append({
            "path": str(md_path.relative_to(REPO_ROOT)),
            "score": score,
            "snippet": snippet,
        })

    results.sort(key=lambda r: -r["score"])
    return results[:20]


@mcp.tool()
def read_page(path: str) -> str:
    """Read the full markdown content of a single vault page by its path (e.g. vault/04-finance/insurance.md)."""
    resolved = _safe_resolve(path.replace("vault/", "", 1) if path.startswith("vault/") else path)
    if not _is_visible(resolved):
        raise ValueError("page not found")
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"page not found: {path}")
    return resolved.read_text(encoding="utf-8", errors="ignore")


@mcp.tool()
def list_pages(section: str = "") -> list[str]:
    """List vault page paths, optionally scoped to a section (e.g. '04-finance'). Empty section lists everything."""
    base = VAULT_DIR / section if section else VAULT_DIR
    if not base.exists():
        return []
    pages = []
    for md_path in base.rglob("*.md"):
        if not _is_visible(md_path):
            continue
        pages.append(str(md_path.relative_to(REPO_ROOT)))
    return sorted(pages)


class RateLimitMiddleware:
    """Basic IP-based rate limiting (SPEC.md Section 13: treat this endpoint as
    internet-facing regardless of URL obscurity). A hand-rolled sliding-window
    limiter instead of slowapi, which assumes every route is a plain function
    handler with __name__ -- the MCP streamable-HTTP transport mounts a raw
    ASGI sub-app instead, which breaks slowapi's route introspection.
    """

    def __init__(self, app, max_requests=60, window_seconds=60):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = {}  # ip -> list[monotonic timestamps]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import time

        client = scope.get("client")
        ip = client[0] if client else "unknown"
        now = time.monotonic()

        hits = [t for t in self._hits.get(ip, []) if now - t < self.window_seconds]
        hits.append(now)
        self._hits[ip] = hits

        if len(hits) > self.max_requests:
            response_body = b'{"error": "rate limit exceeded"}'
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": response_body})
            return

        await self.app(scope, receive, send)


def build_app():
    app = mcp.streamable_http_app()
    return RateLimitMiddleware(app, max_requests=60, window_seconds=60)


app = build_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
