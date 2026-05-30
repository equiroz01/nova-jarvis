from langchain.tools import tool
from app.knowledge.brain import save_note, search_notes, read_note, list_notes, get_stats


@tool
def remember(fact: str, category: str = "facts", related: str = "") -> str:
    """Save something to your memory/brain. Use this when the user says 'recuerda que...', 'anota que...',
    or tells you important information you should remember for later.
    Categories: people, facts, projects, preferences, conversations.
    Related: comma-separated names of related notes to link with [[links]]."""
    links = [r.strip() for r in related.split(",") if r.strip()] if related else []
    # Use the fact as title if short, otherwise generate one
    title = fact[:60] if len(fact) < 80 else fact.split('.')[0][:60]
    return save_note(title=title, content=fact, category=category, links=links)


@tool
def recall(query: str) -> str:
    """Search your memory/brain for information you've stored before.
    Use this when you need to check if you know something about a person, project, or fact.
    Also use this BEFORE answering personal questions about the user or their contacts."""
    results = search_notes(query, max_results=5)
    if not results:
        return "I don't have any stored knowledge about that."

    lines = []
    for r in results:
        tags = ", ".join(r.get("tags", [])) if r.get("tags") else ""
        links = ", ".join(r.get("links", [])) if r.get("links") else ""
        path = r.get("path", "")
        lines.append(f"- **{r['title']}** [{path}] (relevance: {r['score']})")
        if r.get("summary"):
            lines.append(f"  {r['summary']}")
        if links:
            lines.append(f"  Links: {links}")

    return "Knowledge found:\n" + "\n".join(lines)


@tool
def read_memory(title: str) -> str:
    """Read a specific note from your brain by its title.
    Use this when you found a note via recall and want to read the full content."""
    return read_note(title)


@tool
def brain_stats() -> str:
    """Get statistics about your brain/knowledge vault.
    Use this when the user asks what you know or how much you've learned."""
    stats = get_stats()
    lines = [
        f"Total notes: {stats['total_notes']}",
        f"Total connections: {stats['total_links']}",
        "Categories:",
    ]
    for cat, count in stats["categories"].items():
        lines.append(f"  - {cat}: {count} notes")
    return "\n".join(lines)
