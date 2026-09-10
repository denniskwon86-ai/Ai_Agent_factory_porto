"""Two short female voice auditions using ONLY the non-confidential generic text below.
Does not read or send any product narration, documents, database, screenshots or source code.
Uses the project's configured Gemini credential only to authenticate to Google's API.
"""
from pathlib import Path
import os,json,wave,sys
from dotenv import dotenv_values
from google import genai
from google.genai import types
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
TEXT='더 나은 변화는, 현장에서 시작됩니다. 오늘의 작은 경험이 쌓여, 내일의 선택을 바꿉니다. 이제, 다음 가능성을 만나보세요.'
STYLE='''Create a clean studio voice-over in Korean, by one experienced adult female Korean narrator.
Use native standard Seoul Korean pronunciation and a natural, grounded medium pitch.
Speak to one listener with composed confidence, clear diction and subtle human intonation.
Use a comfortable medium speaking pace with natural sentence-final falls and short breath pauses.
Keep meaningful phrases connected. Avoid syllable-by-syllable reading, a robotic sing-song cadence,
over-enunciation, exaggerated advertising excitement, whispers, vocal fry, or background music.
Read only the Korean script below exactly; do not read these directions or add words.
'''
VARIANTS=[('A_announcer','Kore','A calm, polished Korean female broadcast presenter introducing a documentary. Crisp but friendly, with restrained authority.'),
          ('B_warm_narrator','Sulafat','A warm, reassuring Korean female voice actor narrating a thoughtful brand film. Gently conversational, relaxed and sincere; a subtle smile in the voice.')]
def main():
 sys.stdout.reconfigure(encoding='utf-8');cfg=dotenv_values(ROOT/'.env');key=os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY') or cfg.get('GEMINI_API_KEY') or cfg.get('GOOGLE_API_KEY')
 if not key:raise RuntimeError('Configured Gemini credential unavailable')
 client=genai.Client(api_key=key,http_options=types.HttpOptions(timeout=90000));records=[]
 for name,voice,guide in VARIANTS:
  dest=OUT/f'{name}.wav';prompt=STYLE+'\nPerformance: '+guide+'\n\nSCRIPT:\n'+TEXT
  (OUT/f'{name}_prompt.txt').write_text(prompt,encoding='utf-8')
  if not dest.exists():
   try:
    result=client.models.generate_content(model='gemini-3.1-flash-tts-preview',contents=prompt,config=types.GenerateContentConfig(response_modalities=['AUDIO'],max_output_tokens=2048,speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
   except Exception as exc:
    print('GENERATION_ERROR',type(exc).__name__,getattr(exc,'code',None),flush=True);raise SystemExit(2)
   parts=[p.inline_data for c in (result.candidates or []) for p in (c.content.parts or []) if p.inline_data and p.inline_data.data]
   if not parts:raise RuntimeError('No generated audio returned')
   pcm=b''.join(p.data for p in parts)
   with wave.open(str(dest),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(pcm)
  with wave.open(str(dest),'rb') as w:duration=w.getnframes()/w.getframerate()
  records.append({'id':name,'voice':voice,'model':'gemini-3.1-flash-tts-preview','duration':duration,'script':TEXT,'file':dest.name})
  (OUT/'auditions.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8');print('GENERATED',name,round(duration,2),flush=True)
 client.close()
if __name__=='__main__':main()
