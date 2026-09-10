"""Creator-centred revision, preserving real UI footage and the approved voice style."""
from pathlib import Path
import sys,json,math,asyncio,subprocess,re
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];OLD=OUT.parent/'2026-09-10-mainfilm'
sys.path.insert(0,str(ROOT/'tmp/laxs-video-deps'));sys.path.insert(0,str(OLD))
import imageio_ffmpeg,edge_tts,render_mainfilm as style
FF=imageio_ffmpeg.get_ffmpeg_exe();W,H=1920,1080
for name in ['audio','assets','segments']:(OUT/name).mkdir(exist_ok=True)
ADDED=[
 {'id':'creator_brand','title':'현업이 직접 만들고 운영하는 플랫폼','text':'랙스 엠은 현업이 직접 만들고 운영하며, 그 데이터를 전사의 판단으로 연결하는 에이엑스 경영 플랫폼입니다.','kind':'graphic'},
 {'id':'software','title':'SW 생성기 — 현업의 요구를 업무 소프트웨어로','text':'에스더블유 생성기에서 현업이 업무 요구를 직접 정의합니다. 에이아이와 함께 기획부터 설계, 구현과 검토를 진행해, 필요한 업무 소프트웨어를 만듭니다.','note':'실제 생성 설정 → 기존 제작 사례 조회','kind':'capture'},
 {'id':'agents','title':'현업이 직접 만드는 업무 에이전트','text':'현업은 자기 업무에 맞는 에이전트도 직접 만듭니다. 역할과 필요한 스킬을 정하고, 여러 에이전트를 연결해 업무 실행 흐름을 구성합니다.','note':'실제 에이전트 생성·역할 설정 · 저장 전 편집판','kind':'capture'},
 {'id':'simulators','title':'업무영역별 담당 현업이 시뮬레이터를 생성·운영','text':'구매, 생산, 판매의 담당 현업은 자기 업무의 데이터와 규칙으로 시뮬레이터를 직접 생성하고 운영합니다. 반복 실행으로 계획과 예측, 시나리오 결과 데이터를 만들어 냅니다.','note':'실제 생성 설정 → 기존 시뮬레이터 관리','kind':'capture'},
 {'id':'data_cycle','title':'현업의 운영이 전사 데이터의 생산으로','text':'현업의 운영은 데이터 생산으로 이어집니다. 실적, 계획, 예측과 시나리오를 구분해 축적하고, 전사 판단의 근거로 연결합니다.','kind':'graphic'},
]
def run(args):
 r=subprocess.run([FF,'-y',*args],capture_output=True,text=True,encoding='utf-8',errors='replace')
 if r.returncode:raise RuntimeError(r.stderr[-6000:])
 return r
def font(n,b=True):return ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf' if b else 'C:/Windows/Fonts/malgun.ttf',n)
def text(d,xy,s,n=36,color='#f6f8fa',anchor=None):d.text(xy,s,font=font(n),fill=color,anchor=anchor)
def duration(path):
 r=subprocess.run([FF,'-i',str(path)],capture_output=True,text=True,encoding='utf-8',errors='replace');m=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',r.stderr)
 return int(m[1])*3600+int(m[2])*60+float(m[3])
async def voices():
 for s in ADDED:
  path=OUT/'audio'/f"{s['id']}.mp3"
  if not path.exists():await edge_tts.Communicate(s['text'],'ko-KR-SunHiNeural',rate='-4%',pitch='-2Hz').save(str(path))
  raw=subprocess.run([FF,'-v','error','-i',str(path),'-f','s16le','-ac','1','-ar','48000','-'],capture_output=True,check=True).stdout
  s['voice_duration']=len(raw)/96000;s['duration']=math.ceil((s['voice_duration']+1.3)*30)/30
  print('VOICE',s['id'],s['duration'],flush=True)
def header(s,transparent=True):
 im=Image.new('RGBA',(W,H),(0,0,0,0) if transparent else (7,25,45,255));d=ImageDraw.Draw(im)
 d.rectangle((0,0,W,148),fill='#07192d')
 text(d,(96,19),'LAXS-M  /  현업 주도 AX',20,'#6fcdd4')
 text(d,(96,55),s['title'],42)
 text(d,(1824,127),s.get('note','실제 제품 화면 · 시연 데이터'),19,'#a0b8c8','rm')
 return im
