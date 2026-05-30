"""
N.O.V.A. Brain — Obsidian vault as persistent knowledge graph.

Reads and writes markdown notes with [[links]] to build a knowledge graph.
The vault can be opened in Obsidian for visual graph exploration.
"""

import os
import re
import logging
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

VAULT_PATH = Path(__file__).parent.parent.parent / "nova-brain"

# Categories map to vault subdirectories
CATEGORIES = {
    "people": "people",
    "persona": "people",
    "fact": "facts",
    "facts": "facts",
    "project": "projects",
    "projects": "projects",
    "preference": "preferences",
    "preferences": "preferences",
    "conversation": "conversations",
    "daily": "daily",
}


def _vault_dir() -> Path:
    VAULT_PATH.mkdir(parents=True, exist_ok=True)
    return VAULT_PATH


def _slugify(text: str) -> str:
    """Convert text to a safe filename."""
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    return text.strip()[:80]


def _extract_links(content: str) -> list[str]:
    """Extract [[wiki links]] from markdown content."""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def _extract_tags(content: str) -> list[str]:
    """Extract tags from frontmatter."""
    match = re.search(r'tags:\s*\[([^\]]*)\]', content)
    if match:
        return [t.strip() for t in match.group(1).split(',') if t.strip()]
    return []


def save_note(
    title: str,
    content: str,
    category: str = "facts",
    tags: list[str] = None,
    links: list[str] = None,
) -> str:
    """Save a note to the vault. Creates or updates if exists."""
    vault = _vault_dir()
    subdir = CATEGORIES.get(category.lower(), "facts")
    folder = vault / subdir
    folder.mkdir(parents=True, exist_ok=True)

    filename = _slugify(title) + ".md"
    filepath = folder / filename

    # Build frontmatter
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    all_tags = list(set((tags or []) + [category]))
    tag_str = ", ".join(all_tags)

    # Add links to content
    if links:
        for link in links:
            if f"[[{link}]]" not in content:
                content += f"\n\nRelated: [[{link}]]"

    note = f"""---
tags: [{tag_str}]
created: {now}
---

# {title}

{content}
"""

    # Check if note exists — update instead of overwrite
    if filepath.exists():
        existing = filepath.read_text(encoding="utf-8")
        # Update the created date from existing
        created_match = re.search(r'created:\s*(.+)', existing)
        if created_match:
            note = note.replace(f"created: {now}", f"created: {created_match.group(1).strip()}\nupdated: {now}")

    filepath.write_text(note, encoding="utf-8")
    logger.info(f"Brain: saved note '{title}' in {subdir}/")
    return f"Note saved: {subdir}/{filename}"


def search_notes(query: str, max_results: int = 5) -> list[dict]:
    """Search all notes in the vault by content and title."""
    vault = _vault_dir()
    results = []
    query_lower = query.lower()
    query_words = set(query_lower.split())

    for md_file in vault.rglob("*.md"):
        if md_file.name == "README.md":
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        content_lower = content.lower()
        title = md_file.stem
        title_lower = title.lower()
        rel_path = md_file.relative_to(vault)

        # Scoring
        score = 0.0

        # Exact query in content
        if query_lower in content_lower:
            score = 0.9

        # Query in title
        if query_lower in title_lower:
            score = max(score, 1.0)

        # Word overlap
        content_words = set(content_lower.split())
        overlap = query_words & content_words
        word_score = len(overlap) / max(len(query_words), 1) * 0.7
        score = max(score, word_score)

        # Title similarity
        sim = SequenceMatcher(None, query_lower, title_lower).ratio()
        score = max(score, sim * 0.6)

        if score > 0.2:
            # Extract summary (first non-frontmatter, non-heading line)
            lines = content.split('\n')
            summary = ""
            in_frontmatter = False
            for line in lines:
                if line.strip() == '---':
                    in_frontmatter = not in_frontmatter
                    continue
                if in_frontmatter or line.startswith('#') or not line.strip():
                    continue
                summary = line.strip()[:150]
                break

            results.append({
                "title": title,
                "path": str(rel_path),
                "summary": summary,
                "score": round(score, 2),
                "links": _extract_links(content),
                "tags": _extract_tags(content),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def read_note(title: str) -> str:
    """Read a specific note by title (searches all subdirs)."""
    vault = _vault_dir()
    slug = _slugify(title)

    for md_file in vault.rglob("*.md"):
        if md_file.stem.lower() == slug.lower() or md_file.stem.lower() == title.lower():
            return md_file.read_text(encoding="utf-8")

    return f"Note '{title}' not found in the vault."


def list_notes(category: str = None) -> list[dict]:
    """List all notes, optionally filtered by category."""
    vault = _vault_dir()
    results = []

    for md_file in vault.rglob("*.md"):
        if md_file.name == "README.md":
            continue
        rel_path = md_file.relative_to(vault)
        folder = rel_path.parts[0] if len(rel_path.parts) > 1 else "root"

        if category:
            target_dir = CATEGORIES.get(category.lower(), category.lower())
            if folder != target_dir:
                continue

        results.append({
            "title": md_file.stem,
            "category": folder,
            "path": str(rel_path),
        })

    return results


def get_context(query: str, max_notes: int = 3) -> str:
    """Get relevant knowledge context for a query. Used to enrich prompts."""
    results = search_notes(query, max_results=max_notes)
    if not results:
        return ""

    vault = _vault_dir()
    context_parts = []
    for r in results:
        filepath = vault / r["path"]
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            # Strip frontmatter
            parts = content.split('---', 2)
            body = parts[2].strip() if len(parts) >= 3 else content
            context_parts.append(f"[{r['title']}]: {body[:300]}")

    return "\n\n".join(context_parts)


def get_stats() -> dict:
    """Get vault statistics."""
    vault = _vault_dir()
    categories = {}
    total = 0
    total_links = 0

    for md_file in vault.rglob("*.md"):
        if md_file.name == "README.md":
            continue
        total += 1
        rel_path = md_file.relative_to(vault)
        folder = rel_path.parts[0] if len(rel_path.parts) > 1 else "root"
        categories[folder] = categories.get(folder, 0) + 1

        try:
            content = md_file.read_text(encoding="utf-8")
            total_links += len(_extract_links(content))
        except Exception:
            pass

    return {
        "total_notes": total,
        "total_links": total_links,
        "categories": categories,
    }
