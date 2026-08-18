import asyncio
import hashlib
import shutil
import tempfile
from dataclasses import dataclass

from sqlalchemy import select

from app.auth.models import User, UserRole
from app.auth.seeding import seed_demo_users
from app.config import Settings
from app.database import AsyncSessionFactory
from app.documents.models import Document, DocumentStatus
from app.evaluations.dataset import EVALUATION_ROOT
from app.ingestion.service import process_document


@dataclass(frozen=True)
class EvaluationDocument:
    filename: str
    allowed_roles: tuple[UserRole, ...]


EVALUATION_DOCUMENTS = (
    EvaluationDocument("evaluation-employee-handbook.md", tuple(UserRole)),
    EvaluationDocument("evaluation-engineering-guide.md", (UserRole.DEVELOPER, UserRole.EXECUTIVE)),
    EvaluationDocument("evaluation-finance-policy.md", (UserRole.FINANCE, UserRole.EXECUTIVE)),
    EvaluationDocument("evaluation-hr-confidential.md", (UserRole.HR, UserRole.EXECUTIVE)),
    EvaluationDocument("evaluation-executive-strategy.md", (UserRole.EXECUTIVE,)),
)


async def seed_evaluation_data(settings: Settings) -> tuple[int, int]:
    if settings.demo_user_password is None:
        raise RuntimeError("DEMO_USER_PASSWORD must be configured before seeding evaluation data.")

    async with AsyncSessionFactory() as session:
        await seed_demo_users(session, settings.demo_user_password.get_secret_value())
        user_result = await session.execute(select(User).where(User.email == "executive@demo.com"))
        uploader = user_result.scalar_one()

    seeded = 0
    unchanged = 0
    for item in EVALUATION_DOCUMENTS:
        source = EVALUATION_ROOT / "documents" / item.filename
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        roles = [role.value for role in item.allowed_roles]
        async with AsyncSessionFactory() as session:
            document_result = await session.execute(
                select(Document).where(Document.filename == item.filename)
            )
            document = document_result.scalar_one_or_none()
            if (
                document is not None
                and document.file_hash == content_hash
                and document.allowed_roles == roles
                and document.status == DocumentStatus.READY
            ):
                unchanged += 1
                continue
            if document is None:
                document = Document(
                    filename=item.filename,
                    file_hash=content_hash,
                    status=DocumentStatus.PROCESSING,
                    uploaded_by=uploader.id,
                    allowed_roles=roles,
                )
                session.add(document)
            else:
                document.file_hash = content_hash
                document.status = DocumentStatus.PROCESSING
                document.uploaded_by = uploader.id
                document.allowed_roles = roles
                document.chunk_count = 0
                document.error_message = None
            await session.commit()
            await session.refresh(document)
            document_id = document.id

        with tempfile.NamedTemporaryFile(prefix="ekip_eval_", suffix=".md", delete=False) as target:
            temporary_path = target.name
        await asyncio.to_thread(shutil.copyfile, source, temporary_path)
        await process_document(document_id, temporary_path)

        async with AsyncSessionFactory() as session:
            ingested = await session.get(Document, document_id)
            if ingested is None or ingested.status != DocumentStatus.READY:
                message = ingested.error_message if ingested is not None else "record missing"
                raise RuntimeError(
                    f"Evaluation document {item.filename} failed ingestion: {message}"
                )
        seeded += 1
    return seeded, unchanged
