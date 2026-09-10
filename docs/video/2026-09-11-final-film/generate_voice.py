"""Generate the 12 narration paragraphs approved in the conversation, using chosen B voice.
Only approved narration and performance directions go to Google Gemini; no documents or media.
"""
from pathlib import Path
import concurrent.futures,json,os,sys,wave,time
from dotenv import dotenv_values
from google import genai
from google.genai import types

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
AUDITION=OUT.parent/'2026-09-11-voice-audition'
SCENES=json.loads((OUT.parent/'2026-09-10-creator-film/picture_timeline.json').read_text(encoding='utf-8'))['scenes']
if (OUT/'narration_override.json').exists():
    overrides=json.loads((OUT/'narration_override.json').read_text(encoding='utf-8'))
    for scene in SCENES:scene.update(overrides.get(scene['id'],{}))
# Preserve the exact voice direction selected in the B audition.
STYLE=(AUDITION/'B_warm_narrator_prompt.txt').read_text(encoding='utf-8').split('\n\nSCRIPT:')[0]

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    (OUT/'audio').mkdir(parents=True,exist_ok=True)
    cfg=dotenv_values(ROOT/'.env')
    key=os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY') or cfg.get('GEMINI_API_KEY') or cfg.get('GOOGLE_API_KEY')
    if not key:raise RuntimeError('Gemini credential unavailable')
    def generate(s):
        dest=OUT/'audio'/f"{s['id']}.wav"
        prompt=STYLE+'\n\nSCRIPT:\n'+s['text']
        (OUT/'audio'/f"{s['id']}_prompt.txt").write_text(prompt,encoding='utf-8')
        if not dest.exists():
            print('QUEUED',s['id'],flush=True)
            time.sleep(35)
            client=genai.Client(api_key=key,http_options=types.HttpOptions(timeout=120000))
            try:
                result=client.models.generate_content(model='gemini-3.1-flash-tts-preview',contents=prompt,config=types.GenerateContentConfig(response_modalities=['AUDIO'],max_output_tokens=4096,speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Sulafat')))))
                parts=[p.inline_data for c in (result.candidates or []) for p in (c.content.parts or []) if p.inline_data and p.inline_data.data]
                if not parts:raise RuntimeError('No audio returned')
                pcm=b''.join(p.data for p in parts)
                with wave.open(str(dest),'wb') as w:
                    w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(pcm)
            except Exception as exc:
                print('GENERATION_ERROR',s['id'],type(exc).__name__,getattr(exc,'code',None),flush=True)
                error=getattr(exc,'details',{}) or {}
                details=error.get('error',error).get('details',[]) if isinstance(error,dict) else []
                safe=[]
                for detail in details:
                    if 'retryDelay' in detail:safe.append({'retryDelay':detail['retryDelay']})
                    for v in detail.get('violations',[]):safe.append({k:v[k] for k in ['quotaMetric','quotaId','quotaValue'] if k in v})
                print('LIMIT_DETAILS',json.dumps(safe),flush=True)
                print('LIMIT_STATUS',str(getattr(exc,'message',''))[:600].replace(key,'[REDACTED]'),flush=True)
                raise RuntimeError('Narration generation failed') from None
            finally:client.close()
        with wave.open(str(dest),'rb') as w:duration=w.getnframes()/w.getframerate()
        if not 3<duration<50:raise RuntimeError('Unexpected voice duration: '+s['id'])
        print('GENERATED',s['id'],round(duration,2),flush=True)
        return {**s,'voice_duration':duration,'voice':'Sulafat','file':str(dest.relative_to(OUT))}
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        futures=[pool.submit(generate,s) for s in SCENES]
        results=[];failed=[]
        for scene,future in zip(SCENES,futures):
            try:results.append(future.result())
            except RuntimeError:failed.append(scene['id'])
        if failed:
            print('INCOMPLETE',','.join(failed),flush=True)
            raise SystemExit(2)
    (OUT/'narration_generated.json').write_text(json.dumps({'model':'gemini-3.1-flash-tts-preview','voice':'Sulafat','style':'B warm female narrator','sections':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print('ALL 12 VOICES COMPLETE',flush=True)
if __name__=='__main__':main()
