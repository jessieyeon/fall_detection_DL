"""v4: 7 base features (motion 4 + tilt3d + aspect + shoulder_y) -> temporal features."""
import sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupShuffleSplit

BASE = ["vertical_velocity","horizontal_velocity","tilt_angle_deg","tilt_angular_velocity",
        "tilt3d_deg","aspect_ratio","shoulder_y"]
ROLL = BASE + ["speed_mag"]
FPS_T = 25.0
WINDOWS=(5,12,25); SLOPE_LAG=12; EWMA_ALPHA=0.3; PROBA_EWMA_ALPHA=0.4
SPEED_FACTORS=(0.85,1.15)

def add_temporal_features(df):
    out=[]
    for _,g in df.groupby("video_id",sort=False):
        g=g.sort_values("frame").copy()
        g["speed_mag"]=np.hypot(g["vertical_velocity"],g["horizontal_velocity"])
        g["vert_accel"]=g["vertical_velocity"].diff().fillna(0)*FPS_T
        g["tilt_accel"]=g["tilt_angular_velocity"].diff().fillna(0)*FPS_T
        g["tilt3d_vel"]=g["tilt3d_deg"].diff().fillna(0)*FPS_T
        g["aspect_vel"]=g["aspect_ratio"].diff().fillna(0)*FPS_T
        g["shoulder_vel"]=g["shoulder_y"].diff().fillna(0)*FPS_T
        for w in WINDOWS:
            for c in ROLL:
                r=g[c].rolling(w,min_periods=1)
                g[f"{c}_m{w}"]=r.mean(); g[f"{c}_s{w}"]=r.std().fillna(0)
                g[f"{c}_r{w}"]=r.max()-r.min()
        for c in ("tilt_angle_deg","vertical_velocity","tilt3d_deg","aspect_ratio","shoulder_y"):
            g[f"{c}_slope"]=(g[c]-g[c].shift(SLOPE_LAG)).fillna(0)/(SLOPE_LAG/FPS_T)
        for c in BASE:
            g[f"{c}_ewma"]=g[c].ewm(alpha=EWMA_ALPHA).mean()
        out.append(g)
    return pd.concat(out)

def augment_video(g,kind):
    g=g.sort_values("frame").reset_index(drop=True)
    if kind=="mirror":
        a=g.copy(); a["horizontal_velocity"]=-a["horizontal_velocity"]
    else:
        s=float(kind); n=max(int(len(g)/s),15)
        pos=np.linspace(0,len(g)-1,n)
        a=pd.DataFrame({c:np.interp(pos,np.arange(len(g)),g[c].values) for c in BASE})
        for c in ("vertical_velocity","horizontal_velocity","tilt_angular_velocity"): a[c]*=s
        a["label"]=g["label"].values[np.round(pos).astype(int)]
        a["frame"]=np.arange(1,n+1); a["dataset"]=g["dataset"].iloc[0]; a["video"]=g["video"].iloc[0]
    a["video_id"]=g["video_id"].iloc[0]+f"#{kind}"
    return a

def build_augmented(tr):
    parts=[tr]
    for _,g in tr.groupby("video_id",sort=False):
        parts.append(augment_video(g,"mirror"))
        for s in SPEED_FACTORS: parts.append(augment_video(g,s))
    return pd.concat(parts,ignore_index=True)

def smooth_proba(t,col):
    sm=[]
    for _,g in t.groupby("video_id",sort=False):
        sm.append(g.sort_values("frame")[col].ewm(alpha=PROBA_EWMA_ALPHA).mean())
    return pd.concat(sm)

def trigger_frame(frames,preds,pers):
    run=0
    for fr,p in zip(frames,preds):
        if p==1:
            run+=1
            if run==pers: return fr
        else: run=0
    return None

def count_events(preds,pers):
    ev=run=0; fired=False
    for p in preds:
        if p==1:
            run+=1
            if run==pers and not fired: ev+=1; fired=True
        else: run=0; fired=False
    return ev

def evaluate(t,thr,pers,fps,grace_s=0.0):
    t=t.copy(); t["pred"]=(t["proba_sm"]>=thr).astype(int)
    nf=nc=na=nfp=0; leads=[]
    for _,g in t.sort_values("frame").groupby("video_id"):
        hf=(g["label"]==1).any()
        tf=trigger_frame(g["frame"].tolist(),g["pred"].tolist(),pers)
        if hf:
            nf+=1; onset=g.loc[g["label"]==1,"frame"].max()+1
            if tf is not None and tf<=onset+grace_s*fps:
                nc+=1; leads.append((onset-tf)/fps)
        else:
            na+=1; nfp+=count_events(g["pred"].tolist(),pers)
    return dict(catch=nc,nfall=nf,fp=nfp/max(na,1),nadl=na,
                lead=None if not leads else round(float(np.median(leads)),2))

if __name__=="__main__":
    d=pd.read_csv("/tmp/features_v4.csv")
    d["video_id"]=d["dataset"]+"/"+d["video"]
    le2i=d[d.dataset=="LE2I"]; urfd=d[d.dataset=="URFD"]
    own=d[d.dataset=="OWN"].copy(); own["person"]=own["video"].str.extract(r"_(p\d)_")[0]
    mcf=d[d.dataset=="MCF"].copy(); mcf["scen"]=mcf["video"].str.split("_").str[0]

    gss=GroupShuffleSplit(n_splits=1,test_size=0.25,random_state=42)
    i,j=next(gss.split(le2i,groups=le2i["video_id"]))
    le2i_tr,le2i_te=le2i.iloc[i],le2i.iloc[j]
    useq=sorted(urfd["video"].unique())
    ut=set(np.random.RandomState(42).choice(useq,size=len(useq)//4,replace=False))
    urfd_tr,urfd_te=urfd[~urfd["video"].isin(ut)],urfd[urfd["video"].isin(ut)]

    results={}
    for test_p in ("p1","p2"):
        own_tr=own[own.person!=test_p].drop(columns=["person"])
        own_te=own[own.person==test_p].drop(columns=["person"])
        own_tr3=pd.concat([own_tr.assign(video_id=own_tr.video_id+f"~{k}") for k in range(3)])
        raw=build_augmented(pd.concat([le2i_tr,urfd_tr,own_tr3],ignore_index=True))
        f=add_temporal_features(raw)
        feats=[c for c in f.columns if c not in ("dataset","video","frame","label","video_id","person","scen")]
        clf=HistGradientBoostingClassifier(max_iter=400,max_depth=6,learning_rate=0.08,
                                           class_weight="balanced",random_state=42)
        clf.fit(f[feats],f["label"])
        joblib.dump({"model":clf,"features":feats},f"/tmp/v4_{test_p}.joblib")
        t=add_temporal_features(own_te.copy()).copy()
        t["proba"]=clf.predict_proba(t[feats])[:,1]; t["proba_sm"]=smooth_proba(t,"proba")
        t.to_pickle(f"/tmp/v4_own_te_{test_p}.pkl")
        print(f"trained test={test_p}, {len(feats)} feats",flush=True)
    # holdouts with the p2-test model (trained incl. p1)
    b=joblib.load("/tmp/v4_p2.joblib"); feats=b["features"]; clf=b["model"]
    for nm,te,fps in [("Le2i",le2i_te,25.0),("URFD",urfd_te,30.0)]:
        t=add_temporal_features(te.copy()).copy()
        t["proba"]=clf.predict_proba(t[feats])[:,1]; t["proba_sm"]=smooth_proba(t,"proba")
        t.to_pickle(f"/tmp/v4_{nm}_te.pkl")
    print("holdout features cached")
