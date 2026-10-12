"""Import every mapped table so Base.metadata is complete for Alembic and tests."""

from backend.infrastructure.database import Base
from backend.infrastructure.database.models.case import (
    CaseTemplate,
    Character,
    CharacterSecret,
    Evidence,
    EvidenceDependency,
    LieRule,
    Scene,
)
from backend.infrastructure.database.models.session import (
    Accusation,
    ActionRequest,
    GameEventLog,
    GameSession,
    NpcState,
    PlayerEvidence,
    RuleEffect,
    Visitor,
)

__all__ = [
    "Accusation",
    "ActionRequest",
    "Base",
    "CaseTemplate",
    "Character",
    "CharacterSecret",
    "Evidence",
    "EvidenceDependency",
    "GameEventLog",
    "GameSession",
    "LieRule",
    "NpcState",
    "PlayerEvidence",
    "RuleEffect",
    "Scene",
    "Visitor",
]
