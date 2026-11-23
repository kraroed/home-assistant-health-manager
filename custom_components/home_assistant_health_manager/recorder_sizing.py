"""Utilities for keeping entity attribute payloads below Recorder limits.

The helper measures the UTF-8 JSON representation of the complete attribute
mapping, including page metadata. It never drops or truncates a record: a
single record that cannot fit raises an explicit exception for the caller to
surface and route to the full diagnostic report.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_ATTRIBUTE_BUDGET = 12_000


class RecordTooLargeError(ValueError):
    """Raised when one record cannot fit in a Recorder-safe page."""


def json_attribute_size(attributes: Mapping[str, Any]) -> int:
    """Return the UTF-8 byte length of a JSON-serialized attribute mapping."""
    return len(
        json.dumps(
            attributes,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def pack_json_records(
    records: Sequence[Mapping[str, Any]],
    *,
    attribute_key: str = "items",
    metadata: Mapping[str, Any] | None = None,
    max_bytes: int = DEFAULT_ATTRIBUTE_BUDGET,
) -> list[list[Mapping[str, Any]]]:
    """Pack records into pages whose complete attribute payload fits budget.

    Metadata is included in every size calculation. Empty input produces one
    empty page so callers can keep a stable page-zero entity. No record is
    discarded. If one record cannot fit by itself, raise RecordTooLargeError.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    base = dict(metadata or {})
    if attribute_key in base:
        raise ValueError(f"metadata must not contain reserved key {attribute_key!r}")

    def payload(page: list[Mapping[str, Any]]) -> dict[str, Any]:
        return {**base, attribute_key: page}

    pages: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []

    for index, record in enumerate(records):
        candidate = [*current, record]
        if json_attribute_size(payload(candidate)) <= max_bytes:
            current = candidate
            continue

        if current:
            pages.append(current)
            current = [record]
        else:
            current = [record]

        size = json_attribute_size(payload(current))
        if size > max_bytes:
            raise RecordTooLargeError(
                f"Record {index} requires {size} bytes; page budget is {max_bytes}"
            )

    if current or not pages:
        pages.append(current)

    return pages
