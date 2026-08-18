import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.auth.models import User, UserRole
from app.auth.seeding import DEMO_USERS
from app.config import Settings, get_settings
from app.database import AsyncSessionFactory
from app.evaluations.dataset import EvaluationCase, load_dataset
from app.evaluations.models import (
    Evaluation,
    EvaluationFailureCategory,
    EvaluationRun,
    EvaluationRunStatus,
)
from app.evaluations.ragas_adapter import RagasEvaluator, RagasScores
from app.rag.service import RagService

logger = logging.getLogger(__name__)
RagFactory = Callable[[Settings], RagService]
EvaluatorFactory = Callable[[Settings], RagasEvaluator]


def _safe_error(error: Exception) -> str:
    if isinstance(error, HTTPException) and isinstance(error.detail, dict):
        message = error.detail.get("message")
        if isinstance(message, str):
            return message[:1000]
    return "The evaluation case could not be completed. Check the server logs for details."


def _failure_category(error: Exception) -> EvaluationFailureCategory:
    if isinstance(error, HTTPException) and isinstance(error.detail, dict):
        code = str(error.detail.get("code", ""))
        if code == "ANSWER_GENERATION_FAILED":
            return EvaluationFailureCategory.GENERATION
        if any(part in code for part in ("RETRIEVAL", "RERANK", "EMBEDDING", "SPARSE")):
            return EvaluationFailureCategory.RETRIEVAL
    return EvaluationFailureCategory.SYSTEM


class EvaluationRunner:
    def __init__(
        self,
        settings: Settings,
        rag_factory: RagFactory = RagService,
        evaluator_factory: EvaluatorFactory = RagasEvaluator,
    ) -> None:
        self.settings = settings
        self.rag_factory = rag_factory
        self.evaluator_factory = evaluator_factory

    async def _users_by_role(self) -> dict[UserRole, User]:
        email_by_role = {demo.role: demo.email for demo in DEMO_USERS}
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(User).where(User.email.in_(email_by_role.values()))
            )
            users = result.scalars().all()
        return {UserRole(user.role): user for user in users}

    async def _persist_result(self, result: Evaluation) -> None:
        async with AsyncSessionFactory() as session:
            session.add(result)
            run = await session.get(EvaluationRun, result.run_id, with_for_update=True)
            if run is None:
                raise RuntimeError("Evaluation run disappeared while executing.")
            run.completed_cases += 1
            await session.commit()

    async def _evaluate_case(
        self,
        run_id: UUID,
        case: EvaluationCase,
        users: dict[UserRole, User],
        rag: RagService,
        evaluator: RagasEvaluator,
    ) -> Evaluation:
        result = Evaluation(
            run_id=run_id,
            evaluation_case_id=case.id,
            question=case.question,
            role=case.role.value,
            expected_answer=case.expected_answer,
            expected_document=case.expected_document,
        )
        user = users.get(case.role)
        if user is None:
            result.failure_category = EvaluationFailureCategory.AUTHORIZATION
            result.error_message = f"The {case.role.value} demo user is not seeded."
            return result

        try:
            prepared = await rag.prepare(case.question, user.id, user.role)
            result.query_id = prepared.query_intelligence.query_id
            result.insufficient_context = prepared.insufficient_context
            response = await rag.complete(prepared)
            result.generated_answer = response.answer
            if prepared.insufficient_context:
                result.failure_category = EvaluationFailureCategory.RETRIEVAL
                result.error_message = "The retrieval pipeline returned no authorized context."
                return result

            scores: RagasScores = await evaluator.evaluate(
                question=case.question,
                answer=response.answer,
                contexts=list(prepared.contexts),
                reference=case.expected_answer,
            )
            result.faithfulness = scores.faithfulness
            result.answer_relevancy = scores.answer_relevancy
            result.context_precision = scores.context_precision
            result.context_recall = scores.context_recall
            if scores.failed_metrics:
                result.failure_category = EvaluationFailureCategory.METRIC
                result.error_message = "Metrics unavailable: " + ", ".join(scores.failed_metrics)
        except Exception as error:
            logger.exception("Evaluation case %s failed", case.id)
            result.failure_category = _failure_category(error)
            result.error_message = _safe_error(error)
        return result

    async def run(self, run_id: UUID, case_ids: list[str] | None = None) -> None:
        rag: RagService | None = None
        evaluator: RagasEvaluator | None = None
        try:
            cases = load_dataset(case_ids)
            users = await self._users_by_role()
            async with AsyncSessionFactory() as session:
                run = await session.get(EvaluationRun, run_id)
                if run is None:
                    return
                run.total_cases = len(cases)
                await session.commit()

            rag = self.rag_factory(self.settings)
            evaluator = self.evaluator_factory(self.settings)
            for case in cases:
                result = await self._evaluate_case(run_id, case, users, rag, evaluator)
                await self._persist_result(result)

            async with AsyncSessionFactory() as session:
                run = await session.get(EvaluationRun, run_id)
                if run is not None:
                    run.status = EvaluationRunStatus.COMPLETED
                    run.completed_at = datetime.now(UTC)
                    await session.commit()
        except Exception:
            logger.exception("Evaluation run %s failed", run_id)
            async with AsyncSessionFactory() as session:
                run = await session.get(EvaluationRun, run_id)
                if run is not None:
                    run.status = EvaluationRunStatus.FAILED
                    run.error_message = (
                        "The evaluation run could not be completed. Check the server logs."
                    )
                    run.completed_at = datetime.now(UTC)
                    await session.commit()
        finally:
            if evaluator is not None:
                await evaluator.close()
            if rag is not None:
                await rag.close()


async def run_evaluation(run_id: UUID, case_ids: list[str] | None) -> None:
    await EvaluationRunner(get_settings()).run(run_id, case_ids)
