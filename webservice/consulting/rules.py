"""체류/이동 히트맵 → 낙상 위험 소견·권고. 순수 함수, 규칙 기반.

히트맵이 '어디에 오래 머무는가'만 알므로, 그 체류 패턴을 낙상 위험 해석으로
번역하는 규칙 한 겹을 여기 둔다. 임계값(0.66/0.33)은 물리 상수가 아니라
연출값이므로 리허설 히트맵으로 조정한다.
"""

_ROW_LABEL = {0: "안쪽", 1: "중앙", 2: "출입구 쪽"}
_COL_LABEL = {0: "좌측", 1: "중앙", 2: "우측"}

_RECOMMEND = {
    "높음": "{zone} 구역에 머무는 시간이 가장 깁니다. 미끄럼 방지 매트와 "
            "손잡이(그랩바) 설치, 야간 조명 보강을 권장합니다.",
    "보통": "{zone} 구역 이동이 잦습니다. 바닥의 전선·문턱 등 걸림 요소를 "
            "제거하세요.",
    "낮음": "{zone} 구역은 활동이 적어 즉각적인 조치는 필요하지 않습니다.",
}


def grid_scores(heatmap, rows, cols):
    h, w = heatmap.shape
    ch, cw = h // rows, w // cols
    scores = []
    for r in range(rows):
        row = []
        for c in range(cols):
            cell = heatmap[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
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
    return "높음" if ratio >= 0.66 else "보통" if ratio >= 0.33 else "낮음"


def analyze_report(heatmap, rows=3, cols=3, top_n=2):
    scores = grid_scores(heatmap, rows, cols)
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
        summary = (f"분석 결과 '{top['zone']}' 구역에서 체류가 가장 두드러졌으며 "
                   f"낙상 위험도는 '{top['level']}'입니다. 아래 권고사항을 확인하세요.")
    else:
        summary = "분석할 활동이 감지되지 않았습니다."
    return {"findings": findings, "summary": summary, "grid": scores}
