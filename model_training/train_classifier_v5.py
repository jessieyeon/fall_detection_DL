import sys, warnings, json
warnings.filterwarnings("ignore")
sys.path.insert(0,"/tmp")
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupShuffleSplit
import train_v4 as v4

BASE_V5 = v4.BASE + ["tilt3d_deg_rel","aspect_ratio_rel","shoulder_y_rel","tilt_angle_deg_rel"]

def add_temporal_v5(df):
    """v4와 동일하되 rel 특징에도 윈도우 통계를 적용"""
    ROLL = BASE_V5 + ["speed_mag"]
    out=[]
    for _,g in df.groupby("video_id",sort=False):
        g=g.sort_values("frame").copy()
        g["speed_mag"]=np.hypot(g["vertical_velocity"],g["horizontal_velocity"])
        g["vert_accel"]=g["vertical_velocity"].diff().fillna(0)*v4.FPS_T
        g["tilt_accel"]=g["tilt_angular_velocity"].diff().fillna(0)*v4.FPS_T
        g["tilt3d_vel"]=g["tilt3d_deg"].diff().fillna(0)*v4.FPS_T
        g["aspect_vel"]=g["aspect_ratio"].diff().fillna(0)*v4.FPS_T
        g["shoulder_vel"]=g["shoulder_y"].diff().fillna(0)*v4.FPS_T
        for w in v4.WINDOWS:
            for c in ROLL:
                r=g[c].rolling(w,min_periods=1)
                g[f"{c}_m{w}"]=r.mean(); g[f"{c}_s{w}"]=r.std().fillna(0)
                g[f"{c}_r{w}"]=r.max()-r.min()
        for c in ("tilt_angle_deg","vertical_velocity","tilt3d_deg","aspect_ratio","shoulder_y",
                  "tilt3d_deg_rel","aspect_ratio_rel"):
            g[f"{c}_slope"]=(g[c]-g[c].shift(v4.SLOPE_LAG)).fillna(0)/(v4.SLOPE_LAG/v4.FPS_T)
        for c in BASE_V5:
            g[f"{c}_ewma"]=g[c].ewm(alpha=v4.EWMA_ALPHA).mean()
        out.append(g)
    return pd.concat(out)

def augment(g,kind):
    g=g.sort_values("frame").reset_index(drop=True)
    if kind=="mirror":
        a=g.copy(); a["horizontal_velocity"]=-a["horizontal_velocity"]
    else:
        s=float(kind); n=max(int(len(g)/s),15)
        pos=np.linspace(0,len(g)-1,n)
        a=pd.DataFrame({c:np.interp(pos,np.arange(len(g)),g[c].values) for c in BASE_V5})
        for c in ("vertical_velocity","horizontal_velocity","tilt_angular_velocity"): a[c]*=s
        a["label"]=g["label"].values[np.round(pos).astype(int)]
        a["frame"]=np.arange(1,n+1); a["dataset"]=g["dataset"].iloc[0]; a["video"]=g["video"].iloc[0]
    a["video_id"]=g["video_id"].iloc[0]+f"#{kind}"
    return a

def build_aug(tr):
    parts=[tr]
    for _,g in tr.groupby("video_id",sort=False):
        parts.append(augment(g,"mirror"))
        for s in v4.SPEED_FACTORS: parts.append(augment(g,s))
    return pd.concat(parts,ignore_index=True)

