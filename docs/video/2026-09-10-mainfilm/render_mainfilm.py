"""신경망 음성과 실제 브라우저 녹화로 본편을 편집한다.

--graphics-only: 인트로·엔딩과 음성만 제작한다.
기본 실행은 capture_manifest.json에 여섯 실제 촬영본이 없으면 중단한다.
"""
from pathlib import Path
import sys,math,json,subprocess,wave,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageChops
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'tmp/laxs-video-deps'))
import imageio_ffmpeg
FF=imageio_ffmpeg.get_ffmpeg_exe();W,H,FPS=1920,1080,30
META=json.loads((OUT/'narration.json').read_text(encoding='utf-8'))
SECTIONS=META['sections'];NAVY=(7,25,45);WHITE=(247,248,250);CYAN=(55,213,217);DIM=(144,170,193)
FONT={}
def f(n,b=True):
 k=(n,b)
 if k not in FONT:FONT[k]=ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf' if b else 'C:/Windows/Fonts/malgun.ttf',n)
 return FONT[k]
def txt(d,p,s,n=32,col=WHITE,b=True,anchor=None):d.text(p,s,font=f(n,b),fill=col,anchor=anchor)
def ease(t):return 1-(1-max(0,min(1,t)))**3
def draw_text_reveal(im,xy,s,n,progress,col=WHITE):
 layer=Image.new('RGBA',(W,H));d=ImageDraw.Draw(layer);txt(d,xy,s,n,col)
 width=d.textlength(s,font=f(n));mask=Image.new('L',(W,H));m=ImageDraw.Draw(mask)
 m.rectangle((xy[0],xy[1],xy[0]+width*ease(progress),xy[1]+n*1.6),fill=255)
 im.paste(layer,mask=ImageChops.multiply(mask,layer.getchannel("A")))
def base():
 y,x=np.mgrid[0:H,0:W];a=np.maximum(0,1-np.sqrt(((x-1100)/1450)**2+((y-600)/1000)**2))
 rgb=np.stack([7+a*2,25+a*19,45+a*25],axis=-1).astype(np.uint8)
 return Image.fromarray(rgb)
BG=base();LOGO=Image.open(ROOT/'docs/official/assets/brand-v0.3/laxs-logo-primary-on-navy-v2.png').convert('RGB')

def graphic(idx,t,duration):
 im=BG.copy();d=ImageDraw.Draw(im)
 for k in range(4):
  radius=350+k*110+t*11
  d.ellipse((1300-radius,450-radius,1300+radius,450+radius),outline=(15,49,68),width=1)
 txt(d,(88,52),'LAXS-M',28);txt(d,(1832,70),'AX MANAGEMENT PLATFORM',20,DIM,False,'rm')
 d.line((88,113,1832,113),fill=(30,65,86),width=1)
 if idx==0:
  txt(d,(96,182),'하나의 변화는, 어디까지 이어질까요?',30,CYAN,False)
  draw_text_reveal(im,(87,268),'원료 도입이 늦어지면,',94,t/.95)
  draw_text_reveal(im,(87,400),'회사의 내일은?',118,(t-.55)/1.2)
  d=ImageDraw.Draw(im)
  labels=['구매','재고','생산','판매','현금'];xs=[210,585,960,1335,1710];yy=761
  for k in range(4):
   p=ease((t-1.3-k*.5)/1.0);d.line((xs[k],yy,xs[k]+(xs[k+1]-xs[k])*p,yy),fill=(43,156,173),width=4)
  for k,x in enumerate(xs):
   p=ease((t-.65-k*.3)/.6);y=yy+int((1-p)*65)
   r=51
   d.ellipse((x-r,y-r,x+r,y+r),fill=(13,48,69),outline=CYAN,width=3)
   txt(d,(x,y-1),labels[k],30,WHITE,True,'mm')
   if k in (2,3,4):txt(d,(x,y+93),'?',42,CYAN,True,'mm')
  pulse=210+1500*((max(0,t-1)/5)%1)
  d.ellipse((pulse-8,yy-8,pulse+8,yy+8),fill=WHITE)
 elif idx==1:
  draw_text_reveal(im,(89,211),'LAXS-M',180,t/1)
  draw_text_reveal(im,(96,457),'현업의 실행과',66,(t-.5)/1.1)
  draw_text_reveal(im,(96,552),'경영의 판단을 연결합니다.',66,(t-1.2)/1.2,CYAN)
  d=ImageDraw.Draw(im)
  y=790
  for k,(word,x) in enumerate([('현업',180),('데이터',670),('경영',1160)]):
   offset=int((1-ease((t-.8-k*.3)/.7))*100)
   d.rounded_rectangle((x,y+offset,x+360,y+100+offset),radius=22,fill=(17,56,80),outline=(41,99,121),width=2)
   txt(d,(x+180,y+49+offset),word,36,WHITE,True,'mm')
   if k<2:d.line((x+360,y+50,x+490,y+50),fill=CYAN,width=3)
 else:
  txt(d,(96,190),'THE LIVING ENTERPRISE',24,CYAN)
  for k,(word,color) in enumerate([('현업이 만들고,',WHITE),('전사가 연결하며,',WHITE),('경영이 판단합니다.',CYAN)]):
   draw_text_reveal(im,(90,284+k*116),word,84,(t-k*.5)/.85,color)
  d=ImageDraw.Draw(im)
  d.line((96,729,1050,729),fill=(54,94,117),width=2)
  txt(d,(96,796),'회사의 일과 경영 안에 AX를.',36,DIM,False)
  logo=LOGO.resize((615,231),Image.Resampling.LANCZOS)
  im.paste(logo,(1210,650));d=ImageDraw.Draw(im)
  txt(d,(1517,930),'LAXS-M',56,WHITE,True,'mm')
 txt(d,(88,1034),'제품 소개 · 시연 데이터 기반',19,DIM,False)
 return im

