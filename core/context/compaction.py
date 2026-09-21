"""Harness-based conversation compaction for AZ sessions."""

from __future__ import annotations

from pydantic_ai.messages import ToolCallPart
from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    DeduplicateFileReads,
    SummarizingCompaction,
    TieredCompaction,
)

from config.settings import Settings
from models.mimo import build_mimo_model

SUMMARY_PROMPT = """\
You summarize prior turns of an AI assistant conversation for future context reuse.

Produce a compact, factual summary using exactly this template:
HISTORICAL SUMMARY
Goals: ...
Constraints: ...
Established facts: ...
Decisions: ...
Open questions: ...
Relevant files and entities: ...
END HISTORICAL SUMMARY

Rules:
- Do not add facts that are not present in the conversation.
- Prefer exact file paths, identifiers, commands, and API names when they matter.
- Refine any earlier summary included in the conversation instead of duplicating it.
- Use `none` when a field has no content.
- Return only the summary, with no preamble or code fence.

<messages>
{messages}
</messages>\
"""


def file_read_key(call: ToolCallPart) -> str | None:
    """Return a stable key for tools that read a project file."""
    if call.tool_name not in {"read_project_file", "read_file"}:
        return None

    args = call.args_as_dict()
    path = args.get("file_path") or args.get("path")
    return str(path) if path else None


def build_compaction(settings: Settings) -> TieredCompaction:
    """Build the cheap-to-expensive context budget policy for an AZ run."""
    return TieredCompaction(
        tiers=[
            ClampOversizedMessages(
                max_part_tokens=settings.context_max_part_tokens,
            ),
            DeduplicateFileReads(file_key=file_read_key),
            ClearToolResults(
                max_tokens=1,
                keep_pairs=settings.context_keep_tool_pairs,
            ),
            SummarizingCompaction(
                model=build_mimo_model(settings),
                max_messages=1,
                keep_messages=settings.context_keep_messages,
                summary_prompt=SUMMARY_PROMPT,
            ),
        ],
        target_tokens=settings.context_target_tokens,
    )
