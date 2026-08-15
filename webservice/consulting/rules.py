"""동선(통행량) 지도 → 낙상 위험 소견·권고. 순수 함수, 규칙 기반.

## 왜 '체류'가 아니라 '동선'인가

초기 구현은 히트맵이 '어디에 오래 머무는가'를 재고, 그 체류 시간을 위험도로
번역했다. 그런데 오래 앉아 있는 자리(소파, 식탁)는 낙상이 잘 일어나는 자리가
아니다. 낙상은 **걷고 있을 때, 방향을 바꿀 때, 문턱을 넘을 때** 일어난다.

그래서 판정 기준을 '자주 지나다니는 동선'으로 바꿨다. 같은 경로를 자주 지날수록
그 경로 위의 위험 요소(문턱·전선·미끄러운 바닥·어두운 구간)에 노출되는 횟수가
누적된다. 통행량이 많은 구역을 먼저 손보는 것이 개선 효과가 크다는 논리다.

입력 지도는 `heatmap.accumulate_passage_map` 이 만든다. 제자리에 머문 구간은
이미 걷어낸 상태이므로, 여기서는 '값이 크다 = 자주 지나간다' 로 읽으면 된다.

임계값(0.66/0.33)은 물리 상수가 아니라 연출값이므로 실제 영상의 통행량 분포로
조정한다. 문헌 근거에 맞춘 기준 재설정은 WORK_PLAN.md 작업 E 참고.
"""

_ROW_LABEL = {0: "안쪽", 1: "중앙", 2: "출입구 쪽"}
_COL_LABEL = {0: "좌측", 1: "중앙", 2: "우측"}

_RECOMMEND = {
    "높음": "{zone} 구역을 가장 자주 지나다닙니다. 낙상 충격을 완화하는 "
            "DA:ON 안전 타일을 이 경로에 우선 설치하는 것을 권장합니다. "
            "바닥의 전선·문턱·러그 같은 걸림 요소 제거도 함께해 주세요.",
    "보통": "{zone} 구역에서도 이동이 관찰됩니다. 미끄러운 바닥재와 문턱 높이를 "
            "점검하고, DA:ON 안전 타일 추가 설치를 검토해 보세요.",
    "낮음": "{zone} 구역은 통행이 드물어 즉각적인 조치는 필요하지 않습니다.",
}

# 판정 근거 — '우리 알고리즘이 어떻게 분석하는지'를 비전문가 눈높이로 설명한다.
# 촬영 위치가 리포트마다 다르므로 특정 공간(공용 라운지·복도 등) 통계는 넣지 않는다.
# 세대 내부를 찍은 리포트에 '복도' 이야기가 나오면 오히려 신뢰를 깎는다.
EVIDENCE_NOTE = (
    "AI가 걸어 다닌 길을 따라가며 자주 지나는 구역을 찾고, 몸을 돌리는 지점은 "
    "넘어질 위험이 커서(연구상 골절 위험 약 8배) 더 위험하게 봅니다. "
    "이렇게 자주 다니는 곳부터 고치면 낙상이 38% 줄어든다는 연구 결과가 있습니다"
    "(Cochrane 문헌고찰)."
)


def grid_scores(passage_map, rows, cols):
    """통행량 지도를 rows×cols 격자로 접어 셀별 평균 통행량을 낸다."""
    h, w = passage_map.shape
    ch, cw = h // rows, w // cols
    scores = []
    for r in range(rows):
        row = []
        for c in range(cols):
            cell = passage_map[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
            row.append(float(cell.mean()) if cell.size else 0.0)
        scores.append(row)
    return scores


def _zone_label(r, c, rows, cols):
    # 3행/3열 기준 라벨. 다른 격자면 인덱스를 3구간으로 접어 근사한다.
    rl = _ROW_LABEL[min(r * 3 // max(rows, 1), 2)]
    cl = _COL_LABEL[min(c * 3 // max(cols, 1), 2)]
    if rl == "중앙" and cl == "중앙":
        return "중앙"
    return f"{rl} {cl}"


def _level(ratio):
    """가장 통행량이 많은 구역 대비 비율 → 3단계 등급.

    **0.66 / 0.33 이라는 경계값 자체에는 문헌 근거가 없다.** 문헌이 지지하는 것은
    '통행량 순으로 우선순위를 매기는 것'(§근거 1)과 '회전 지점에 더 큰 비중을
    두는 것'(§근거 2)이지 특정 숫자가 아니다. 이 경계는 사용자가 어느 구역부터
    볼지 정하도록 돕는 **표시 규약**이며, 임상적 절단점이 아니다.
    근거 논의는 docs/낙상-동선-근거.md 참고.
    """
    return "높음" if ratio >= 0.66 else "보통" if ratio >= 0.33 else "낮음"


def analyze_report(passage_map, rows=3, cols=3, top_n=2):
    scores = grid_scores(passage_map, rows, cols)
    flat = [(scores[r][c], r, c) for r in range(rows) for c in range(cols)]
    mx = max((s for s, _, _ in flat), default=0.0) or 1.0
    flat.sort(key=lambda t: t[0], reverse=True)

    findings = []
    for score, r, c in flat[:top_n]:
        level = _level(score / mx)
        zone = _zone_label(r, c, rows, cols)
        findings.append({
            "zone": zone, "cell": [r, c], "score": round(score, 2),
            "level": level,
            "recommendation": _RECOMMEND[level].format(zone=zone),
        })

    if findings:
        top = findings[0]
        summary = (f"분석 결과 '{top['zone']}' 구역이 가장 자주 지나다니는 "
                   f"동선으로 확인됐으며, 낙상 위험도는 '{top['level']}'입니다. "
                   f"아래 권고사항을 확인하세요.")
    else:
        summary = "분석할 이동이 감지되지 않았습니다."
    return {"findings": findings, "summary": summary, "grid": scores,
            "evidence": EVIDENCE_NOTE}
