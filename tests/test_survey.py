import pytest
from webservice import survey


def test_load_questions_shape():
    q = survey.load_questions()
    assert len(q["questions"]) == 8
    assert q["thresholds"] == {"medium": 5, "high": 10}


def _all(idx):
    return {qq["id"]: idx for qq in survey.load_questions()["questions"]}


def test_score_min_is_low():
    assert survey.score_answers(_all(0)) == (0, "낮음")


def test_score_max_is_high():
    score, level = survey.score_answers({
        "age": 3, "past_fall": 2, "meds": 1, "dizzy": 2,
        "aid": 1, "night_toilet": 2, "balance": 2, "vision": 1})
    assert score == 19 and level == "높음"


def test_score_medium_band():
    # age=2, past_fall=1(2점) → 4? 필요 5. dizzy=1(1점) 추가 → 5 → 보통
    ans = _all(0)
    ans.update({"age": 2, "past_fall": 1, "dizzy": 1})
    score, level = survey.score_answers(ans)
    assert score == 5 and level == "보통"


def test_missing_question_raises():
    with pytest.raises(ValueError):
        survey.score_answers({"age": 0})


def test_bad_index_raises():
    ans = _all(0)
    ans["age"] = 9
    with pytest.raises(ValueError):
        survey.score_answers(ans)
