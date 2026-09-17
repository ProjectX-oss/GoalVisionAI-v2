"""Presentation and action contracts used by the console boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TableModel:
    title: str
    columns: tuple[str,...]
    rows: tuple[tuple[object,...],...]


@dataclass(frozen=True, slots=True)
class PageModel:
    title: str
    status: str
    summary: tuple[tuple[str,object],...]
    tables: tuple[TableModel,...]
    warnings: tuple[str,...]=()
    controlled_demo: bool=False


@dataclass(frozen=True, slots=True)
class ActionRequest:
    request_id: str
    action_type: str
    operator_identifier: str
    source_page: str
    target_identifier: str | None
    confirmation: str
    normalized_input: dict[str,object]
    requested_at_utc: str
