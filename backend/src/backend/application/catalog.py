"""Offline case import and read-only access to published definitions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from backend.application.case import content_hash, load_case, validate_case
from backend.domain.models import Case
from backend.domain.rules import RULE_EXECUTION_VERSION
from backend.infrastructure.database.models import CaseTemplate
from backend.infrastructure.database.repositories.case_repository import CaseRepository


class CaseIntegrityError(RuntimeError):
    """A stored definition no longer matches its published identity."""


def is_supported(template: CaseTemplate) -> bool:
    """Whether this server can run the version; older ones stay stored but are not offered."""
    return template.rule_execution_version == RULE_EXECUTION_VERSION


@dataclass(frozen=True)
class ImportResult:
    template_id: str
    case_id: str
    version: str
    content_hash: str
    created: bool


def import_case(sessions: sessionmaker[Session], path: Path) -> ImportResult:
    """Validate a reviewed case file and publish it as an immutable version, in one transaction."""
    case = load_case(path)
    digest = content_hash(case)
    now = datetime.now(UTC)
    with sessions() as db, db.begin():
        repository = CaseRepository(db)
        existing = repository.find(case.case_id, case.version)
        # The draft below is published in this transaction, so a stored version is never a draft.
        if existing is not None:
            if existing.content_hash != digest:
                raise ValueError(
                    f"{case.case_id} {case.version} 已发布且内容不同；修订请使用新的版本号。"
                )
            return ImportResult(
                str(existing.template_id), case.case_id, case.version, digest, False
            )
        template = repository.insert_draft(case, RULE_EXECUTION_VERSION, now)
        # Publishing checks that the tables reproduce exactly the reviewed definition.
        if content_hash(repository.load_case(template)) != digest:
            raise ValueError("导入后的数据库定义与案件文件不一致。")
        template.status = "PUBLISHED"
        template.content_hash = digest
        template.published_at = now
        return ImportResult(str(template.template_id), case.case_id, case.version, digest, True)


class CaseCatalog:
    """Caches immutable published definitions by template and content hash."""

    def __init__(self):
        self._cache: dict[tuple, Case] = {}

    def load(self, db: Session, template: CaseTemplate) -> Case:
        key = (template.template_id, template.content_hash)
        if key not in self._cache:
            if template.status == "DRAFT" or not is_supported(template):
                raise CaseIntegrityError("案件版本未发布或规则执行版本不受支持。")
            case = CaseRepository(db).load_case(template)
            validate_case(case)
            if content_hash(case) != template.content_hash:
                raise CaseIntegrityError("案件定义与发布摘要不一致。")
            self._cache[key] = case
        return self._cache[key]
