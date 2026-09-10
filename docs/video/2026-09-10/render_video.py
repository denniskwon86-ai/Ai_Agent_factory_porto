"""LAXS-M 20초 콘셉트 영상. Pillow 모션그래픽 + 로컬 음성 + 합성 배경음.

실행: bundled Python render_video.py
준비: make_voice.ps1, imageio-ffmpeg (tmp/laxs-video-deps 또는 설치 환경)
"""
from pathlib import Path
import sys, math, json, wave, subprocess, hashlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / 'tmp/laxs-video-deps'))
import imageio_ffmpeg

W, H, FPS, DURATION = 1920, 1080, 30, 20
STARTS = [0, 3.2, 7.4, 11.8, 16.6, 20]
NAVY = (9, 41, 72)
DARK = (6, 25, 49)
WHITE = (248, 249, 251)
MUTED = (161, 182, 202)
CYAN = (69, 210, 219)
RED = (250, 0, 45)
PAPER = (244, 243, 239)
INK = (17, 27, 46)
FONTS = {}
for bold in [False, True]:
    for size in [20, 22, 24, 26, 28, 30, 32, 34, 36, 40, 44, 48, 52, 56, 60, 66, 72, 78, 84, 100]:
        FONTS[size, bold] = ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf' if bold else 'C:/Windows/Fonts/malgun.ttf', size)

def font(size, bold=False):
    return FONTS[size, bold]

def text(draw, xy, value, size=32, fill=WHITE, bold=False, anchor=None):
    draw.text(xy, value, font=font(size,bold), fill=fill, anchor=anchor, stroke_width=0)

def ease(x):
    x = max(0, min(1, x))
    return 1-(1-x)**3

def mix(a,b,t):
    return tuple(int(x+(y-x)*t) for x,y in zip(a,b))

def rr(draw, box, fill, outline=None, radius=22, width=2):
    draw.rounded_rectangle(tuple(map(int,box)), radius, fill, outline, width)

def line(draw, pts, fill, width=3):
    draw.line(pts, fill=fill, width=width, joint='curve')

def pulse(draw,a,b,t,color=CYAN, width=3):
    line(draw,[a,b],mix(NAVY,CYAN,.3),width)
    p=t%1
    x=a[0]+(b[0]-a[0])*p;y=a[1]+(b[1]-a[1])*p
    draw.ellipse((x-7,y-7,x+7,y+7),fill=color)

def pill(draw,xy,label,width=210,light=False,color=None):
    x,y=xy
    rr(draw,(x,y,x+width,y+50),(230,235,238) if light else (19,57,86),color or ((205,214,223) if light else (43,87,114)),radius=25)
    text(draw,(x+width/2,y+24),label,22,INK if light else WHITE,True,'mm')

def background(light=False):
    if light:
        im=Image.new('RGB',(W,H),PAPER)
    else:
        yy,xx=np.mgrid[0:H,0:W]
        g=np.maximum(0,1-np.sqrt(((xx-1450)/1600)**2+((yy-470)/1200)**2))*.55
        arr=np.zeros((H,W,3),dtype=np.uint8)
        for c in range(3):arr[:,:,c]=DARK[c]+g*(NAVY[c]+(8 if c==2 else 0)-DARK[c])
        im=Image.fromarray(arr)
    dr=ImageDraw.Draw(im)
    col=(224,226,224) if light else (15,43,65)
    for x in range(0,W,80):dr.line((x,0,x,H),fill=col)
    for y in range(0,H,80):dr.line((0,y,W,y),fill=col)
    return im

BGS=[background(),background(),background(True),background(),Image.new('RGB',(W,H),NAVY)]
LOGO=Image.open(ROOT/'docs/official/assets/brand-v0.3/laxs-logo-primary-on-navy-v2.png').convert('RGB')
LOGO=LOGO.resize((760,285),Image.Resampling.LANCZOS)

def chrome(im,i,t):
    d=ImageDraw.Draw(im)
    light=i==2
    fg=INK if light else WHITE
    sub=(105,120,135) if light else MUTED
    text(d,(88,58),'LAXS-M',30,fg,True)
    text(d,(1832,73),'AX 경영 플랫폼  /  LS MnM',22,sub,False,'rm')
    d.line((88,115,1832,115),fill=(215,220,222) if light else (38,65,87),width=1)
    text(d,(88,1015),'제품 비전 · 콘셉트 영상',20,sub)
    text(d,(1832,1030),f'{i+1:02d} / 05',20,sub,False,'rm')
    d.rectangle((0,1074,int(W*t/DURATION),1079),fill=CYAN)

