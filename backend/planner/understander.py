"""Query intent classification and mode extraction with Mission Mode support."""

from __future__ import annotations

import re


CAPTION_PATTERNS = [
    r"\bcaption\b",
    r"\bdescribe\b",
    r"\bwhat does this (image|scene|area) (show|contain|look like)\b",
    r"\boverview\b",
    r"\bsummarize\b",
]

GROUNDING_PATTERNS = [
    r"\blocate\b",
    r"\bfind\b",
    r"\bwhere (is|are)\b",
    r"\bgrounding\b",
    r"\bhighlight\b",
    r"\bdetect\b",
    r"\bbounding box\b",
]

CHANGE_PATTERNS = [
    r"\bchange\b",
    r"\bdifference\b",
    r"\bbefore and after\b",
    r"\btemporal\b",
    r"\bincreased\b",
    r"\bdecreased\b",
    r"\bwhat changed\b",
    r"\bexpansion\b",
    r"\bloss\b",
    r"\bgrowth\b",
    r"\bdeforestation\b",
]

FUSION_PATTERNS = [
    r"\bsar\b",
    r"\boptical\b",
    r"\bfusion\b",
    r"\bcross.?modal\b",
    r"\brisat\b",
    r"\bcartosat\b",
    r"\bsentinel\b",
    r"\bjoint\b",
    r"\bcomplementary\b",
]

MISSION_PATTERNS = [
    r"\bmission\b",
    r"\banalyze this region for\b",
    r"\bcomprehensive assessment\b",
    r"\bfull analysis\b",
    r"\burban expansion assessment\b",
    r"\bdeforestation assessment\b",
]


def classify_query(query: str, detected_mode: str, image_count: int) -> str:
    q = query.lower().strip()

    # Check Mission Mode
    if any(re.search(p, q) for p in MISSION_PATTERNS) or q.startswith("analyze this region for"):
        return "mission_mode"

    if detected_mode == "cross_modal_pair" or (image_count == 2 and any(re.search(p, q) for p in FUSION_PATTERNS)):
        return "fusion"

    if detected_mode in {"bi_temporal", "change_vqa"} or image_count == 2:
        if any(re.search(p, q) for p in CHANGE_PATTERNS):
            if "?" in query or any(w in q for w in ["has", "did", "is there", "how much", "what"]):
                return "change_vqa"
            return "change_detection"
        if image_count == 2:
            return "change_vqa"

    # Explicit Grounding commands take priority over description
    if q.startswith("locate") or q.startswith("find") or q.startswith("highlight") or q.startswith("detect"):
        return "grounding"

    # Compound queries: "describe image and locate vegetation"
    if ("describe" in q or "caption" in q) and any(re.search(p, q) for p in GROUNDING_PATTERNS):
        return "compound_vqa_grounding"

    if any(re.search(p, q) for p in GROUNDING_PATTERNS):
        return "grounding"

    if any(re.search(p, q) for p in CAPTION_PATTERNS):
        return "caption"

    return "vqa"
