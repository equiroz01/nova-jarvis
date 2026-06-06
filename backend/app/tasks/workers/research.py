"""Research worker — multi-step web search + LLM synthesis."""

import asyncio
import logging

from .base import llm_generate, brave_search, get_workspace_dir, save_to_brain, parse_json_response

logger = logging.getLogger(__name__)

DECOMPOSE_SYSTEM = """You are a research planning assistant.
Given a research question, decompose it into 3-6 specific sub-questions that, when answered together, provide a comprehensive understanding of the topic.
Return ONLY a JSON array of strings. No explanations, no markdown, just the JSON array.
Example: ["What is X?", "How does X compare to Y?", "What are the latest developments in X?"]"""

SYNTHESIZE_SYSTEM = """You are a senior research analyst. Synthesize the following search results into a comprehensive, well-structured markdown report.

Requirements:
- Write in the SAME LANGUAGE as the original question
- Include: Executive Summary, detailed sections for each topic area, key findings, and a Sources section
- Use markdown formatting: headers (##), bullet points, bold for key terms
- Be thorough but concise — aim for 800-1500 words
- Cite sources inline where relevant using [Source Name](URL) format
- End with a "Sources" section listing all referenced URLs"""


async def research_worker(task, update_progress) -> str:
    """Execute a multi-step research task.

    Pipeline: decompose → search each sub-question → synthesize → save
    """
    task_id = task.id

    # Step 1: Decompose the question into sub-questions
    await update_progress(task_id, "task_update", progress=5, progress_text="Analizando pregunta...")

    sub_questions = await _decompose(task.description)
    n = len(sub_questions)
    logger.info(f"Research {task_id[:8]}: decomposed into {n} sub-questions")

    await update_progress(
        task_id, "task_update",
        progress=10, progress_text=f"Plan: {n} sub-preguntas identificadas",
    )

    # Step 2: Search each sub-question
    all_results = {}
    for i, question in enumerate(sub_questions):
        progress = 20 + int(50 * i / n)
        await update_progress(
            task_id, "task_update",
            progress=progress, progress_text=f"Buscando ({i+1}/{n}): {question[:50]}...",
        )

        # Web search
        results = await asyncio.get_event_loop().run_in_executor(
            None, brave_search, question, 5, False
        )

        # Also try news for current-event queries
        news_kw = ["2025", "2026", "latest", "recent", "noticias", "nuevo", "actual", "trends"]
        if any(kw in question.lower() for kw in news_kw):
            news = await asyncio.get_event_loop().run_in_executor(
                None, brave_search, question, 3, True
            )
            results.extend(news)

        all_results[question] = results
        logger.info(f"Research {task_id[:8]}: Q{i+1}/{n} got {len(results)} results")

        # Small delay between searches
        await asyncio.sleep(0.3)

    # Check if we got any results at all
    total_results = sum(len(r) for r in all_results.values())
    if total_results == 0:
        logger.warning(f"Research {task_id[:8]}: zero search results, using LLM knowledge only")
        await update_progress(task_id, "task_update", progress=75, progress_text="Sin resultados web, usando conocimiento del modelo...")
        report = await llm_generate(
            f"Write a comprehensive research report about: {task.description}",
            system="You are a research analyst. Write a detailed markdown report based on your knowledge. "
                   "Write in the SAME LANGUAGE as the question. Include headers, bullet points, and structure.",
        )
    else:
        # Step 3: Synthesize into a report
        await update_progress(task_id, "task_update", progress=75, progress_text=f"Sintetizando {total_results} resultados...")
        report = await _synthesize(task.title, task.description, all_results)

    # Step 4: Save to brain and workspace
    await update_progress(task_id, "task_update", progress=90, progress_text="Guardando reporte...")

    save_to_brain(f"Research: {task.title}", report, category="facts")

    workspace = get_workspace_dir(task_id)
    report_path = workspace / "report.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info(f"Research {task_id[:8]}: report saved to {report_path}")

    return report


async def _decompose(description: str) -> list[str]:
    """Decompose a research question into sub-questions."""
    try:
        response = await llm_generate(description, system=DECOMPOSE_SYSTEM)
        questions = parse_json_response(response)
        if isinstance(questions, list) and len(questions) >= 2:
            return questions[:6]  # Cap at 6
    except Exception as e:
        logger.warning(f"Decompose failed: {e}")

    # Fallback: use the original question as-is
    return [description]


async def _synthesize(title: str, original_question: str, results: dict) -> str:
    """Synthesize search results into a markdown report."""
    # Build context from all search results
    context_parts = [f"# Research: {title}\n\nOriginal question: {original_question}\n"]

    for question, items in results.items():
        context_parts.append(f"\n## Sub-question: {question}\n")
        if not items:
            context_parts.append("No results found.\n")
            continue
        for r in items:
            title_r = r.get("title", "")
            desc = r.get("description", "")
            url = r.get("url", "")
            source = r.get("source", "")
            age = r.get("age", "")
            extra = f" ({source}, {age})" if source else ""
            context_parts.append(f"- **{title_r}**{extra}: {desc}\n  URL: {url}\n")

    context = "\n".join(context_parts)

    try:
        report = await llm_generate(context, system=SYNTHESIZE_SYSTEM)
        return report
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        # Fallback: return raw results as markdown
        return context
