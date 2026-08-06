"""v4: all datasets -> 7 base features (4 motion + tilt3d + aspect + shoulder_y)."""
import os, sys, csv, glob, math, time, collections
import cv2
sys.path.insert(0,"/tmp")
import mediapipe as mp
from mcf_labels import fall_intervals_for_cam

DATA="/sessions/lucid-wizardly-hawking/mnt/FallDetection/data"
OUT="/tmp/features_v4.csv"; PROG="/tmp/v4.progress"
ONSETS={"fall_p1_forward_01":4.38,"fall_p1_forward_02":0.51,"fall_p1_backward_01":3.64,
 "fall_p1_backward_02":2.84,"fall_p1_side_01":0.52,"fall_p1_side_02":0.96,
 "fall_p1_chair_01":0.44,"fall_p2_forward_01":2.94,"fall_p2_forward_02":0.59,
 "fall_p2_backward_01":1.24,"fall_p2_backward_02":2.96,"fall_p2_side_01":3.55,
 "fall_p2_forward_03":1.08,"fall_p2_chair_01":1.64,"fall_p2_side_02":1.00,
 "fall_p2_side_03":2.75,"fall_p2_backward_03":1.69}
PRE_S,BUF_S,MCF_BUF_S,FALL_DUR_S=1.0,1.0,2.0,1.5
SMOOTH=3; MCF_CAMS=(1,3,5,7)
L_SH,R_SH,L_HP,R_HP=11,12,23,24
t0=time.time()
pose=mp.solutions.pose.Pose(static_image_mode=False,min_detection_confidence=0.5,model_complexity=1)

