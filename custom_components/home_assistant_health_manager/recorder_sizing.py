"""Utilities for keeping entity attribute payloads below Recorder limits."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_ATTRIBUTE_BUDGET = 12_000


class RecordTooLargeError(ValueError):
    """Raised when one record cannot fit in a Recorder-safe page."""


def json_attribute_size(attributes: Mapping[str, Any]) -> int:
    """Return the UTF-8 byte length of a JSON-serialized attribute mapping."""
    return len(json.dumps(attributes, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def pack_json_records(records: Sequence[Mapping[str, Any]], *, attribute_key: str = "items", metadata: Mapping[str, Any] | None = None, max_bytes: int = DEFAULT_ATTRIBUTE_BUDGET) -> list[list[Mapping[str, Any]]]:
    """Pack records into pages without dropping or truncating records."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    base = dict(metadata or {})
    if attribute_key in base:
        raise ValueError(f"metadata must not contain reserved key {attribute_key!r}")

    def payload(page):
        return {**base, attribute_key: page}

    pages = []
    current = []
    for index, record in enumerate(records):
        candidate = [*current, record]
        if json_attribute_size(payload(candidate)) <= max_bytes:
            current = candidate
            continue
        if current:
            pages.append(current)
        current = [record]
        size = json_attribute_size(payload(current))
        if size > max_bytes:
            raise RecordTooLargeError(f"Record {index} requires {size} bytes; page budget is {max_bytes}")
    if current or not pages:
        pages.append(current)
    return pages


def recorder_safe_attributes(attributes: Mapping[str, Any], *, report_path: str | None, entity_key: str, report_verified: bool = False, max_bytes: int = DEFAULT_ATTRIBUTE_BUDGET) -> dict[str, Any]:
    """Return safe attributes or an explicit overflow reference.

    A path is metadata, not proof of preservation. Callers may set
    report_verified only after validating the report archive and its contents.
    """
    size = json_attribute_size(attributes)
    if size <= max_bytes:
        return dict(attributes)

    record_counts = {
        key: len(value)
        for key, value in attributes.items()
        if isinstance(value, (list, dict))
    }
    verified = bool(report_path and report_verified)
    fallback = {
        "recorder_attribute_overflow": True,
        "overflowed_entity_key": entity_key,
        "original_attribute_bytes": size,
        "attribute_budget_bytes": max_bytes,
        "overflowed_attribute_keys": list(attributes),
        "overflowed_collection_counts": record_counts,
        "details_preserved_in_report": verified,
        "full_details_report": report_path,
        "report_verification_status": "verified" if verified else "unverified",
        "note": (
            "Attributes exceeded the Recorder-safe budget. No records were truncated; the diagnostic report was verified."
            if verified else
            "Attributes exceeded the Recorder-safe budget. No records were truncated, but the diagnostic report is not verified. Review report verification before relying on preservation."
        ),
    }
    if json_attribute_size(fallback) > max_bytes:
        raise RecordTooLargeError("Recorder overflow fallback exceeds its budget")
    return fallback