def graphic(s,t):
 im=style.BG.copy();d=ImageDraw.Draw(im);text(d,(96,52),'LAXS-M',28);text(d,(1824,67),'FIELD-LED AX',20,'#91b2c5','rm')
 d.line((96,112,1824,112),fill='#2a4a62',width=2)
 if s['id']=='creator_brand':
  style.draw_text_reveal(im,(91,188),'현업이 직접 만들고,',94,t/.8)
  style.draw_text_reveal(im,(91,317),'운영합니다.',112,(t-.45)/.9,style.CYAN)
  d=ImageDraw.Draw(im)
  for i,(title,desc) in enumerate([('업무 SW','현업 요구를 실행 가능한 앱으로'),('업무 에이전트','업무 역할과 실행 흐름을 직접 구성'),('업무 시뮬레이터','담당 현업의 데이터·규칙으로 운영')]):
   x=96+i*592;y=562+int(70*(1-style.ease((t-.7-i*.2)/.7)))
   d.rounded_rectangle((x,y,x+552,y+241),radius=20,fill='#103249',outline='#376377',width=2)
   text(d,(x+30,y+32),f'0{i+1}',26,'#41d3d7');text(d,(x+30,y+84),title,45);text(d,(x+30,y+161),desc,23,'#aec5d2')
  text(d,(96,876),'현업의 실행  →  데이터 축적  →  전사 판단',39,'#b7d4e0')
 else:
  style.draw_text_reveal(im,(92,180),'현업은 데이터의 생산자입니다.',72,t/.9)
  text(d,(96,305),'직접 만든 도구를 운영하며, 회사가 쓸 데이터와 결과를 축적합니다.',32,'#abc6d5')
  for i,word in enumerate(['업무 SW','에이전트','업무별 시뮬레이터']):
   x=96+i*592;d.rounded_rectangle((x,408,x+552,517),radius=17,fill='#153c51',outline='#3c6c80',width=2);text(d,(x+276,461),word,36,anchor='mm')
  d.line((960,520,960,606),fill='#36cdd2',width=4)
  for i,(word,desc) in enumerate([('실적','실제 업무의 기록'),('계획','앞으로 실행할 기준'),('예측','데이터에 근거한 전망'),('시나리오','가정별 계산 결과')]):
   x=96+i*445;y=614;d.rounded_rectangle((x,y,x+402,y+195),radius=17,fill='#0d2c43',outline='#3c6c80',width=2)
   text(d,(x+201,y+65),word,51,'#42d6db','mm');text(d,(x+201,y+137),desc,25,'#bfd0da','mm')
  text(d,(960,898),'구분해 축적하고  ·  공통 기준으로 연결하고  ·  판단의 근거로 활용',31,anchor='mm')
 text(d,(96,1040),'플랫폼 운영 구조 설명',19,'#93b0c0')
 return im