class FS:
    def __init__(s): s.reset()
    def reset(s): s.vel=[]; s.tilt=[]; s.prev=None
    def step(s,frame,fps):
        h,w=frame.shape[:2]
        res=pose.process(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        if not res.pose_landmarks: s.reset(); return None
        lm=res.pose_landmarks.landmark
        sx=(lm[L_SH].x+lm[R_SH].x)/2*w; sy=(lm[L_SH].y+lm[R_SH].y)/2*h
        hx=(lm[L_HP].x+lm[R_HP].x)/2*w; hy=(lm[L_HP].y+lm[R_HP].y)/2*h
        cx,cy=(sx+hx)/2,(sy+hy)/2
        tilt=math.degrees(math.atan2(abs(hx-sx),abs(hy-sy)+1e-6))
        xs=[p.x for p in lm]; ys=[p.y for p in lm]
        aspect=((max(xs)-min(xs))*w)/(((max(ys)-min(ys))*h)+1e-6)
        sh_y=(lm[L_SH].y+lm[R_SH].y)/2
        t3=tilt
        if res.pose_world_landmarks:
            wl=res.pose_world_landmarks.landmark
            dx=(wl[L_HP].x+wl[R_HP].x)/2-(wl[L_SH].x+wl[R_SH].x)/2
            dy=(wl[L_HP].y+wl[R_HP].y)/2-(wl[L_SH].y+wl[R_SH].y)/2
            dz=(wl[L_HP].z+wl[R_HP].z)/2-(wl[L_SH].z+wl[R_SH].z)/2
            t3=math.degrees(math.atan2(math.hypot(dx,dz),abs(dy)+1e-9))
        vy=vx=tv=0.0
        if s.prev is not None:
            vy=(cy-s.prev[1])/h*fps; vx=(cx-s.prev[0])/w*fps
            s.vel.append((vy,vx))
            if len(s.vel)>SMOOTH: s.vel.pop(0)
            vy=sum(v[0] for v in s.vel)/len(s.vel); vx=sum(v[1] for v in s.vel)/len(s.vel)
        if s.tilt: tv=(tilt-s.tilt[-1])*fps
        s.tilt.append(tilt)
        if len(s.tilt)>SMOOTH: s.tilt.pop(0)
        s.prev=(cx,cy)
        return vy,vx,tilt,tv,t3,aspect,sh_y

def lab_for(fi,intervals,fps,buf_s):
    pre=int(round(PRE_S*fps)); buf=int(round(buf_s*fps)); lab=0
    for s,e in intervals:
        if s-pre<=fi<s: return 1
        if s-pre-buf<=fi<=e+buf: lab=None
    return lab

def le2i_ann(base,vname):
    for nm in ("Annotation_files","Annotations_files"):
        p=os.path.join(base,nm,os.path.splitext(vname)[0]+".txt")
        if os.path.isfile(p):
            ls=[l.strip() for l in open(p) if l.strip()]
            try: return int(ls[0]),int(ls[1])
            except: return 0,0
    return None

tasks=[]
for fold in ("Home_01","Home_02","Coffee_room_01","Coffee_room_02"):
    base=os.path.join(DATA,"le2i",fold,fold)
    for vp in sorted(glob.glob(os.path.join(base,"Videos","*.avi"))):
        tasks.append(("le2i",vp,f"{fold}/{os.path.basename(vp)}",(base,)))
rows=collections.defaultdict(list)
with open(os.path.join(DATA,"urfd/urfall-cam0-falls.csv")) as f:
    for row in csv.reader(f):
        if len(row)>=3: rows[row[0]].append((int(row[1]),int(row[2])))
u_on={}
for sq,rr in rows.items():
    on=next((fr for fr,l in rr if l>=0),None)
    u_on[sq]=(on,max((fr for fr,l in rr if l==0),default=on))
for d in sorted(glob.glob(os.path.join(DATA,"urfd","*-cam0-rgb"))):
    st=os.path.basename(d).split("-cam0")[0]
    tasks.append(("urfd",d,st,u_on.get(st,(None,None))))
for sc in range(1,23):
    hits=sorted(glob.glob(os.path.join(DATA,"mcf",f"chute{sc:02d}*")))
    if hits:
        for cam in MCF_CAMS:
            av=os.path.join(hits[0],f"cam{cam}.avi")
            if os.path.isfile(av): tasks.append(("mcf",av,f"chute{sc:02d}_cam{cam}",(sc,cam)))
for p in sorted(glob.glob(DATA+"/raw/*.mov")+glob.glob(DATA+"/raw/*.MOV")):
    tasks.append(("own",p,os.path.splitext(os.path.basename(p))[0],()))

done=set(l.strip() for l in open(PROG)) if os.path.isfile(PROG) else set()
new=not os.path.isfile(OUT)
out=open(OUT,"a",newline=""); w=csv.writer(out)
COLS=["dataset","video","frame","vertical_velocity","horizontal_velocity","tilt_angle_deg",
      "tilt_angular_velocity","tilt3d_deg","aspect_ratio","shoulder_y","label"]
if new: w.writerow(COLS)
prog=open(PROG,"a")
fs=FS()
for kind,path,name,meta in tasks:
    key=f"{kind}/{name}"
    if key in done: continue
    if time.time()-t0>36: print("TIME UP"); sys.exit(0)
    print("START",key,flush=True)
    fs.reset(); n=0
    try:
        if kind!="urfd":
            with open(path,'rb') as _f:
                _f.seek(0,2); _sz=_f.tell(); _f.seek(max(0,_sz-65536))
                _f.read(65536)  # raises Errno35 if evicted/partial
        if kind=="urfd":
            on,en=meta; iv=[(on,en)] if on else []
            fps=30.0
            for i,p in enumerate(sorted(glob.glob(os.path.join(path,"*.png"))),1):
                img=cv2.imread(p)
                if img is None: fs.reset(); continue
                r=fs.step(img,fps)
                if r is None: continue
                lab=lab_for(i,iv,fps,BUF_S)
                if lab is not None: w.writerow(["URFD",name,i]+[round(x,5) for x in r]+[lab]); n+=1
        else:
            open_path=path
            if kind=="le2i":
                import shutil, subprocess
                shutil.copyfile(path,"/tmp/_cur.avi")
                subprocess.run(["ffmpeg","-y","-v","error","-i","/tmp/_cur.avi","-an",
                                "-c:v","libx264","-preset","ultrafast","-crf","18",
                                "/tmp/_cur.mp4"], check=True)
                open_path="/tmp/_cur.mp4"
            cap=cv2.VideoCapture(open_path)
            if kind=="le2i":
                fps=cap.get(cv2.CAP_PROP_FPS) or 25.0
                ann=le2i_ann(meta[0], os.path.basename(path))
                iv=[] if (ann is None or ann[0]==0) else [ann]
                buf=BUF_S; resize=None
            elif kind=="mcf":
                fps=30.0; iv=fall_intervals_for_cam(*meta); buf=MCF_BUF_S; resize=(480,320)
            else:
                fps=cap.get(cv2.CAP_PROP_FPS) or 30.0
                on=int(round(ONSETS[name]*fps)) if name in ONSETS else None
                iv=[(on,on+int(FALL_DUR_S*fps))] if on else []
                buf=BUF_S; resize="half"
            fi=0
            while True:
                ok,f=cap.read()
                if not ok: break
                fi+=1
                if resize=="half":
                    h0,w0=f.shape[:2]; sc2=480/max(h0,w0)
                    f=cv2.resize(f,(int(w0*sc2),int(h0*sc2)))
                elif resize: f=cv2.resize(f,resize)
                r=fs.step(f,fps)
                if r is None: continue
                lab=lab_for(fi,iv,fps,buf)
                if lab is not None:
                    w.writerow([kind.upper(),name.replace("/","_") if kind=="mcf" else name,fi]
                               +[round(x,5) for x in r]+[lab]); n+=1
            cap.release()
    except OSError as e:
        print(key,"OSError -> later",flush=True); continue
    out.flush(); prog.write(key+"\n"); prog.flush()
    print("done",key,n,flush=True)
print("ALL DONE")
