"""낙상 위험 자가진단 설문 로드와 채점. 순수 함수, DB·웹 의존 없음."""

import json
import os

_QUESTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "data", "questions.json")


def load_questions(path=None):
    with open(path or _QUESTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def score_answers(answers, questions=None):
    q = questions or load_questions()
    total = 0
    for question in q["questions"]:
        qid = question["id"]
        if qid not in answers:
            raise ValueError(f"미응답 문항: {qid}")
        idx = answers[qid]
        opts = question["options"]
        if not isinstance(idx, int) or idx < 0 or idx >= len(opts):
            raise ValueError(f"잘못된 응답: {qid}={idx!r}")
        total += opts[idx]["points"]
    t = q["thresholds"]
    level = "높음" if total >= t["high"] else "보통" if total >= t["medium"] else "낮음"
    return total, level
