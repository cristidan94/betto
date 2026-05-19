from __future__ import annotations

import re


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-")


def cs_participant_id(source: str, source_id: str) -> str:
    return f"cs:participant:{source}:{slugify(source_id)}"


def cs_contest_id(source: str, source_id: str) -> str:
    return f"cs:contest:{source}:{slugify(source_id)}"

