"""Local PCM pause analysis for readable sentence captions; no network calls."""
from pathlib import Path
import json,re,wave
import numpy as np

OUT=Path(__file__).resolve().parent

def analyze(path):
    with wave.open(str(path),'rb') as w:
        sr=w.getframerate();x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768
    hop=int(sr*.01);rms=np.sqrt(np.mean(x[:len(x)//hop*hop].reshape(-1,hop)**2,axis=1))
    threshold=max(.0015,float(np.percentile(rms,90))*.035)
    silent=rms<threshold;edges=np.diff(np.r_[False,silent,False].astype(int))
    pauses=[(a*.01,b*.01) for a,b in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)) if (b-a)>=12]
    return {'duration':len(x)/sr,'peak_dbfs':round(20*np.log10(max(np.max(np.abs(x)),1e-9)),2),'silence_fraction':round(float(np.mean(silent)),3),'pauses':pauses}

def prepare(scenes):
    timing={};checks={}
    for s in scenes:
        check=analyze(OUT/s['file']);checks[s['id']]=check
        chunks=[x.strip() for x in re.split(r'(?<=[.?!])\s+',s['text']) if x.strip()]
        dur=s['voice_duration'];weight=sum(map(len,chunks));pos=0;bounds=[0.0]
        for chunk in chunks[:-1]:
            pos+=len(chunk);guess=dur*pos/weight
            candidates=[(a+b)/2 for a,b in check['pauses'] if bounds[-1]+1<(a+b)/2<dur-1 and abs((a+b)/2-guess)<min(1.7,dur*.15)]
            bounds.append(min(candidates,key=lambda p:abs(p-guess)) if candidates else guess)
        bounds.append(dur)
        timing[s['id']]=[(a+.45,b+.45,text) for a,b,text in zip(bounds,bounds[1:],chunks)]
    (OUT/'audio_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'caption_timing.json').write_text(json.dumps(timing,ensure_ascii=False,indent=2),encoding='utf-8')
    return timing