if __name__=="__main__":
    mode=sys.argv[1]  # "A" = rel features, "AB" = rel + MCF pseudo-label
    d=pd.read_pickle("/tmp/features_v5.pkl")
    le2i=d[d.dataset=="LE2I"]; urfd=d[d.dataset=="URFD"]; own=d[d.dataset=="OWN"].copy()
    own["person"]=own["video"].str.extract(r"_(p\d)_")[0]
    mcf=d[d.dataset=="MCF"].copy(); mcf["scen"]=mcf["video"].str.split("_").str[0]
    gss=GroupShuffleSplit(n_splits=1,test_size=0.25,random_state=42)
    i,j=next(gss.split(le2i,groups=le2i["video_id"]))
    le2i_tr,le2i_te=le2i.iloc[i],le2i.iloc[j]
    useq=sorted(urfd["video"].unique())
    ut=set(np.random.RandomState(42).choice(useq,size=len(useq)//4,replace=False))
    urfd_tr,urfd_te=urfd[~urfd["video"].isin(ut)],urfd[urfd["video"].isin(ut)]
    scen=sorted(mcf["scen"].unique())
    mt=set(np.random.RandomState(42).choice(scen,size=len(scen)//4,replace=False))
    mcf_tr=mcf[~mcf["scen"].isin(mt)]; mcf_te=mcf[mcf["scen"].isin(mt)]

    results={}
    for test_p in (sys.argv[2],) if len(sys.argv)>2 else ("p1","p2"):
        own_tr=own[own.person!=test_p].drop(columns=["person"])
        own_te=own[own.person==test_p].drop(columns=["person"])
        own3=pd.concat([own_tr.assign(video_id=own_tr.video_id+f"~{k}") for k in range(3)])
        parts=[le2i_tr,urfd_tr,own3]
        raw=build_aug(pd.concat(parts,ignore_index=True))
        f=add_temporal_v5(raw)
        feats=[c for c in f.columns if c not in ("dataset","video","frame","label","video_id","person","scen")]
        clf=HistGradientBoostingClassifier(max_iter=400,max_depth=6,learning_rate=0.08,
                                           class_weight="balanced",random_state=42)
        clf.fit(f[feats],f["label"])

        if mode=="AB":
            # RGB2Depth(IEEE Sensors'23)의 pseudo-label 아이디어: 라벨 노이즈가 큰 MCF를
            # 모델 확신도로 정제해서 학습에 재투입 (원 라벨과 합치할 때만 채택)
            mt_f=add_temporal_v5(mcf_tr.copy()).copy()
            pr=clf.predict_proba(mt_f[feats])[:,1]
            keep=((pr>=0.6)&(mt_f["label"]==1))|((pr<=0.05)&(mt_f["label"]==0))
            ps=mt_f[keep].copy()
            print(f"  pseudo-label 채택 {len(ps)}/{len(mt_f)} (pos {int(ps.label.sum())})",flush=True)
            f2=pd.concat([f,ps[f.columns.intersection(ps.columns)]],ignore_index=True)
            clf=HistGradientBoostingClassifier(max_iter=400,max_depth=6,learning_rate=0.08,
                                               class_weight="balanced",random_state=42)
            clf.fit(f2[feats],f2["label"])

        t=add_temporal_v5(own_te.copy()).copy()
        t["proba"]=clf.predict_proba(t[feats])[:,1]; t["proba_sm"]=v4.smooth_proba(t,"proba")
        t.to_pickle(f"/tmp/v5{mode}_own_{test_p}.pkl")
        joblib.dump({"model":clf,"features":feats},f"/tmp/v5{mode}_{test_p}.joblib")
        print(f"trained {mode} test={test_p}",flush=True)
    # 공개 홀드아웃은 p2 모델로
    b=joblib.load(f"/tmp/v5{mode}_p2.joblib")
    for nm,te in [("Le2i",le2i_te),("URFD",urfd_te)]:
        t=add_temporal_v5(te.copy()).copy()
        t["proba"]=b["model"].predict_proba(t[b["features"]])[:,1]
        t["proba_sm"]=v4.smooth_proba(t,"proba")
        t.to_pickle(f"/tmp/v5{mode}_{nm}.pkl")
    sc=mcf_te.groupby("video_id")["label"].max()
    mte=mcf_te[mcf_te["video_id"].isin(sc[sc==1].index)]
    t=add_temporal_v5(mte.copy()).copy()
    t["proba"]=b["model"].predict_proba(t[b["features"]])[:,1]
    t["proba_sm"]=v4.smooth_proba(t,"proba")
    t.to_pickle(f"/tmp/v5{mode}_MCF.pkl")
    print("cached")
