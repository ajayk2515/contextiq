import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.auth.models import UserRole
from app.query_intelligence.domain import QueryCategory

EVALUATION_ROOT = Path(__file__).resolve().parents[3] / "evaluation"
DATASET_PATH = EVALUATION_ROOT / "dataset.json"


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    question: str = Field(min_length=1, max_length=2000)
    expected_answer: str = Field(min_length=1)
    expected_document: str = Field(min_length=1, max_length=255)
    role: UserRole
    category_hint: QueryCategory


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    cases: list[EvaluationCase] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> "EvaluationDataset":
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Evaluation case IDs must be unique.")
        return self


def load_dataset(case_ids: list[str] | None = None) -> list[EvaluationCase]:
    dataset = EvaluationDataset.model_validate_json(DATASET_PATH.read_text(encoding="utf-8"))
    if case_ids is None:
        return dataset.cases

    selected_ids = set(case_ids)
    known_ids = {case.id for case in dataset.cases}
    unknown = sorted(selected_ids - known_ids)
    if unknown:
        raise ValueError(f"Unknown evaluation case IDs: {', '.join(unknown)}")
    return [case for case in dataset.cases if case.id in selected_ids]


def dataset_json() -> dict[str, object]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
