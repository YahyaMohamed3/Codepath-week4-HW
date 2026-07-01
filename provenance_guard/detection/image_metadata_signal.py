"""Image-metadata provenance signals.

This module analyzes structured image *metadata*, never pixels. It exposes three
independent signals, each returning an AI-likelihood score in ``[0, 1]``:

1. ``generation_tool``   — does the metadata name a known generative tool?
2. ``metadata_consistency`` — are the fields internally consistent/plausible?
3. ``provenance_history`` — is there credible creator-process evidence?
"""

from __future__ import annotations

# Known generative tools (lowercased substrings).
GENERATIVE_TOOLS = [
    "midjourney",
    "dall-e",
    "dall e",
    "dalle",
    "stable diffusion",
    "stablediffusion",
    "adobe firefly",
    "firefly",
    "flux",
    "comfyui",
    "automatic1111",
    "a1111",
    "leonardo.ai",
    "leonardo ai",
    "nightcafe",
    "runway",
    "sdxl",
    "novelai",
]

# Generic editing tools that must NOT by themselves imply AI generation.
NEUTRAL_TOOLS = ["photoshop", "gimp", "lightroom", "affinity", "capture one"]

_KNOWN_MIME_EXT = {
    "image/png": {"png"},
    "image/jpeg": {"jpg", "jpeg"},
    "image/webp": {"webp"},
    "image/gif": {"gif"},
    "image/tiff": {"tif", "tiff"},
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _software_fields(metadata: dict) -> str:
    parts = [
        str(metadata.get("software", "")),
        str(metadata.get("generator", "")),
        str(metadata.get("notes", "")),
        str(metadata.get("comment", "")),
    ]
    return " ".join(parts).lower()


def generation_tool_signal(metadata: dict) -> dict:
    """Signal 1: explicit generative-tool markers in the metadata."""
    haystack = _software_fields(metadata)
    matched = [tool for tool in GENERATIVE_TOOLS if tool in haystack]
    neutral_matched = [tool for tool in NEUTRAL_TOOLS if tool in haystack]

    if matched:
        score = 0.95
    elif neutral_matched:
        # Editing software is neutral evidence, not AI evidence.
        score = 0.35
    else:
        # No software field at all is mildly suspicious but far from conclusive.
        score = 0.5 if not haystack.strip() else 0.4

    return {
        "score": round(_clamp(score), 4),
        "available": True,
        "matched_tools": matched,
        "neutral_tools": neutral_matched,
    }


def metadata_consistency_signal(metadata: dict) -> dict:
    """Signal 2: internal plausibility/consistency of the metadata fields."""
    issues: list[str] = []

    width = metadata.get("width")
    height = metadata.get("height")
    for name, value in (("width", width), ("height", height)):
        if value is not None and (not isinstance(value, int) or value <= 0):
            issues.append(f"invalid {name}")

    mime = str(metadata.get("mime_type", "")).lower()
    filename = str(metadata.get("filename", "")).lower()
    if mime and filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1]
        allowed = _KNOWN_MIME_EXT.get(mime)
        if allowed is not None and ext not in allowed:
            issues.append("mime/extension mismatch")

    has_exif = metadata.get("has_exif")
    # Missing EXIF alone is only mildly suspicious (platforms strip it).
    exif_missing = has_exif is False

    # Perfectly square, EXIF-free images with no capture metadata are a common
    # generated-image shape, but this is weak evidence on its own.
    square_no_exif = (
        isinstance(width, int)
        and isinstance(height, int)
        and width == height
        and exif_missing
    )

    score = 0.35
    score += 0.15 * len(issues)
    if exif_missing:
        score += 0.10
    if square_no_exif:
        score += 0.10
    if not issues and has_exif:
        score -= 0.10

    return {
        "score": round(_clamp(score), 4),
        "available": True,
        "issues": issues,
        "exif_missing": exif_missing,
    }


def provenance_history_signal(metadata: dict) -> dict:
    """Signal 3: credible creator-process evidence lowers AI likelihood."""
    source_hash = str(metadata.get("source_hash", "")).strip()
    edit_count = metadata.get("edit_count", 0)
    attestation = bool(metadata.get("creator_attestation", False))
    revision_info = str(metadata.get("revision_info", "")).strip()

    evidence = 0
    if source_hash:
        evidence += 1
    if isinstance(edit_count, int) and edit_count > 0:
        evidence += 1
    if attestation:
        evidence += 1
    if revision_info:
        evidence += 1

    # Start neutral-uncertain; strong process evidence pulls toward human.
    # Missing evidence only nudges toward uncertainty (conservative).
    score = 0.55 - 0.12 * evidence
    return {
        "score": round(_clamp(score), 4),
        "available": True,
        "evidence_count": evidence,
        "has_attestation": attestation,
    }


def analyze(metadata: dict) -> dict:
    """Run all three image-metadata signals and return them keyed by name."""
    return {
        "generation_tool": generation_tool_signal(metadata),
        "metadata_consistency": metadata_consistency_signal(metadata),
        "provenance_history": provenance_history_signal(metadata),
    }
