"""Finish audio, export a complete real simulation take and verify the deliverables."""
from pathlib import Path
import sys,json,math,wave,subprocess,re
import numpy as np
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'tmp/laxs-video-deps'))
import imageio_ffmpeg
FF=imageio_ffmpeg.get_ffmpeg_exe()
META=json.loads((OUT/'narration.json').read_text(encoding='utf-8'))
MAN=json.loads((OUT/'capture_manifest.json').read_text(encoding='utf-8'))
def run(args):
 r=subprocess.run([FF,'-y',*args],capture_output=True,text=True,encoding='utf-8',errors='replace')
 if r.returncode:raise RuntimeError(r.stderr[-7000:])
 return r
def font(n,bold=False):return ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf' if bold else 'C:/Windows/Fonts/malgun.ttf',n)
def write_bed():
 # Original, quiet tonal accompaniment. No third-party music or sound samples.
 sr=48000;dur=META['total_duration']+2;n=int(sr*dur);audio=np.zeros((n,2),dtype=np.float32)
 chords=[[50,57,61,66],[47,54,57,62],[43,50,57,59],[45,52,57,62]]
 for pos in np.arange(0,dur,8):
  length=min(10,dur-pos);t=np.arange(int(length*sr))/sr
  env=np.minimum(1,t/1.8)*np.minimum(1,(length-t)/2.3)
  for j,midi in enumerate(chords[int(pos/8)%4]):
   hz=440*2**((midi-69)/12)
   tone=(np.sin(2*np.pi*hz*t)+.10*np.sin(2*np.pi*hz*2*t))*.0032*env
   off=int(pos*sr);audio[off:off+len(t),j%2]+=tone
   audio[off:off+len(t),1-j%2]+=tone*.65
 fade=np.minimum(1,np.arange(n)/sr/2)*np.minimum(1,(n-np.arange(n))/sr/3)
 audio*=fade[:,None]
 path=OUT/'audio/original_ambient_bed.wav'
 with wave.open(str(path),'wb') as w:
  w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((audio*32767).astype('<i2').tobytes())
 return path
def make_demo(bed):
 c=MAN['06_simulation'];start=3.1;duration=c['end']-start
 stages=[(0,3.1,'01  인증된 데이터 판 선택','기준선으로 사용할 판을 명시적으로 고릅니다.'),
         (3.1,10.4,'02  시연 기준값 입력','기준값은 합성 시연용으로 직접 입력한 값입니다.'),
         (10.4,15.9,'03  변화 가정 입력 · 실제 실행','환율 +3.5%  /  도입 지연 12일  /  전력단가 +8%'),
         (15.9,duration,'04  서버 계산 결과 확인','동일 기준선의 생산·손익·현금 영향을 비교합니다.')]
 inputs=['-ss',str(start),'-i',str(OUT/c['file'])];filters=['[0:v]setpts=PTS-STARTPTS,fps=30,pad=1920:1080:96:160:color=0x07192d[v0]']
 for i,(a,b,title,caption) in enumerate(stages):
  im=Image.new('RGBA',(1920,1080));d=ImageDraw.Draw(im)
  d.text((96,45),title,font=font(44,True),fill='#ffffff')
  d.text((96,108),'LAXS-M  ·  실제 기능 시연  ·  합성 데이터  ·  재생 속도 1배',font=font(23),fill='#8fb3c4')
  d.rounded_rectangle((96,990,1824,1057),radius=10,fill='#102d46')
  d.text((960,1020),caption,font=font(30,True),fill='white',anchor='mm')
  fn=OUT/'assets'/f'demo_{i}.png';im.save(fn);inputs+=['-loop','1','-i',str(fn)]
  filters.append(f"[v{i}][{i+1}:v]overlay=0:0:enable='between(t,{a},{b})'[v{i+1}]")
 inputs+=['-i',str(bed)]
 filters+=['[v4]format=yuv420p[v]',f'[5:a]atrim=duration={duration},afade=t=out:st={duration-2}:d=2[a]']
 run(['-v','error',*inputs,'-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-t',str(duration),'-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k','-movflags','+faststart',str(OUT/'LAXS-M_simulation_demo.mp4')])
def timestamp(v):
 ms=round(v*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
def srt():
 from render_mainfilm import subtitle_parts
 lines=[];offset=0
 for s in META['sections']:
  for a,b,t in subtitle_parts(s):lines.append(f'{len(lines)+1}\n{timestamp(offset+a)} --> {timestamp(offset+b)}\n{t}\n')
  offset+=math.ceil(s['duration']*30)/30
 (OUT/'LAXS-M_mainfilm.srt').write_text('\n'.join(lines),encoding='utf-8')
def qa(path):
 r=run(['-hide_banner','-i',str(path),'-vf','blackdetect=d=0.5:pix_th=0.02','-af','volumedetect','-f','null','-'])
 (OUT/(path.stem+'_verification.txt')).write_text(r.stderr,encoding='utf-8')
 return {'file':path.name,'bytes':path.stat().st_size,'decode':'passed','duration':re.search(r'Duration: ([\d:.]+)',r.stderr).group(1),'volume':re.findall(r'(?:mean_volume|max_volume): [^\n]+',r.stderr),'black_intervals':re.findall(r'black_start:[^\n]+',r.stderr)}
def contact():
 times=[3,10,19,31,43,51,55,58,67,78,86,92];sheet=Image.new('RGB',(1920,1520),'#07192d')
 for i,t in enumerate(times):
  fn=OUT/'assets'/f'final_frame_{t}.jpg'
  run(['-v','error','-ss',str(t),'-i',str(OUT/'LAXS-M_mainfilm_final.mp4'),'-frames:v','1',str(fn)])
  im=Image.open(fn);im.thumbnail((640,360));sheet.paste(im,((i%3)*640,(i//3)*380+20))
  # keep the review sheet compact without altering deliverable frames
  # preserve 16:9 aspect ratio in the review sheet
  ImageDraw.Draw(sheet).text(((i%3)*640+8,(i//3)*380+3),f'{t:02}s',fill='white')
 sheet.save(OUT/'mainfilm_contact_sheet.jpg',quality=94)
def main():
 bed=write_bed();source=OUT/'LAXS-M_mainfilm.mp4';final=OUT/'LAXS-M_mainfilm_final.mp4'
 # Normalize narration first; the accompaniment stays approximately 25 dB below speech.
 run(['-v','error','-i',str(source),'-i',str(bed),'-filter_complex','[0:a]loudnorm=I=-16:TP=-1.5:LRA=8[a0];[a0][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]','-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(final)])
 run(['-v','error','-i',str(source),'-vn','-af','loudnorm=I=-16:TP=-1.5:LRA=8','-codec:a','libmp3lame','-b:a','192k',str(OUT/'LAXS-M_main_narration.mp3')])
 print('MAIN FINAL',flush=True);make_demo(bed);print('DEMO FINAL',flush=True);srt()
 results=[qa(final),qa(OUT/'LAXS-M_simulation_demo.mp4')]
 (OUT/'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');contact();print(json.dumps(results,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
