import numpy as np
from webservice.consulting import rules


def test_grid_scores_shape():
    hm = np.ones((30, 30), dtype=np.float32)
    scores = rules.grid_scores(hm, 3, 3)
    assert len(scores) == 3 and len(scores[0]) == 3
    assert all(abs(c - 1.0) < 1e-6 for row in scores for c in row)


def test_top_finding_points_at_hot_cell():
    hm = np.zeros((30, 30), dtype=np.float32)
    hm[0:10, 0:10] = 100.0            # 좌상단 셀만 뜨겁게
    report = rules.analyze_report(hm, rows=3, cols=3, top_n=2)
    assert report["findings"][0]["cell"] == [0, 0]
    assert report["findings"][0]["level"] == "높음"
    assert "권" in report["findings"][0]["recommendation"] or \
           report["findings"][0]["recommendation"]           # 비어있지 않은 권고문
    assert isinstance(report["summary"], str) and report["summary"]


def test_uniform_heatmap_levels_not_high_bias():
    hm = np.ones((30, 30), dtype=np.float32)
    report = rules.analyze_report(hm, rows=3, cols=3, top_n=2)
    # 모든 셀이 같으면 비율 1.0 → 높음. 그래도 findings/summary 형태는 유지.
    assert len(report["findings"]) == 2
    # evidence: 권고의 문헌 근거 설명 (docs/낙상-동선-근거.md)
    assert set(report.keys()) == {"findings", "summary", "grid", "evidence"}
