"""Prompt envelope declarations for compacted conversation history."""

COMPACTED_HISTORY_SUMMARY_TEMPLATE = (
    "COMPACTED CONVERSATION SUMMARY (older turns): {summary}"
)


###############################################################################
def build_compacted_history_summary(summary: str) -> str:
    return COMPACTED_HISTORY_SUMMARY_TEMPLATE.format(summary=summary)