def scene(i,u):
    im=BGS[i].copy();d=ImageDraw.Draw(im)
    rise=int((1-ease(u/.6))*25)
    if i==0:
        text(d,(90,208+rise),'THE MANAGEMENT GAP',24,CYAN,True)
        text(d,(86,302+rise),'업무는 흩어지고,',78,WHITE,True)
        text(d,(86,410+rise),'판단은 늦어집니다.',78,WHITE,True)
        text(d,(90,563),'구매 · 생산 · 판매 · 재무',32,MUTED)
        text(d,(90,619),'같은 질문, 서로 다른 기준.',32,MUTED)
        cards=[(1170,253,'ERP','거래와 실적'),(1455,453,'MES','생산과 현장'),(1115,650,'Excel','계획과 보고')]
        for k,(x,y,title,sub) in enumerate(cards):
            y+=int(math.sin(u*1.2+k)*9)
            rr(d,(x,y,x+305,y+168),(15,47,74),(60,83,105))
            d.rectangle((x+24,y+26,x+30,y+62),fill=RED if k==2 else CYAN)
            text(d,(x+49,y+21),title,40,WHITE,True)
            text(d,(x+26,y+105),sub,26,MUTED)
        for a,b in [((1320,420),(1500,445)),((1480,623),(1420,690))]:
            for n in range(0,10,2):
                p=n/10;q=(n+1)/10
                line(d,[(a[0]+(b[0]-a[0])*p,a[1]+(b[1]-a[1])*p),(a[0]+(b[0]-a[0])*q,a[1]+(b[1]-a[1])*q)],(104,97,115),3)
        d.ellipse((1090,868,1104,882),fill=RED)
        text(d,(1120,858),'연결되지 않은 경영의 맥락',24,MUTED)
    elif i==1:
        text(d,(90,208+rise),'OPERATIONAL APP FACTORY',24,CYAN,True)
        text(d,(86,302+rise),'현업의 생각을',78,WHITE,True)
        text(d,(86,410+rise),'업무 앱으로.',78,CYAN,True)
        text(d,(90,570),'업무키트와 AI 에이전트로 시작하고,',30,MUTED)
        text(d,(90,623),'회사 권한과 데이터 기준 안에서 운영합니다.',30,MUTED)
        pill(d,(90,728),'현업 주도',190)
        pill(d,(298,728),'회사 기준 상속',255)
        x=1090+int(40*(1-ease(u/.7)))
        rr(d,(x,232,x+705,340),(21,64,91),(55,124,149))
        text(d,(x+352,286),'“원료 도입 계획을 관리하고 싶어요.”',30,WHITE,False,'mm')
        pulse(d,(x+350,341),(x+350,425),u*.55)
        rr(d,(x,430,x+705,815),(243,246,248),None)
        rr(d,(x,430,x+705,497),(228,235,240),None)
        text(d,(x+30,449),'원료 도입 계획',30,INK,True)
        for k,lab in enumerate(['품목 · 공급사','도입 일정','검토 · 승인']):
            y=530+k*83
            rr(d,(x+28,y,x+676,y+61),(255,255,255),(211,222,230),radius=10)
            text(d,(x+48,y+12),lab,24,INK)
            progress=ease((u-.6-k*.35)/.7)
            d.line((x+340,y+30,x+340+int(280*progress),y+30),fill=(0,155,180),width=8)
        text(d,(x+352,855),'업무 목적 → 생성 · 검증 → 운영',26,MUTED,False,'mm')
    elif i==2:
        text(d,(90,192+rise),'MANAGEMENT MEANING MAP',24,(0,128,149),True)
        text(d,(86,267+rise),'부서의 데이터가,',72,INK,True)
        text(d,(86,364+rise),'회사의 지식이 됩니다.',72,INK,True)
        labs=['구매','재고','생산','판매','재무']
        xs=[190,530,870,1210,1550]
        for k in range(4):pulse(d,(xs[k]+180,612),(xs[k+1],612),u*.45-k*.15,(0,155,180),4)
        for k,(x,lab) in enumerate(zip(xs,labs)):
            y=539+int(24*(1-ease((u-k*.12)/.55)))
            rr(d,(x,y,x+180,y+146),(255,255,255),(195,210,218),radius=18)
            text(d,(x+90,y+39),f'0{k+1}',22,(0,155,180),True,'mm')
            text(d,(x+90,y+91),lab,36,INK,True,'mm')
            line(d,[(x+90,y+146),(x+90,746)],(139,176,188),2)
        rr(d,(190,746,1730,832),NAVY,None,18)
        text(d,(960,789),'기업 경영 의미지도   ·   같은 데이터, 같은 뜻, 같은 기준',30,WHITE,True,'mm')
        text(d,(960,888),'ERP · MES · LPL의 데이터와 현업 지식을 연결',26,(83,106,123),False,'mm')
    elif i==3:
        text(d,(90,192+rise),'MANAGEMENT TWIN → DECISION',24,CYAN,True)
        text(d,(86,275+rise),'미래를 비교하고,',72,WHITE,True)
        text(d,(86,372+rise),'결정을 실행으로.',72,WHITE,True)
        pill(d,(92,523),'기준안',210)
        pill(d,(324,523),'대안',210,color=CYAN)
        text(d,(90,622),'손익 · 현금 · 납기의 영향을 검토',30,MUTED)
        text(d,(90,682),'데이터·산식으로 계산, 사람이 결정',30,MUTED)
        cx,cy=1430,548
        points=[]
        for k in range(5):
            ang=-math.pi/2+k*math.tau/5
            points.append((cx+285*math.cos(ang),cy+240*math.sin(ang)))
        for k in range(5):pulse(d,points[k],points[(k+1)%5],u*.5-k*.2,CYAN,3)
        for k,(x,y) in enumerate(points):
            active=int(max(0,u-.15)/.68)%5==k
            rr(d,(x-92,y-40,x+92,y+40),(22,80,99) if active else (16,48,76),CYAN if active else (56,91,116),radius=20)
            text(d,(x,y-1),['판단','승인','실행','효과','학습'][k],32,WHITE,True,'mm')
        text(d,(cx,cy-15),'결정의 근거와',26,MUTED,False,'mm')
        text(d,(cx,cy+28),'결과를 축적',30,WHITE,True,'mm')
        pill(d,(90,803),'실적 · 계획 · 예측 · 시나리오 구분',620)
    else:
        im.paste(LOGO,(580,205))
        d=ImageDraw.Draw(im)
        text(d,(960,565+rise),'LAXS-M',100,WHITE,True,'mm')
        text(d,(960,704+rise),'현업이 만들고, 경영이 결정합니다.',56,WHITE,True,'mm')
        text(d,(960,795),'LS의 일과 경영에 AX를 내재화합니다.',30,CYAN,False,'mm')
        line(d,[(630,871),(1290,871)],(67,103,128),2)
        text(d,(960,916),'현업 실행  ·  전사 연결  ·  경영 판단',26,MUTED,False,'mm')
    return im

