"""Field-by-field SI to BL comparison."""

from __future__ import annotations

from typing import Any

from .extract import FIELDS, ReviewRequired
from .normalize import normalize_field


def compare_documents(si_fields: dict[str, str], bl_fields: dict[str, str]) -> dict[str, Any]:
    mismatches: list[dict[str, str]] = []
    for field in FIELDS:
        si_normalized = normalize_field(field, si_fields[field])
        bl_normalized = normalize_field(field, bl_fields[field])
        if si_normalized is None or bl_normalized is None:
            raise ReviewRequired(
                "unreadable",
                "unreliable_field_normalization",
                f"Could not reliably normalize {field}",
            )
        if si_normalized != bl_normalized:
            mismatches.append(
                {"field": field, "si_value": si_fields[field], "bl_value": bl_fields[field]}
            )

    if not mismatches:
        return {"status": "OK", "message": "No mismatch detected.", "mismatches": []}
    return {
        "status": "MISMATCH",
        "message": f"Mismatch detected in {len(mismatches)} field(s).",
        "mismatches": mismatches,
    }
