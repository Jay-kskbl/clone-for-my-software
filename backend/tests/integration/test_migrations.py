"""T03 🧪：迁移能在空库上升级、降级。"""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import Base

EXPECTED_TABLES = {
    "users",
    "documents",
    "document_shares",
    "tags",
    "document_tags",
    "processing_tasks",
    "document_chunks",
    "image_assets",
    "ocr_results",
    "image_embeddings",
    "search_logs",
    "experiment_runs",
}


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_upgrade_downgrade_upgrade_on_empty_database(empty_engine, alembic_config):
    command.upgrade(alembic_config, "head")
    assert _tables(empty_engine) == EXPECTED_TABLES

    command.downgrade(alembic_config, "base")
    assert _tables(empty_engine) == set()

    # 降级必须删得干净，否则这里的再次升级会因为对象已存在而失败
    command.upgrade(alembic_config, "head")
    assert _tables(empty_engine) == EXPECTED_TABLES


def test_models_declare_exactly_the_expected_tables():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_migration_matches_models(migrated_engine):
    """迁移脚本建出来的库与 models.py 一致：防止改了模型却忘了写迁移。"""
    with migrated_engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "compare_server_default": True}
        )
        assert compare_metadata(context, Base.metadata) == []


def _user_and_document(session: Session, **doc_overrides) -> models.Document:
    user = models.User(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x")
    session.add(user)
    session.flush()
    fields = dict(
        owner_id=user.id,
        filename="报告.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        sha256="a" * 64,
        storage_key=f"2026/{uuid.uuid4()}/{'a' * 64}.pdf",
    )
    fields.update(doc_overrides)
    document = models.Document(**fields)
    session.add(document)
    session.flush()
    return document


def test_defaults_are_applied(migrated_engine):
    with Session(migrated_engine) as session:
        document = _user_and_document(session)
        task = models.ProcessingTask(task_type="parse", document_id=document.id)
        session.add(task)
        session.commit()
        session.refresh(document)
        session.refresh(task)

        assert document.status == "pending"
        assert document.deleted_at is None
        assert document.created_at.tzinfo is not None
        assert (task.status, task.attempts, task.max_attempts, task.payload) == (
            "pending",
            0,
            3,
            {},
        )
        assert session.get(models.User, document.owner_id).role == "user"


@pytest.mark.parametrize(
    "make_bad_row",
    [
        lambda s, d: models.User(username="x", password_hash="x", role="root"),
        lambda s, d: models.ProcessingTask(task_type="parse", document_id=d.id, status="done"),
        lambda s, d: models.ProcessingTask(task_type="parse", document_id=d.id, max_attempts=0),
        lambda s, d: models.DocumentChunk(
            chunk_id=f"{d.id}:v1:0",
            document_id=d.id,
            parse_version="v1",
            seq=0,
            source_type="title",
            text="t",
            locator={"type": "pdf_page", "page": 1},
        ),
        lambda s, d: models.ProcessingTask(task_type="parse", document_id=uuid.uuid4()),
        lambda s, d: models.Document(
            owner_id=d.owner_id,
            filename="f",
            mime_type="m",
            size_bytes=1,
            sha256="b" * 64,
            storage_key=d.storage_key,
        ),
    ],
    ids=[
        "非法角色",
        "非法任务状态",
        "最大重试次数为0",
        "非法source_type",
        "任务指向不存在的文档",
        "storage_key重复",
    ],
)
def test_constraints_reject_bad_rows(migrated_engine, make_bad_row):
    with Session(migrated_engine) as session:
        document = _user_and_document(session)
        session.add(make_bad_row(session, document))
        with pytest.raises(IntegrityError):
            session.flush()


def test_invalid_document_status_rejected(migrated_engine):
    with Session(migrated_engine) as session:
        with pytest.raises(IntegrityError):
            _user_and_document(session, status="deleted")


def test_same_image_content_embedded_once_per_model(migrated_engine):
    def embedding(model_version: str) -> models.ImageEmbedding:
        return models.ImageEmbedding(
            sha256="c" * 64,
            model_name="chinese-clip-vit-b-16",
            model_version=model_version,
            dim=3,
            vector=[0.1, 0.2, 0.3],
        )

    with Session(migrated_engine) as session:
        session.add_all([embedding("1"), embedding("2")])  # 不同模型版本可以并存
        session.flush()
        stored = session.scalars(select(models.ImageEmbedding.vector)).first()
        assert stored == pytest.approx([0.1, 0.2, 0.3])

        session.add(embedding("1"))
        with pytest.raises(IntegrityError):
            session.flush()


def test_hard_deleting_document_removes_dependent_rows(migrated_engine):
    with Session(migrated_engine) as session:
        document = _user_and_document(session)
        other = models.User(username="sharee", password_hash="x")
        tag = models.Tag(name="财务")
        session.add_all([other, tag])
        session.flush()
        locator = {"type": "pdf_page", "page": 1}
        session.add_all(
            [
                models.ProcessingTask(task_type="parse", document_id=document.id),
                models.DocumentChunk(
                    chunk_id=f"{document.id}:v1:0",
                    document_id=document.id,
                    parse_version="v1",
                    seq=0,
                    source_type="body",
                    text="正文",
                    locator=locator,
                ),
                models.ImageAsset(
                    image_id=str(document.id), document_id=document.id, sha256="d" * 64
                ),
                models.OCRResult(
                    document_id=document.id,
                    locator=locator,
                    lines=[],
                    model_name="m",
                    model_version="1",
                ),
                models.DocumentShare(document_id=document.id, user_id=other.id),
                models.DocumentTag(document_id=document.id, tag_id=tag.id),
            ]
        )
        session.commit()

        session.delete(document)
        session.commit()

        for model in (
            models.ProcessingTask,
            models.DocumentChunk,
            models.ImageAsset,
            models.OCRResult,
            models.DocumentShare,
            models.DocumentTag,
        ):
            assert session.scalars(select(model)).all() == [], model.__tablename__
        # 标签和用户本身不受影响
        assert session.scalars(select(models.Tag)).one().name == "财务"
        assert len(session.scalars(select(models.User)).all()) == 2


def test_user_with_documents_cannot_be_deleted(migrated_engine):
    with Session(migrated_engine) as session:
        document = _user_and_document(session)
        session.commit()
        session.delete(session.get(models.User, document.owner_id))
        with pytest.raises(IntegrityError):
            session.flush()
