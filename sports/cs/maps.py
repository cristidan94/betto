from __future__ import annotations

ACTIVE_DUTY_MAPS: tuple[str, ...] = (
    "Ancient",
    "Anubis",
    "Dust2",
    "Inferno",
    "Mirage",
    "Nuke",
    "Cache",
    "Cobblestone",
    "Overpass",
    "Train",
    "Vertigo",
)


def normalize_map_name(value: str) -> str:
    cleaned = value.strip().lower().replace("_", " ").replace("-", " ")
    aliases = {
        "de ancient": "Ancient",
        "ancient": "Ancient",
        "de anubis": "Anubis",
        "anubis": "Anubis",
        "de dust2": "Dust2",
        "dust 2": "Dust2",
        "dust2": "Dust2",
        "de inferno": "Inferno",
        "inferno": "Inferno",
        "de mirage": "Mirage",
        "mirage": "Mirage",
        "de nuke": "Nuke",
        "nuke": "Nuke",
        "de cache": "Cache",
        "cache": "Cache",
        "de cbble": "Cobblestone",
        "de cobblestone": "Cobblestone",
        "cobblestone": "Cobblestone",
        "de overpass": "Overpass",
        "overpass": "Overpass",
        "de train": "Train",
        "train": "Train",
        "de vertigo": "Vertigo",
        "vertigo": "Vertigo",
    }
    if cleaned not in aliases:
        raise ValueError(f"unknown CS map: {value}")
    return aliases[cleaned]
