"""Import every mapped table so Base.metadata is complete for Alembic and tests."""

from backend.infrastructure.database import Base
from backend.infrastructure.database.models.case import (
    CaseTemplate,
    Character,
    CharacterSecret,
    Evidence,
    EvidenceDependency,
    LieChain,
    LieRule,
    Relationship,
    Scene,
    TimelineEvent,
)
from backend.infrastructure.database.models.session import (
    Accusation,
    ActionRequest,
    Conversation,
    ConversationMessage,
    GameEventLog,
    GameSession,
    LlmAttempt,
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
    "Conversation",
    "ConversationMessage",
    "Evidence",
    "EvidenceDependency",
    "GameEventLog",
    "GameSession",
    "LieChain",
    "LieRule",
    "LlmAttempt",
    "NpcState",
    "PlayerEvidence",
    "Relationship",
    "RuleEffect",
    "Scene",
    "TimelineEvent",
    "Visitor",
]
