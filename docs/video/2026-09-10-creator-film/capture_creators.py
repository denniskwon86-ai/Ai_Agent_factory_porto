from pathlib import Path
import time,re,json,sys
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;CAP=OUT/'captures';CAP.mkdir(exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,str(OUT.parent/'2026-09-10-mainfilm'))
# Filming annotation only, not a product feature or data replacement.
CURSOR="""(()=>{let e=document.createElement('div');e.style.cssText='position:fixed;width:22px;height:22px;border:2px solid #00bacc;background:#00bacc22;border-radius:50%;pointer-events:none;z-index:2147483647;left:-50px;top:-50px;transform:translate(-50%,-50%)';document.body.append(e);document.addEventListener('mousemove',x=>{e.style.left=x.clientX+'px';e.style.top=x.clientY+'px'})})()"""
def hold(p,s):p.wait_for_timeout(s*1000)
def click(p,l):
 l.scroll_into_view_if_needed();b=l.bounding_box()
 if b:p.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=15)
 hold(p,.2);l.click()
manifest={};mp=OUT/'capture_manifest.json'
if mp.exists():manifest=json.loads(mp.read_text(encoding='utf-8'))
with sync_playwright() as pw:
 browser=pw.chromium.launch(channel='chrome',headless=True)
 for key in (sys.argv[1:] or ['software','agents','simulators']):
  c=browser.new_context(viewport={'width':1728,'height':810},storage_state=str(ROOT/'tmp/video-auth.json'),record_video_dir=str(CAP),record_video_size={'width':1728,'height':810})
  p=c.new_page();t0=time.monotonic();v=p.video
  p.goto('http://127.0.0.1:5173',wait_until='domcontentloaded');p.get_by_role('button',name='경영 홈',exact=True).wait_for();hold(p,.8);p.evaluate(CURSOR);events=[]
  def mark(t):events.append({'at':round(time.monotonic()-t0,3),'action':t})
  try:
   if key=='software':
    p.get_by_role('button',name='앱 제작',exact=True).click();hold(p,.8)
    p.get_by_role('button',name=re.compile('새 앱')).click();hold(p,.5)
    p.get_by_role('button',name=re.compile('일반 앱 제작')).click();hold(p,.5)
    start=time.monotonic()-t0;mark('새 업무 앱 생성 설정');hold(p,.7)
    name=p.get_by_placeholder('예: 원료 재고 부족 조기경보');click(p,name);name.press_sequentially('원료 도입 예외 관리',delay=90);hold(p,1.6)
    click(p,p.get_by_role('button',name='취소',exact=True));hold(p,.4)
    click(p,p.get_by_role('button',name=re.compile('CRM002')).first);click(p,p.get_by_role('button',name='열기',exact=True));hold(p,1.2)
    mark('기존 CRM002 제작 사례 조회');p.evaluate(CURSOR)
    click(p,p.get_by_role('button',name='📋 요구정의',exact=True));hold(p,2.5)
    click(p,p.get_by_role('button',name='📄 기획서',exact=True));mark('기존 요구정의·기획 산출물 조회');hold(p,8)
   elif key=='agents':
    p.get_by_role('button',name='에이전트',exact=True).click();hold(p,.8)
    p.get_by_role('button',name=re.compile('제조업 원가 분석')).click();hold(p,.6)
    p.get_by_role('tab',name=re.compile('^에이전트')).click();hold(p,.5)
    p.get_by_role('button',name=re.compile('새 에이전트')).click();hold(p,.5)
    start=time.monotonic()-t0;mark('현업 에이전트 생성 설정');hold(p,.5)
    name=p.get_by_placeholder('예: 원가 분석 에이전트');click(p,name);name.press_sequentially('원가 변동 원인 분석가',delay=75);hold(p,.7)
    click(p,p.get_by_role('button',name='에이전트 추가',exact=True));hold(p,.7);mark('브라우저 편집판에 새 에이전트 추가; 서버 저장 없음')
    role=p.get_by_placeholder('대략적인 역할을 적고 아래 AI 버튼을 누르면 자동 완성됩니다.');click(p,role);role.fill('계획 대비 실제 원가 차이를 분석하고, 원료 가격·수율·전력비의 영향과 조치안을 설명합니다.');hold(p,3)
    p.get_by_role('tab',name=re.compile('^실행 흐름')).click();hold(p,1);mark('선택한 템플릿 실행 흐름 확인');hold(p,7)
   else:
    p.get_by_role('button',name='시뮬레이션',exact=True).click();hold(p,.8)
    p.get_by_role('button',name=re.compile('새 시뮬레이터')).click();hold(p,.5)
    start=time.monotonic()-t0;mark('업무영역별 시뮬레이터 생성 설정');hold(p,.6)
    name=p.get_by_placeholder('예: 원료 재고 부족 조기경보');click(p,name);name.press_sequentially('생산팀 월간 생산계획 시뮬레이터',delay=65);hold(p,.5)
    sels=p.get_by_role('dialog').get_by_role('combobox');sels.nth(0).select_option(label='제조업 생산 계획 관리 (Manufacturing Production)')
    sels.nth(1).select_option(index=1);mark('생산 계획 절차와 인증 데이터 적용본 선택');hold(p,2.2)
    click(p,p.get_by_role('button',name='취소',exact=True));hold(p,.7)
    click(p,p.get_by_role('button',name=re.compile('제조 경영 시뮬레이션 실가동 검증')));hold(p,.7);mark('기존 시뮬레이터 운영 목록·사용실적 조회');hold(p,8)
   end=time.monotonic()-t0;p.screenshot(path=str(OUT/f'capture-{key}.jpg'));(OUT/f'capture-{key}.txt').write_text(p.locator('body').inner_text(),encoding='utf-8')
   c.close();path=CAP/f'{key}.webm';v.save_as(str(path))
   manifest[key]={'file':path.relative_to(OUT).as_posix(),'start':round(start,3),'duration':round(end-start,3),'actions':events,'disclosure':'실제 생성 설정 및 기존 제작 사례 조회. 신규 프로젝트 생성 실행·운영 반영 없음. 에이전트는 저장 전 브라우저 편집판.'}
   mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print('CAPTURED',key,round(end-start,2),flush=True)
  except Exception:
   p.screenshot(path=str(OUT/f'failure-{key}.jpg'));(OUT/f'failure-{key}.txt').write_text(p.locator('body').inner_text(),encoding='utf-8');c.close();raise
 browser.close()