CAPTIONS=[
    (.25,2.95,'흩어진 업무와 데이터.'),
    (3.45,7.1,'현업의 생각을 업무 앱으로.'),
    (7.65,11.5,'부서의 데이터를 회사의 지식으로.'),
    (12.05,16.3,'경영 판단에서, 실행과 학습까지.'),
    (16.8,19.9,'현업과 경영을 잇는, LAXS-M.')
]

def frame(t):
    i=next((k for k in range(5) if STARTS[k]<=t<STARTS[k+1]),4)
    im=scene(i,t-STARTS[i])
    if i<4 and t>STARTS[i+1]-.26:
        a=(t-(STARTS[i+1]-.26))/.26
        im=Image.blend(im,scene(i+1,0),ease(a))
    chrome(im,i,t)
    d=ImageDraw.Draw(im)
    for a,b,s in CAPTIONS:
        if a<=t<b:
            tw=d.textlength(s,font=font(28,True))
            rr(d,(960-tw/2-24,949,960+tw/2+24,995),(4,17,31),None,12)
            text(d,(960,971),s,28,WHITE,True,'mm')
    return im

def audio():
    sr=48000
    tt=np.arange(sr*DURATION,dtype=np.float64)/sr
    music=np.zeros_like(tt)
    # 직접 합성한 잔잔한 4화음. 외부 음악·샘플을 사용하지 않는다.
    for k,chord in enumerate([[146.83,220,293.66,369.99],[130.81,196,261.63,329.63],[164.81,246.94,329.63,392],[146.83,220,293.66,440]]):
        a=k*5;b=a+5
        sel=(tt>=a)&(tt<b)
        local=tt[sel]-a
        env=np.minimum(local/1,1)*np.minimum((5-local)/1.2,1)
        for f in chord:
            music[sel]+=0.0075*env*(np.sin(2*np.pi*f*local)+.2*np.sin(4*np.pi*f*local))
    # 짧은 연결음으로 장면 전환의 리듬을 만든다.
    for k,a in enumerate([.1,3.2,7.4,11.8,16.6]):
        local=tt-a;sel=(local>=0)&(local<1.4)
        music[sel]+=.019*np.sin(2*np.pi*(659.25 if k%2 else 880)*local[sel])*np.exp(-local[sel]*5)*np.minimum(local[sel]*80,1)
    voice=np.zeros_like(tt)
    durations=[]
    for k,(a,b,s) in enumerate(CAPTIONS):
        f=OUT/f'audio/voice_{k}.wav'
        with wave.open(str(f),'rb') as w:
            rate=w.getframerate();n=w.getnframes();channels=w.getnchannels();sw=w.getsampwidth();raw=w.readframes(n)
        if sw!=2:raise ValueError(f'음성 샘플 폭: {sw}')
        samples=np.frombuffer(raw,np.int16).astype(float)/32768
        if channels>1:samples=samples.reshape(-1,channels).mean(1)
        duration=len(samples)/rate
        # 자막 구간 안에 음성이 들어가도록 필요한 경우만 아주 소폭 압축한다.
        target=min(duration,b-a-.06)
        res=np.interp(np.arange(int(target*sr))/sr/target*duration,np.arange(len(samples))/rate,samples)
        peak=max(abs(res).max(),.01);res=res/peak*.72
        start=int(a*sr);voice[start:start+len(res)]+=res
        durations.append({'scene':k+1,'original_seconds':round(duration,3),'used_seconds':round(target,3),'start':a,'text':s})
    music*=np.minimum(tt/0.4,1)*np.minimum((DURATION-tt)/.6,1)
    stereo=np.stack([voice+music,voice+np.roll(music,240)],axis=1)
    stereo=np.clip(stereo,-.97,.97)
    with wave.open(str(OUT/'audio/mix.wav'),'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((stereo*32767).astype(np.int16).tobytes())
    return durations,float(abs(stereo).max())

def timestamp(s):
    ms=round(s*1000);return f'00:00:{ms//1000:02d},{ms%1000:03d}'

def main():
    OUT.mkdir(exist_ok=True,parents=True)
    speech,peak=audio()
    (OUT/'captions.srt').write_text('\n\n'.join(f'{k+1}\n{timestamp(a)} --> {timestamp(b)}\n{s}' for k,(a,b,s) in enumerate(CAPTIONS))+'\n',encoding='utf-8')
    shots=[]
    for k,t in enumerate([1.8,5.3,9.5,14.1,18.3]):
        im=frame(t);im.save(OUT/f'scene_{k+1:02d}.jpg',quality=93)
        shots.append(im.resize((640,360),Image.Resampling.LANCZOS))
    board=Image.new('RGB',(1920,840),PAPER);bd=ImageDraw.Draw(board)
    text(bd,(48,32),'LAXS-M  /  20초 스토리보드',40,INK,True)
    for k,im in enumerate(shots):board.paste(im,((k%3)*640,110+(k//3)*365))
    text(bd,(1340,551),'현업 실행 → 전사 연결',30,INK,True)
    text(bd,(1340,603),'→ 경영 판단 → 학습',30,INK,True)
    text(bd,(1340,681),'1920 × 1080 · 30 fps · 20 s',24,(86,104,122))
    board.save(OUT/'storyboard.jpg',quality=92)
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    output=OUT/'LAXS-M_20s_sample.mp4'
    cmd=[ffmpeg,'-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(OUT/'audio/mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-t','20','-movflags','+faststart','-metadata','title=LAXS-M | 현업과 경영을 연결하다','-metadata','comment=제품 비전 콘셉트. 실데이터 성과 또는 제품 실행 녹화가 아님.',str(output)]
    with (OUT/'render.log').open('w',encoding='utf-8') as log:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        for n in range(FPS*DURATION):
            proc.stdin.write(frame(n/FPS).tobytes())
            if n%60==0:print(f'렌더링 {n}/{FPS*DURATION}',flush=True)
        proc.stdin.close()
        if proc.wait()!=0:raise RuntimeError('영상 인코딩 실패: render.log 참조')
    decoded=subprocess.run([ffmpeg,'-v','error','-i',str(output),'-progress','pipe:1','-f','null','-'],capture_output=True,text=True)
    counts=[int(row.split('=')[1]) for row in decoded.stdout.splitlines() if row.startswith('frame=')]
    decoded_frames=counts[-1] if counts else None
    metadata=subprocess.run([ffmpeg,'-hide_banner','-i',str(output)],capture_output=True,text=True,encoding='utf-8',errors='replace').stderr
    (OUT/'media_info.txt').write_text(metadata,encoding='utf-8')
    v={'file':output.name,'width':W,'height':H,'fps':FPS,'frames_written':FPS*DURATION,'intended_duration_seconds':DURATION,'decoded_frames':decoded_frames,'duration_20_seconds_verified':'Duration: 00:00:20.00' in metadata,'decode_success':decoded.returncode==0 and decoded_frames==600,'decode_errors':decoded.stderr,'audio_peak_linear':peak,'voice':'Microsoft Heami Desktop (ko-KR), local Windows TTS','music':'Original synthesized tones; no third-party music','narration_segments':speech,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':output.stat().st_size,'scope':'Concept animation of product vision; no actual product execution or ROI claim'}
    (OUT/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(v,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
