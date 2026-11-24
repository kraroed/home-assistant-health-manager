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


def recorder_safe_attributes(
    attributes: Mapping[str, Any],
    *,
    report_path: str | None,
    entity_key: str,
    max_bytes: int = DEFAULT_ATTRIBUTE_BUDGET,
) -> dict[str, Any]:
    """Return attributes unchanged when safe, otherwise an explicit report pointer.

    This is a last-resort guard while record collections are being paginated.
    It never silently truncates: the replacement payload identifies the
    overflow, measured size, affected keys, and whether a full report exists.
    """
    size = json_attribute_size(attributes)
    if size <= max_bytes:
        return dict(attributes)

    record_counts = {
        key: len(value)
        for key, value in attributes.items()
        if isinstance(value, (list, dict))
    }
    fallback = {
        "recorder_attribute_overflow": True,
        "overflowed_entity_key": entity_key,
        "original_attribute_bytes": size,
        "attribute_budget_bytes": max_bytes,
        "overflowed_attribute_keys": list(attributes),
        "overflowed_collection_counts": record_counts,
        "details_preserved_in_report": bool(report_path and report_verified),
        "full_details_report": report_path,\n        "report_verification_status": "verified" if report_verified else "unverified",
        "note": (
            "Attributes exceeded the Recorder-safe budget. No records were "
            "truncated; consult the full diagnostic report."
            if report_path and report_verified else
            "Attributes exceeded the Recorder-safe budget. No records were "
            "truncated, but no report path is available yet. Run diagnostics "
            "to generate a full report."
        ),
    }
    if json_attribute_size(fallback) > max_bytes:
        # The fallback is deliberately compact and contains no source records.
        raise RecordTooLargeError("Recorder overflow fallback exceeds its budget")
    return fallback
