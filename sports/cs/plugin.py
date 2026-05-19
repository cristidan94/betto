from __future__ import annotations

from core.plugins import GamePlugin
from sports.cs import GAME_ID
from sports.cs.features import CS_FEATURES_V1
from sports.cs.ingestion import HltvSeedAdapter, PolymarketSeedAdapter
from sports.cs.models import CS_TARGETS


def build_plugin() -> GamePlugin:
    return GamePlugin(
        game_id=GAME_ID,
        source_adapters=(HltvSeedAdapter(), PolymarketSeedAdapter()),
        feature_names=CS_FEATURES_V1,
        supported_targets=CS_TARGETS,
    )

