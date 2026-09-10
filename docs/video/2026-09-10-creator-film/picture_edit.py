"""LOCAL ONLY: produce a completely silent picture-review cut. No TTS or network calls."""
from pathlib import Path
import json,wave,sys
import build_film as film
OUT=film.OUT
def main():
 durations=[11.5,16,15,18,13.5]
 for s,d in zip(film.ADDED,durations):
  s['duration']=d;s['voice_duration']=d-1.3
  path=OUT/'audio'/f"{s['id']}_silent_guide.wav"
  with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000);w.writeframes(b'\0\0'*int(48000*(d-1.3)))
  s['speech_file']=path
 old=json.loads((film.OLD/'narration.json').read_text(encoding='utf-8'))['sections'];capture=json.loads((OUT/'capture_manifest.json').read_text(encoding='utf-8'))
 scenes=[old[0],*film.ADDED[:4],old[3],film.ADDED[4],old[4],old[5],old[6],old[7],old[8]];files=[];offset=0
 for s in scenes:
  cached=OUT/'segments'/f"{s['id']}.mp4"
  if '--reuse-existing' in sys.argv and s['id']!='software' and cached.exists():path=cached
  else:path=film.added_segment(s,capture) if s in film.ADDED else film.reuse(s)
  files.append(path);s['start']=offset;s['actual_duration']=film.duration(path);offset+=s['actual_duration'];print('PICTURE',s['id'],flush=True)
 concat=OUT/'segments/picture_concat.txt';concat.write_text('\n'.join("file '"+str(p.resolve()).replace('\\','/')+"'" for p in files),encoding='utf-8')
 target=OUT/'LAXS-M_creator_picture_review_SILENT.mp4'
 film.run(['-v','error','-f','concat','-safe','0','-i',str(concat),'-an','-c:v','copy','-movflags','+faststart',str(target)])
 for s in scenes:s.pop('speech_file',None)
 (OUT/'picture_timeline.json').write_text(json.dumps({'status':'silent picture review; narration synthesis approval pending','duration':offset,'scenes':scenes},ensure_ascii=False,indent=2),encoding='utf-8')
 r=film.run(['-hide_banner','-i',str(target),'-vf','blackdetect=d=0.5:pix_th=.02','-f','null','-']);(OUT/'picture_verification.txt').write_text(r.stderr,encoding='utf-8')
 from PIL import Image,ImageDraw
 sheet=Image.new('RGB',(1920,1520),'#07192d')
 for i,s in enumerate(scenes):
  at=s['start']+min(s['actual_duration']*.55,8);fn=OUT/'assets'/f"picture_{s['id']}.jpg";film.run(['-v','error','-ss',str(at),'-i',str(target),'-frames:v','1',str(fn)])
  sheet.paste(Image.open(fn).resize((640,360)),((i%3)*640,(i//3)*380+20));ImageDraw.Draw(sheet).text(((i%3)*640+8,(i//3)*380+3),f'{at:.1f}s '+s['id'],fill='white')
 sheet.save(OUT/'creator_picture_contact_sheet.jpg',quality=94);print('PICTURE COMPLETE',offset,flush=True)
if __name__=='__main__':main()
