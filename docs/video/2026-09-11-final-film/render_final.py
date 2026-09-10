"""Offline picture, caption and audio assembly. This script never calls a network service."""
from pathlib import Path
import json,math,sys,wave
from PIL import Image,ImageDraw

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
OLD=OUT.parent/'2026-09-10-mainfilm'
CREATOR=OUT.parent/'2026-09-10-creator-film'
sys.path.insert(0,str(CREATOR));sys.path.insert(0,str(OLD))
import build_film as creator
import render_mainfilm as style
import finish_outputs as finish

def sources():
    oldcap=json.loads((OLD/'capture_manifest.json').read_text(encoding='utf-8'))
    newcap=json.loads((CREATOR/'capture_manifest.json').read_text(encoding='utf-8'))
    for cap,base in [(oldcap,OLD),(newcap,CREATOR)]:
        for item in cap.values():
            item['file']=str((base/item['file']).resolve())
            if not Path(item['file']).is_file():raise RuntimeError('Capture missing')
    edited=OUT/'assets/software_without_loading.mp4'
    if edited.exists():newcap['software'].update(file=str(edited.resolve()),start=0)
    return oldcap,newcap

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    oldcap,newcap=sources()
    if '--check-sources' in sys.argv:
        print('All original screen recordings and graphic assets available. Offline renderer ready.');return
    if '--partial' in sys.argv:
        source=json.loads((CREATOR/'picture_timeline.json').read_text(encoding='utf-8'))['scenes']
        available=[]
        for scene in source:
            audio=OUT/'audio'/f"{scene['id']}.wav"
            if not audio.exists():continue
            with wave.open(str(audio),'rb') as w:scene['voice_duration']=w.getnframes()/w.getframerate()
            scene['file']=str(audio.relative_to(OUT));available.append(scene)
        meta={'sections':available,'voice':'Sulafat'}
    else:
        meta=json.loads((OUT/'narration_generated.json').read_text(encoding='utf-8'))
    scenes=meta['sections']
    import audio_timing
    timing=audio_timing.prepare(scenes)
    style.subtitle_parts=lambda scene: timing[scene['id']]
    for name in ['audio','assets','segments']:(OUT/name).mkdir(exist_ok=True)
    creator.OUT=OUT;style.OUT=OUT;finish.OUT=OUT
    added={s['id'] for s in creator.ADDED}
    oldidx={s['id']:i for i,s in enumerate(style.SECTIONS)}
    for s in scenes:
        # Preserve natural speech tempo. Extra time extends the visual, never speeds the voice.
        s['duration']=math.ceil(max(s['actual_duration'],s['voice_duration']+1.3)*30)/30
        s['speech_file']=OUT/s['file']
        creator.run(['-v','error','-i',str(s['speech_file']),'-af','loudnorm=I=-16:TP=-1.5:LRA=8','-ar','48000','-c:a','libmp3lame','-b:a','192k',str(OUT/'audio'/f"{s['id']}.mp3")])
        # Both rendering paths consume the same normalized voice.
        s['speech_file']=OUT/'audio'/f"{s['id']}.mp3"
        if s['id'] in oldidx:style.SECTIONS[oldidx[s['id']]]=s
    def header(idx,note='실제 제품 화면 · 시연 데이터'):
        s={**style.SECTIONS[idx],'note':note}
        path=OUT/'assets'/f'header_{idx}.png';creator.header(s,transparent=False).save(path);return path
    style.overlay=header
    paths=[];offset=0;subtitles=[]
    for s in scenes:
        cached=OUT/'segments'/f"{s['id']}.mp4"
        if '--resume' in sys.argv and not ('--refresh-software' in sys.argv and s['id']=='software') and cached.exists() and abs(creator.duration(cached)-s['duration'])<.08:
            path=cached
        elif s['id'] in added:
            path=creator.added_segment(s,newcap)
        else:
            idx=oldidx[s['id']]
            if idx in (0,8):
                visual=style.write_graphic(idx);path=style.process_segment(idx,visual)
            else:
                cap=oldcap[s['id']];path=style.process_segment(idx,Path(cap['file']),cap)
        s['start']=offset;s['actual_duration']=creator.duration(path)
        for a,b,text in style.subtitle_parts(s):subtitles.append((offset+a,offset+b,text))
        offset+=s['actual_duration'];paths.append(path)
        print('EDITED',s['id'],round(s['actual_duration'],2),flush=True)
    for s in scenes:s.pop('speech_file',None)
    if '--partial' in sys.argv:
        print('AVAILABLE SEGMENTS RENDERED; full assembly pending all voices.',flush=True);return
    meta['total_duration']=offset
    (OUT/'narration.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    concat=OUT/'segments/concat.txt'
    concat.write_text('\n'.join("file '"+str(p.resolve()).replace('\\','/')+"'" for p in paths),encoding='utf-8')
    edit=OUT/'LAXS-M_B_narrator_edit.mp4'
    creator.run(['-v','error','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(edit)])
    finish.META={'total_duration':offset};bed=finish.write_bed()
    final=OUT/'LAXS-M_mainfilm_B_female.mp4'
    creator.run(['-v','error','-i',str(edit),'-i',str(bed),'-filter_complex','[0:a][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]','-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(final)])
    creator.run(['-v','error','-i',str(edit),'-vn','-c:a','libmp3lame','-b:a','192k',str(OUT/'LAXS-M_B_narration.mp3')])
    (OUT/'LAXS-M_mainfilm_B_female.srt').write_text('\n'.join(f'{i+1}\n{finish.timestamp(a)} --> {finish.timestamp(b)}\n{text}\n' for i,(a,b,text) in enumerate(subtitles)),encoding='utf-8')
    result=finish.qa(final)
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    sheet=Image.new('RGB',(1920,1520),'#07192d')
    for i,s in enumerate(scenes):
        at=s['start']+min(s['actual_duration']*.55,8);fn=OUT/'assets'/f"review_{s['id']}.jpg"
        creator.run(['-v','error','-ss',str(at),'-i',str(final),'-frames:v','1',str(fn)])
        sheet.paste(Image.open(fn).resize((640,360)),((i%3)*640,(i//3)*380+20))
        ImageDraw.Draw(sheet).text(((i%3)*640+8,(i//3)*380+3),f'{at:.1f}s '+s['id'],fill='white')
    sheet.save(OUT/'final_contact_sheet.jpg',quality=94)
    print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
