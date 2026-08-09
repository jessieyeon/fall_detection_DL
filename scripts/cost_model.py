# -*- coding: utf-8 -*-
"""낙상 1건 예방의 기대 비용 절감 추정 모델.

모든 파라미터는 (출처) 또는 (가정) 으로 표시한다.
계산 단위: 원.
"""
MAN = 10_000  # 만원

# ── 1. 모집단 ──────────────────────────────────────────────
POP65 = 10_240_000          # (출처) 2024.12 주민등록 65세 이상, 초고령사회 진입 시점
FALL_RATE_CLIN = 0.33       # (출처) 65세 이상 1/3 이상이 연 1회 이상 낙상 (임상 문헌)
FALL_RATE_SELF = 0.056      # (출처) 2023 노인실태조사 자기보고 낙상 경험률

falls_clin = POP65 * FALL_RATE_CLIN
falls_self = POP65 * FALL_RATE_SELF

# ── 2. 결과(outcome) 발생 건수 ────────────────────────────
HIP_FX_ALL_AGES = 41_809    # (출처) 심평원 2023 고관절 골절 환자수
SHARE_65P       = 0.80      # (가정) 연령분포로부터 추정한 65세 이상 비중
SHARE_FALL      = 0.90      # (출처) 65세 이상 고관절 골절의 90% 이상이 낙상 기인
hip_fx = HIP_FX_ALL_AGES * SHARE_65P * SHARE_FALL

FALL_HOSP_PER_100K = 2_336  # (출처) 65세 이상 낙상 입원율, 퇴원손상심층조사(2013)
FX_AMONG_HOSP      = 0.75   # (출처) 낙상 입원환자 중 골절 비중 75%
fall_hosp = POP65 * FALL_HOSP_PER_100K / 100_000
total_fx  = fall_hosp * FX_AMONG_HOSP
nonhip_fx = total_fx - hip_fx

# ── 3. 결과별 비용 ────────────────────────────────────────
CPI_2006_2024 = 1.55        # (가정) 소비자물가 기준 2006→2024 환산계수
C_HIP_2006   = 712 * MAN    # (출처) 박일형 등(2006) 고관절 골절 환자당 직접비용
C_SPINE_2006 = 637 * MAN
C_WRIST_2006 = 334 * MAN
C_HIP_ACUTE  = C_HIP_2006   * CPI_2006_2024
C_NONHIP     = (C_SPINE_2006 + C_WRIST_2006) / 2 * CPI_2006_2024  # (가정) 척추·손목 단순평균

P_LTC        = 0.137        # (출처) 고관절 골절 환자의 장기요양 인정 비율 (JKOA 2023)
LTC_MONTHLY  = 137 * MAN    # (출처) 장기요양 급여이용자 1인당 월평균 공단부담금 (2024)
LTC_MONTHS   = 36           # (가정) 평균 수급 지속기간

E_LTC_PER_HIP = P_LTC * LTC_MONTHLY * LTC_MONTHS
C_HIP_TOTAL   = C_HIP_ACUTE + E_LTC_PER_HIP

# ── 4. 낙상 1건당 기대 절감액 ─────────────────────────────
def expected_per_fall(n_falls):
    p_hip    = hip_fx / n_falls
    p_nonhip = nonhip_fx / n_falls
    return p_hip, p_nonhip, p_hip * C_HIP_TOTAL + p_nonhip * C_NONHIP

p_hip_c, p_non_c, E_clin = expected_per_fall(falls_clin)
p_hip_s, p_non_s, E_self = expected_per_fall(falls_self)

# ── 5. 시스템 실효 절감 ───────────────────────────────────
DETECT   = 0.94   # (출처) 자체 촬영 데이터 낙상 감지율 16/17
MITIGATE = 0.60   # (가정) 쿠션 전개 시 부상 저감률 — 미검증

E_eff = E_clin * DETECT * MITIGATE

def w(x): return f"{x/MAN:>10,.1f}만원"

print("=" * 62)
print("1. 모집단 및 발생 건수")
print(f"  65세 이상 인구            {POP65:>12,.0f} 명")
print(f"  연간 낙상(임상 33%)       {falls_clin:>12,.0f} 건")
print(f"  연간 낙상(자기보고 5.6%)  {falls_self:>12,.0f} 건")
print(f"  낙상 기인 고관절 골절     {hip_fx:>12,.0f} 건")
print(f"  낙상 기인 골절 전체       {total_fx:>12,.0f} 건")
print(f"  비고관절 골절             {nonhip_fx:>12,.0f} 건")
print()
print("2. 결과별 1건 비용")
print(f"  고관절 급성기(2024년가)  {w(C_HIP_ACUTE)}")
print(f"  고관절 기대 장기요양비    {w(E_LTC_PER_HIP)}")
print(f"  고관절 골절 1건 합계      {w(C_HIP_TOTAL)}")
print(f"  비고관절 골절 1건         {w(C_NONHIP)}")
print()
print("3. 낙상 1건당 기대 절감액")
print(f"  [기준안] 임상 낙상률      P(고관절)={p_hip_c:.3%}  P(기타골절)={p_non_c:.3%}  →{w(E_clin)}")
print(f"  [상한]  자기보고 낙상률   P(고관절)={p_hip_s:.3%}  P(기타골절)={p_non_s:.3%}  →{w(E_self)}")
print(f"  [실효]  감지율×저감률 반영 ({DETECT:.0%}×{MITIGATE:.0%})            →{w(E_eff)}")
print()
print("4. 민감도 — 장기요양 수급기간 / 부상 저감률")
print(f"  {'':<10}", "".join(f"{m:>4}개월  " for m in (24, 36, 60)))
for mit in (0.4, 0.6, 0.8):
    row = ""
    for months in (24, 36, 60):
        ltc = P_LTC * LTC_MONTHLY * months
        hip = C_HIP_ACUTE + ltc
        e = (p_hip_c * hip + p_non_c * C_NONHIP) * DETECT * mit
        row += f"{e/MAN:>8,.1f}만원"
    print(f"  저감률 {mit:.0%} {row}")
print()
print("5. 전국 규모")
nat = hip_fx * C_HIP_TOTAL + nonhip_fx * C_NONHIP
print(f"  65세 이상 낙상 기인 골절의 연간 총비용   {nat/1e8:>10,.0f} 억원")
print(f"    ├ 고관절 골절                          {hip_fx*C_HIP_TOTAL/1e8:>10,.0f} 억원")
print(f"    └ 비고관절 골절                        {nonhip_fx*C_NONHIP/1e8:>10,.0f} 억원")
for pen in (0.01, 0.05, 0.10):
    print(f"  보급률 {pen:>4.0%} 시 연간 절감 (실효 반영)  {nat*pen*DETECT*MITIGATE/1e8:>10,.0f} 억원")
print("=" * 62)
