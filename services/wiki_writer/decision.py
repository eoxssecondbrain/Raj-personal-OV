"""Calls the model to decide + draft the resolution for one raw entry.

Per SPEC.md Section 4 / Section 9: three-way outcome, prompt-injection guard.
Retrieval of "relevant existing pages" is simple filename/keyword matching
for V1 (embeddings deferred to V2 per SPEC.md Section 14).
"""
import json
import os

import anthropic

from wiki_writer.prompts.system_prompt import SYSTEM_PROMPT

MODEL = "claude-sonnet-5"

DECISION_TOOL = {
    "name": "file_decision",
    "description": "Report the filing decision and draft for this raw entry.",
    "input_schema": {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "string",
                "enum": ["CONFIDENT_UPDATE", "NEW_INFO", "NEEDS_REVIEW"],
            },
            "target_page": {
                "type": "string",
                "description": "Vault-relative path this content targets, e.g. vault/04-finance/insurance.md",
            },
            "draft_content": {
                "type": "string",
                "description": "Full markdown content to write (full page for CONFIDENT_UPDATE/new page, or the section to append for NEW_INFO append case).",
            },
            "reason": {
                "type": "string",
                "description": "One-sentence explanation of the decision. Required and most important for NEEDS_REVIEW.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
        },
        "required": ["outcome", "target_page", "draft_content", "reason", "confidence"],
    },
}


def _client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)


def find_candidate_pages(vault_dir, source_filename, content, limit=5):
    """Simple keyword/filename matching against existing vault pages (V1 -- see SPEC.md Section 14)."""
    import re

    tokens = set(re.findall(r"[a-z0-9]+", (source_filename + " " + content[:2000]).lower()))
    tokens = {t for t in tokens if len(t) > 3}

    scored = []
    for md_path in vault_dir.rglob("*.md"):
        if "_needs-review" in md_path.parts:
            continue
        name_tokens = set(re.findall(r"[a-z0-9]+", md_path.stem.lower()))
        score = len(tokens & name_tokens)
        if score > 0:
            scored.append((score, md_path))

    scored.sort(key=lambda x: -x[0])
    return [str(p.relative_to(vault_dir.parent)) for _, p in scored[:limit]]


def decide(raw_entry_content, source_filename, candidate_pages, vault_dir):
    """Returns dict matching DECISION_TOOL schema."""
    candidate_text = "\n".join(
        f"- {p}: {(vault_dir.parent / p).read_text(encoding='utf-8')[:1500]}"
        for p in candidate_pages
        if (vault_dir.parent / p).exists()
    ) or "(no candidate pages found)"

    user_message = f"""Source filename: {source_filename}

Raw extracted content:
---
{raw_entry_content[:8000]}
---

Candidate existing pages that might relate to this content:
{candidate_text}

Decide the outcome and produce your draft."""

    client = _client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        tools=[DECISION_TOOL],
        tool_choice={"type": "tool", "name": "file_decision"},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "file_decision":
            return block.input

    raise RuntimeError("model did not return a file_decision tool call")
