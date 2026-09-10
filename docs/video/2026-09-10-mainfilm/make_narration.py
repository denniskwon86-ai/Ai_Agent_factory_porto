"""소개용 대본만 Microsoft Edge 신경망 음성 서비스로 전송한다."""
import asyncio,json,sys,subprocess
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'tmp/laxs-video-deps'))
import edge_tts,imageio_ffmpeg

SECTIONS=[
 {'id':'01_question','title':'하나의 변화, 전사의 영향','text':'원료 도입이 늦어지면, 생산과 납기, 회사의 현금은 어떻게 달라질까요?'},
 {'id':'02_brand','title':'현업과 경영을 하나의 흐름으로','text':'랙스 엠은 현업의 실행과 경영의 판단을, 하나의 흐름으로 연결합니다.'},
 {'id':'03_home','title':'먼저 결정할 일을 확인합니다','text':'경영 홈에서 먼저 결정할 일을 살펴봅니다. 업무의 상태와 영향을, 같은 회사 문맥에서 확인합니다.'},
 {'id':'04_apps','title':'업무 앱에서 현장의 데이터를 확인합니다','text':'업무키트에서 원료 도입 앱을 엽니다. 발주와 선적 현황을 직접 조회하고, 같은 기준으로 업무의 진행 상태를 확인합니다.'},
 {'id':'05_knowledge','title':'업무의 관계가 회사 지식으로','text':'부서의 데이터는 따로 끝나지 않습니다. 구매와 재고, 생산과 판매의 관계를 연결해, 함께 쓸 회사 지식으로 쌓습니다.'},
 {'id':'06_simulation','title':'가정을 바꾸고 영향을 비교합니다','text':'이제 가정을 바꿔 봅니다. 원료 도입 지연과 환율 변화를 입력하면, 준비한 시연 기준선에서 생산과 손익, 현금의 영향을 비교합니다.'},
 {'id':'07_decision','title':'근거를 확인하고 사람이 결정합니다','text':'기존 의사결정 안건도 살펴봅니다. 요청자와 결정자, 영향 부서가 같은 근거를 보고, 책임 있는 사람이 결정합니다.'},
 {'id':'08_learning','title':'결정 이후의 결과까지 연결합니다','text':'결정 이후도 이어집니다. 실행 과제의 담당자와 기한을 확인하고, 기록된 효과를 다음 판단의 근거로 남깁니다.'},
 {'id':'09_close','title':'회사의 일과 경영 안에 AX를','text':'현업이 만들고, 전사가 연결하며, 경영이 판단합니다. 회사의 일과 경영에 에이엑스를 내재화하는, 랙스 엠.'},
]

async def main():
 (OUT/'audio').mkdir(exist_ok=True)
 ff=imageio_ffmpeg.get_ffmpeg_exe()
 for item in SECTIONS:
  target=OUT/'audio'/f"{item['id']}.mp3"
  if not target.exists() or item['id'] in ('04_apps','06_simulation','07_decision','08_learning'):
   comm=edge_tts.Communicate(item['text'],'ko-KR-SunHiNeural',rate='-4%',pitch='-2Hz')
   await comm.save(str(target))
  raw=subprocess.run([ff,'-v','error','-i',str(target),'-f','s16le','-ac','1','-ar','48000','-'],capture_output=True,check=True).stdout
  item['voice_duration']=len(raw)/96000
  item['duration']=round(item['voice_duration']+1.1,2)
  print(item['id'],item['voice_duration'],flush=True)
 (OUT/'narration.json').write_text(json.dumps({'voice':'ko-KR-SunHiNeural','rate':'-4%','pitch':'-2Hz','source':'Microsoft Edge online TTS','sections':SECTIONS,'total_duration':sum(x['duration'] for x in SECTIONS)},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':asyncio.run(main())
