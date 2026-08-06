"""v5: 도메인 불변(상대) 특징 추가.
DAFD(IEEE TNSRE'21)의 domain-adaptive 아이디어를 배포 가능한 형태로 구현:
적대적 학습 대신, 각 영상의 '자기 자신 기준선'(인과적 장기 EWMA)에서의 편차를 쓴다.
카메라 높이·거리·화각이 달라도 '이 사람의 평소 자세 대비 얼마나 벗어났나'는 보존된다."""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0,"/tmp")
import numpy as np, pandas as pd
import train_v4 as v4

REL = ["tilt3d_deg","aspect_ratio","shoulder_y","tilt_angle_deg"]
LONG_ALPHA = 0.02          # ~2초 지평의 장기 기준선 (25fps 기준)

def add_relative(df):
    out=[]
    for _,g in df.groupby("video_id",sort=False):
        g=g.sort_values("frame").copy()
        for c in REL:
            base=g[c].ewm(alpha=LONG_ALPHA).mean()      # 인과적: 과거만 사용
            g[f"{c}_rel"]=g[c]-base
        out.append(g)
    return pd.concat(out)

if __name__=="__main__":
    d=pd.read_csv("/tmp/features_v4.csv"); d["video_id"]=d["dataset"]+"/"+d["video"]
    d=add_relative(d)
    d.to_pickle("/tmp/features_v5.pkl")
    print("v5 base cols:", [c for c in d.columns if c.endswith("_rel")])
    print("rows", len(d))