def visual(s):
 path=OUT/'segments'/f"{s['id']}_visual.mp4"
 if path.exists() and abs(duration(path)-s['duration'])<0.025:return path
 proc=subprocess.Popen([FF,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',str(path)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
 for n in range(round(s['duration']*30)):proc.stdin.write(graphic(s,n/30).tobytes())
 proc.stdin.close();err=proc.stderr.read();code=proc.wait()
 if code:raise RuntimeError(err)
 return path
def added_segment(s,capture):
 inputs=[];filters=[]
 if s['kind']=='capture':
  v=capture[s['id']];inputs=['-ss',str(v['start']),'-i',str(OUT/v['file'])]
  filters=[f"[0:v]setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration={s['duration']},pad=1920:1080:96:154:color=0x07192d[raw]"]
  h=OUT/'assets'/f"{s['id']}_head.png";header(s).save(h);inputs+=['-loop','1','-i',str(h)];filters+=['[raw][1:v]overlay=0:0[v0]'];n=2
 else:inputs=['-i',str(visual(s))];filters=['[0:v]setpts=PTS-STARTPTS[v0]'];n=1
 for k,(a,b,caption) in enumerate(style.subtitle_parts(s)):
  png=OUT/'assets'/f"{s['id']}_sub_{k}.png";style.subtitle_png(caption,png);inputs+=['-loop','1','-i',str(png)];filters.append(f"[v{k}][{n}:v]overlay=0:0:enable='between(t,{a},{b})'[v{k+1}]");n+=1
 k=len(style.subtitle_parts(s));filters.append(f"[v{k}]fade=t=in:st=0:d=0.15,fade=t=out:st={s['duration']-.16}:d=0.16,format=yuv420p[v]")
 inputs+=['-i',str(s.get('speech_file',OUT/'audio'/f"{s['id']}.mp3"))];filters.append(f"[{n}:a]adelay=450|450,apad,atrim=duration={s['duration']},aformat=sample_rates=48000:channel_layouts=stereo[a]")
 path=OUT/'segments'/f"{s['id']}.mp4";run(['-v','error',*inputs,'-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-t',str(s['duration']),'-r','30','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k',str(path)]);return path
def reuse(s):
 path=OLD/'segments'/f"{s['id']}.mp4"
 if s['id'] in ['01_question','09_close']:return path
 h=OUT/'assets'/f"{s['id']}_head.png";header(s).save(h);target=OUT/'segments'/path.name
 run(['-v','error','-i',str(path),'-loop','1','-i',str(h),'-filter_complex','[0:v][1:v]overlay=0:0:shortest=1[v]','-map','[v]','-map','0:a','-c:v','libx264','-preset','fast','-crf','18','-c:a','copy',str(target)]);return target
async def main():
 await voices();old=json.loads((OLD/'narration.json').read_text(encoding='utf-8'))['sections'];capture=json.loads((OUT/'capture_manifest.json').read_text(encoding='utf-8'))
 scenes=[old[0],*ADDED[:4],old[3],ADDED[4],old[4],old[5],old[6],old[7],old[8]];files=[];offset=0;captions=[]
 for s in scenes:
  path=added_segment(s,capture) if s in ADDED else reuse(s);files.append(path);s['start']=offset;s['actual_duration']=duration(path)
  for a,b,t in style.subtitle_parts(s):captions.append((offset+a,offset+b,t))
  offset+=s['actual_duration'];print('EDITED',s['id'],flush=True)
 (OUT/'narration.json').write_text(json.dumps({'voice':'ko-KR-SunHiNeural','sections':scenes,'total_duration':offset},ensure_ascii=False,indent=2),encoding='utf-8')
 concat=OUT/'segments/concat.txt';concat.write_text('\n'.join("file '"+str(p.resolve()).replace('\\','/')+"'" for p in files),encoding='utf-8')
 raw=OUT/'LAXS-M_creator_edit.mp4';run(['-v','error','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(raw)])
 import finish_outputs as fin
 fin.OUT=OUT;fin.META={'total_duration':offset};bed=fin.write_bed()
 final=OUT/'LAXS-M_creator_mainfilm.mp4'
 run(['-v','error','-i',str(raw),'-i',str(bed),'-filter_complex','[0:a]loudnorm=I=-16:TP=-1.5:LRA=8[a0];[a0][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=.95[a]','-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(final)])
 (OUT/'LAXS-M_creator_mainfilm.srt').write_text('\n'.join(f'{i+1}\n{fin.timestamp(a)} --> {fin.timestamp(b)}\n{t}\n' for i,(a,b,t) in enumerate(captions)),encoding='utf-8')
 result=fin.qa(final);(OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 sheet=Image.new('RGB',(1920,1520),'#07192d')
 for i,s in enumerate(scenes):
  at=s['start']+min(s['actual_duration']*.55,8);fn=OUT/'assets'/f"review_{s['id']}.jpg";run(['-v','error','-ss',str(at),'-i',str(final),'-frames:v','1',str(fn)])
  im=Image.open(fn).resize((640,360));sheet.paste(im,((i%3)*640,(i//3)*380+20));ImageDraw.Draw(sheet).text(((i%3)*640+8,(i//3)*380+3),f'{at:.1f}s  '+s['id'],fill='white')
 sheet.save(OUT/'creator_contact_sheet.jpg',quality=94);print(json.dumps(result),flush=True)
if __name__=='__main__':asyncio.run(main())
