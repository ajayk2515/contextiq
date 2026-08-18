from app.auth.models import UserRole
from app.evaluations.dataset import EVALUATION_ROOT, load_dataset
from app.query_intelligence.domain import QueryCategory


def test_checked_in_dataset_has_target_size_valid_cases_and_real_documents() -> None:
    cases = load_dataset()

    assert 20 <= len(cases) <= 30
    assert len({case.id for case in cases}) == len(cases)
    assert {case.role for case in cases} == set(UserRole)
    categories = [case.category_hint for case in cases]
    assert set(categories) == set(QueryCategory)
    assert categories.count(QueryCategory.MULTI_DOC_COMPARISON) >= 3
    assert categories.count(QueryCategory.SUMMARIZATION) >= 2
    assert all((EVALUATION_ROOT / "documents" / case.expected_document).is_file() for case in cases)


def test_case_selection_preserves_dataset_order_and_rejects_unknown_ids() -> None:
    selected = load_dataset(["summary-strategy", "faq-annual-leave"])

    assert [case.id for case in selected] == ["faq-annual-leave", "summary-strategy"]

    try:
        load_dataset(["not-a-real-case"])
    except ValueError as error:
        assert "not-a-real-case" in str(error)
    else:
        raise AssertionError("Unknown case IDs must be rejected.")
