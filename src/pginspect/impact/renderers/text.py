"""Text renderer for `ImpactCommandResult` (summary then cards)."""

from __future__ import annotations

from pginspect.impact.models.card import ImpactStatementCard
from pginspect.impact.models.result import ImpactCommandResult
from pginspect.renderers.text import escape_terminal_value


def render_impact_text(result: ImpactCommandResult) -> str:
    """Render outcome summary then statement cards in statement_index order."""
    lines: list[str] = [
        f"Impact: {result.outcome.value} (exit {result.exit_code})",
        (
            f"Input: {escape_terminal_value(result.input.path_basename)} "
            f"({result.input.card_count} cards, "
            f"{result.input.source_statement_count} statements)"
        ),
        f"Overall risk: {result.summary.overall_risk.value}",
        f"Incomplete: {'yes' if result.summary.incomplete else 'no'}",
    ]
    if result.connection_context is not None:
        ctx = result.connection_context
        lines.append(
            "Server: "
            f"{escape_terminal_value(ctx.server_version)} "
            f"(major {ctx.server_major}, db {escape_terminal_value(ctx.database)})"
        )
    if result.error is not None:
        lines.append(f"Error: {escape_terminal_value(result.error.message)}")
    if result.statements:
        lines.append("")
        lines.append("Statements:")
        for card in result.statements:
            lines.extend(_render_card(card))
    return "\n".join(lines) + "\n"


def render_impact_text_debug(result: ImpactCommandResult) -> str | None:
    """Render structured debug for stderr, or None when absent."""
    error = result.error
    if error is None or error.debug is None:
        return None
    debug = error.debug
    lines: list[str] = [
        "Debug:",
        f"  exception_type: {escape_terminal_value(debug.exception_type)}",
    ]
    if debug.causal_chain_types:
        chain = ", ".join(escape_terminal_value(t) for t in debug.causal_chain_types)
        lines.append(f"  causal_chain: {chain}")
    for frame in debug.frames:
        module = escape_terminal_value(frame.module)
        function = escape_terminal_value(frame.function)
        lines.append(f"  {module}.{function}:{frame.line}")
    return "\n".join(lines) + "\n"


def _render_card(card: ImpactStatementCard) -> list[str]:
    lines = [
        f"  #{card.statement_index} [{card.analysis_status.value}] "
        f"risk={card.risk.value} execution={card.execution_prediction.value}",
        f"    preview: {escape_terminal_value(card.sanitized_preview)}",
        (
            f"    lock={card.lock.value} "
            f"rewrite={card.table_rewrite.value} "
            f"scan={card.table_scan.value} "
            f"index_rebuild={card.index_rebuild.value}"
        ),
    ]
    if card.no_op_reason is not None:
        lines.append(f"    no_op_reason: {card.no_op_reason.value}")
    for reason in card.why:
        lines.append(f"    why: {escape_terminal_value(reason)}")
    for limitation in card.limitations:
        lines.append(f"    limitation: {escape_terminal_value(limitation)}")
    return lines
