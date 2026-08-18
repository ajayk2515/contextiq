from statistics import fmean
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.database import get_session
from app.evaluations.dataset import load_dataset
from app.evaluations.models import Evaluation, EvaluationRun, EvaluationRunStatus
from app.evaluations.runner import run_evaluation
from app.evaluations.schemas import (
    EvaluationAverages,
    EvaluationResultResponse,
    EvaluationRunDetail,
    EvaluationRunRequest,
    EvaluationRunSummary,
)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _average(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return fmean(present) if present else None


def _averages(results: list[Evaluation]) -> EvaluationAverages:
    return EvaluationAverages(
        faithfulness=_average([result.faithfulness for result in results]),
        answer_relevancy=_average([result.answer_relevancy for result in results]),
        context_precision=_average([result.context_precision for result in results]),
        context_recall=_average([result.context_recall for result in results]),
    )


def _summary(run: EvaluationRun, results: list[Evaluation]) -> EvaluationRunSummary:
    return EvaluationRunSummary(
        id=run.id,
        status=EvaluationRunStatus(run.status),
        total_cases=run.total_cases,
        completed_cases=run.completed_cases,
        error_message=run.error_message,
        averages=_averages(results),
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


async def _results_for_run(session: AsyncSession, run_id: UUID) -> list[Evaluation]:
    result = await session.execute(
        select(Evaluation)
        .where(Evaluation.run_id == run_id)
        .order_by(Evaluation.created_at, Evaluation.evaluation_case_id)
    )
    return list(result.scalars().all())


@router.post("/run", response_model=EvaluationRunSummary, status_code=status.HTTP_202_ACCEPTED)
async def start_evaluation(
    request: EvaluationRunRequest,
    _current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvaluationRunSummary:
    try:
        cases = load_dataset(request.case_ids)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_EVALUATION_CASES", "message": str(error)},
        ) from error

    run = EvaluationRun(status=EvaluationRunStatus.RUNNING, total_cases=len(cases))
    session.add(run)
    await session.commit()
    await session.refresh(run)
    background_tasks.add_task(run_evaluation, run.id, request.case_ids)
    return _summary(run, [])


@router.get("", response_model=list[EvaluationRunSummary])
async def list_evaluations(
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EvaluationRunSummary]:
    result = await session.execute(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(50)
    )
    runs = list(result.scalars().all())
    summaries: list[EvaluationRunSummary] = []
    for run in runs:
        summaries.append(_summary(run, await _results_for_run(session, run.id)))
    return summaries


@router.get("/{run_id}", response_model=EvaluationRunDetail)
async def get_evaluation(
    run_id: UUID,
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvaluationRunDetail:
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EVALUATION_NOT_FOUND", "message": "Evaluation run not found."},
        )
    results = await _results_for_run(session, run.id)
    return EvaluationRunDetail(
        **_summary(run, results).model_dump(),
        evaluations=[
            EvaluationResultResponse.model_validate(result, from_attributes=True)
            for result in results
        ],
    )