def run(cmd):
 r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace')
 if r.returncode:raise RuntimeError(r.stderr[-5000:])
 return r

def write_graphic(idx):
 s=SECTIONS[idx];duration=s['duration'];target=OUT/'segments'/f"{s['id']}_visual.mp4"
 cmd=[FF,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-','-an','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p',str(target)]
 proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
 for n in range(round(duration*FPS)):proc.stdin.write(graphic(idx,n/FPS,duration).tobytes())
 proc.stdin.close();err=proc.stderr.read();code=proc.wait()
 if code:raise RuntimeError(err)
 graphic(idx,min(3,duration/2),duration).save(OUT/f"{s['id']}_poster.jpg",quality=93)
 return target

def subtitle_parts(s):
 # 문장별 자막. 음성 원본 길이 안에 글자 비중으로 배치한다.
 import re
 chunks=[x.strip() for x in re.split(r'(?<=[.?!])\s+',s['text']) if x.strip()]
 result=[];pos=.45;weight=sum(len(x) for x in chunks)
 for x in chunks:
  dur=s['voice_duration']*len(x)/weight
  result.append((pos,pos+dur,x));pos+=dur
 return result

def subtitle_png(text,path):
 im=Image.new('RGBA',(1920,1080));d=ImageDraw.Draw(im)
 words=text.split();lines=['']
 for word in words:
  if d.textlength((lines[-1]+' '+word).strip(),font=f(29))>1680:lines.append(word)
  else:lines[-1]=(lines[-1]+' '+word).strip()
 height=48*len(lines)+12;y=1051-height
 d.rounded_rectangle((70,y,1850,1054),radius=10,fill=(4,15,28,238))
 for k,line in enumerate(lines):txt(d,(960,y+30+k*44),line,29,WHITE,True,'mm')
 im.save(path)

def overlay(idx,note='실제 제품 화면 · 시연 데이터'):
 s=SECTIONS[idx];im=Image.new('RGBA',(1920,1080),NAVY+(255,));d=ImageDraw.Draw(im)
 d.rounded_rectangle((95,153,1825,966),radius=16,fill=(0,0,0,0),outline=(59,89,110),width=2)
 txt(d,(96,48),f'{idx-1:02d}',52,CYAN)
 txt(d,(194,48),s['title'],44,WHITE)
 txt(d,(1824,77),note,20,DIM,False,'rm')
 txt(d,(96,1014),'LAXS-M',20,DIM)
 path=OUT/'assets'/f'overlay_{idx}.png';im.save(path);return path

def process_segment(idx,visual,capture=None):
 s=SECTIONS[idx];duration=s['duration'];inputs=[];filters=[]
 if capture:
  inputs=['-ss',str(capture.get('start',0)),'-i',str(visual),'-loop','1','-i',str(overlay(idx,capture.get('note','실제 제품 화면 · 시연 데이터')))]
  # 전 구간은 실제 영상. 부족한 끝부분만 마지막 프레임을 유지한다.
  crop=capture.get('crop')
  crop_filter=f'crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},' if crop else ''
  if idx==5:crop_filter="crop=1208:566:220:'if(lt(t,5.05),240,74)',"
  if idx==7:crop_filter='crop=1208:566:220:230,'
  filters=[f'[0:v]setpts=PTS-STARTPTS,{crop_filter}fps=30,scale=1728:810:force_original_aspect_ratio=decrease,pad=1728:810:(ow-iw)/2:(oh-ih)/2:color=0x07192d,tpad=stop_mode=clone:stop_duration={duration}[screen]', '[1:v][screen]overlay=96:154:shortest=1[v0]']
  n=2
  if idx==5:
   panel=Image.new('RGBA',(1920,1080));d=ImageDraw.Draw(panel)
   d.rounded_rectangle((780,192,1780,862),radius=22,fill=(10,31,52,255),outline=(38,82,103),width=2)
   txt(d,(830,232),'시연할 변화 가정',30,CYAN)
   for row,(v,label) in enumerate([('12일','원료 도입 지연'),('+3.5%','환율 변화'),('+8%','전력단가 변화')]):
    yy=310+row*151;txt(d,(835,yy),v,64);txt(d,(1190,yy+22),label,32,DIM)
   txt(d,(830,798),'시연 기준값을 직접 입력해 비교합니다.',26,DIM,False)
   panel_path=OUT/'assets/simulation_callout.png';panel.save(panel_path)
   inputs+=['-loop','1','-i',str(panel_path)]
   filters[-1]=filters[-1].replace('[v0]','[vraw]')
   filters.append("[vraw][2:v]overlay=0:0:enable='lt(t,4.4)'[v0]");n=3
 else:
  inputs=['-i',str(visual)];filters=['[0:v]setpts=PTS-STARTPTS[v0]'];n=1
 for k,(a,b,txtval) in enumerate(subtitle_parts(s)):
  png=OUT/'assets'/f"caption_{idx}_{k}.png";subtitle_png(txtval,png);inputs+=['-loop','1','-i',str(png)]
  filters.append(f"[v{k}][{n}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[v{k+1}]");n+=1
 k=len(subtitle_parts(s));filters.append(f'[v{k}]fade=t=in:st=0:d=0.15,fade=t=out:st={duration-.16}:d=0.16,format=yuv420p[v]')
 inputs+=['-i',str(OUT/'audio'/f"{s['id']}.mp3")]
 filters.append(f'[{n}:a]adelay=450|450,apad,atrim=duration={duration},aformat=sample_rates=48000:channel_layouts=stereo[a]')
 target=OUT/'segments'/f"{s['id']}.mp4"
 run([FF,'-y','-v','error',*inputs,'-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-t',str(duration),'-r','30','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k',str(target)])
 return target

def main():
 (OUT/'segments').mkdir(exist_ok=True);(OUT/'assets').mkdir(exist_ok=True)
 graphics_only='--graphics-only' in sys.argv
 manifest={} if graphics_only else json.loads((OUT/'capture_manifest.json').read_text(encoding='utf-8'))
 if not graphics_only:
  for idx in range(2,8):
   s=SECTIONS[idx]
   if s['id'] not in manifest:raise RuntimeError(f"실제 촬영본이 없습니다: {s['id']}")
 produced=[]
 for idx,s in enumerate(SECTIONS):
  if graphics_only and idx not in (0,1,8):continue
  if idx in (0,1,8):
   v=OUT/'segments'/f"{s['id']}_visual.mp4"
   if not v.exists() or '--refresh-graphics' in sys.argv:v=write_graphic(idx)
   target=process_segment(idx,v)
  else:target=process_segment(idx,OUT/manifest[s['id']]['file'],manifest[s['id']])
  produced.append(target);print('편집 완료',s['id'],flush=True)
 if graphics_only:
  items=produced[:2];output=OUT/'LAXS-M_opening_preview.mp4'
 else:items=produced;output=OUT/'LAXS-M_mainfilm.mp4'
 concat=OUT/'segments'/('opening.txt' if graphics_only else 'main.txt')
 concat.write_text('\n'.join("file '"+str(p).replace('\\','/')+"'" for p in items),encoding='utf-8')
 run([FF,'-y','-v','error','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(output)])
 print('완료',output,flush=True)

if __name__=='__main__':main()
