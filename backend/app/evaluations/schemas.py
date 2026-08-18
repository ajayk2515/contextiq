from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.models import UserRole
from app.evaluations.models import EvaluationFailureCategory, EvaluationRunStatus


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_ids: list[str] | None = Field(default=None, min_length=1, max_length=30)

    @field_validator("case_ids")
    @classmethod
    def require_unique_case_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Evaluation case IDs must be unique.")
        return value


class EvaluationAverages(BaseModel):
    faithfulness: float | None
    answer_relevancy: float | None
    context_precision: float | None
    context_recall: float | None


class EvaluationRunSummary(BaseModel):
    id: UUID
    status: EvaluationRunStatus
    total_cases: int
    completed_cases: int
    error_message: str | None
    averages: EvaluationAverages
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


class EvaluationResultResponse(BaseModel):
    id: UUID
    evaluation_case_id: str
    query_id: UUID | None
    question: str
    role: UserRole
    expected_answer: str
    expected_document: str
    generated_answer: str | None
    faithfulness: float | None
    answer_relevancy: float | None
    context_precision: float | None
    context_recall: float | None
    failure_category: EvaluationFailureCategory | None
    error_message: str | None
    insufficient_context: bool
    created_at: datetime


class EvaluationRunDetail(EvaluationRunSummary):
    evaluations: list[EvaluationResultResponse]
