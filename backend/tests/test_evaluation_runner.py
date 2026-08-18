from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.auth.models import User, UserRole
from app.config import Settings
from app.evaluations.dataset import load_dataset
from app.evaluations.models import EvaluationFailureCategory, EvaluationRun, EvaluationRunStatus
from app.evaluations.ragas_adapter import RagasScores
from app.evaluations.runner import EvaluationRunner, _optimize_completed_run
from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    IntendedRetrievalStrategy,
    QueryCategory,
    RetrievalProfile,
)
from app.rag.schemas import ChatResponse, QueryIntelligenceMetadata
from app.rag.service import PreparedAnswer


def settings() -> Settings:
    return Settings(jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters")


def user(role: UserRole) -> User:
    return User(
        id=uuid4(), email=f"{role.value.lower()}@demo.com", password_hash="unused", role=role
    )


async def test_runner_uses_server_resolved_role_and_exact_prepared_contexts() -> None:
    case = load_dataset(["faq-annual-leave"])[0]
    query_id = uuid4()
    prepared = PreparedAnswer(
        question=case.question,
        context="formatted prompt context",
        contexts=("exact chunk one", "exact chunk two"),
        sources=[],
        insufficient_context=False,
        query_intelligence=QueryIntelligenceMetadata(
            query_id=query_id,
            category=QueryCategory.FAQ,
            profile=RetrievalProfile.FAST,
            intended_strategy=IntendedRetrievalStrategy.DENSE,
            executed_strategy=ExecutedRetrievalStrategy.DENSE,
            candidate_top_k=3,
            classification_fallback=False,
        ),
    )
    rag = SimpleNamespace(
        prepare=AsyncMock(return_value=prepared),
        complete=AsyncMock(
            return_value=ChatResponse(
                answer="Twenty days.",
                sources=[],
                insufficient_context=False,
                query_intelligence=prepared.query_intelligence,
            )
        ),
    )
    evaluator = SimpleNamespace(evaluate=AsyncMock(return_value=RagasScores(0.9, 0.8, 0.7, 0.6)))
    current_user = user(UserRole.DEVELOPER)
    runner = EvaluationRunner(settings())

    result = await runner._evaluate_case(
        uuid4(), case, {UserRole.DEVELOPER: current_user}, rag, evaluator
    )

    rag.prepare.assert_awaited_once_with(case.question, current_user.id, UserRole.DEVELOPER)
    rag.complete.assert_awaited_once_with(prepared)
    evaluator.evaluate.assert_awaited_once_with(
        question=case.question,
        answer="Twenty days.",
        contexts=["exact chunk one", "exact chunk two"],
        reference=case.expected_answer,
    )
    assert result.query_id == query_id
    assert result.faithfulness == 0.9
    assert result.failure_category is None


async def test_runner_records_partial_metric_failure_without_losing_scores() -> None:
    case = load_dataset(["faq-annual-leave"])[0]
    metadata = SimpleNamespace(query_id=uuid4())
    prepared = SimpleNamespace(
        query_intelligence=metadata,
        insufficient_context=False,
        contexts=("context",),
    )
    rag = SimpleNamespace(
        prepare=AsyncMock(return_value=prepared),
        complete=AsyncMock(return_value=SimpleNamespace(answer="Answer")),
    )
    evaluator = SimpleNamespace(
        evaluate=AsyncMock(return_value=RagasScores(0.9, None, 0.7, 0.6, ("answer_relevancy",)))
    )

    result = await EvaluationRunner(settings())._evaluate_case(
        uuid4(), case, {UserRole.DEVELOPER: user(UserRole.DEVELOPER)}, rag, evaluator
    )

    assert result.answer_relevancy is None
    assert result.faithfulness == 0.9
    assert result.failure_category == EvaluationFailureCategory.METRIC
    assert result.error_message == "Metrics unavailable: answer_relevancy"


async def test_runner_rejects_missing_demo_role_without_running_rag() -> None:
    case = load_dataset(["restricted-retention-bonus"])[0]
    rag = SimpleNamespace(prepare=AsyncMock(), complete=AsyncMock())
    evaluator = SimpleNamespace(evaluate=AsyncMock())

    result = await EvaluationRunner(settings())._evaluate_case(uuid4(), case, {}, rag, evaluator)

    assert result.failure_category == EvaluationFailureCategory.AUTHORIZATION
    rag.prepare.assert_not_awaited()
    evaluator.evaluate.assert_not_awaited()


async def test_evaluation_completion_marks_run_before_triggering_optimizer() -> None:
    run = EvaluationRun(
        id=uuid4(), status=EvaluationRunStatus.RUNNING, total_cases=1, completed_cases=1
    )
    session = MagicMock()
    session.get = AsyncMock(return_value=run)
    session.commit = AsyncMock()

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    with (
        patch("app.evaluations.runner.AsyncSessionFactory", return_value=SessionContext()),
        patch("app.evaluations.runner._optimize_completed_run", new=AsyncMock()) as optimize,
    ):
        await EvaluationRunner(settings())._complete_run(run.id)

    assert run.status == EvaluationRunStatus.COMPLETED
    assert run.completed_at is not None
    session.commit.assert_awaited_once()
    optimize.assert_awaited_once_with(run.id)


async def test_optimizer_failure_does_not_propagate_to_completed_evaluation() -> None:
    run_id = uuid4()
    with patch(
        "app.evaluations.runner.generate_recommendations",
        new=AsyncMock(side_effect=RuntimeError("optimization unavailable")),
    ):
        await _optimize_completed_run(run_id)
