"""Record real local product interactions using an authorized, normally logged-in session.
No data replacement, API stubs, certification, approvals or external publishing.
The turquoise cursor is a filming annotation only.
"""
from pathlib import Path
import sys,json,time,re
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
CAP=OUT/'captures';CAP.mkdir(exist_ok=True)
MAN=OUT/'capture_manifest.json'
manifest=json.loads(MAN.read_text(encoding='utf-8')) if MAN.exists() else {}
CURSOR="""(()=>{let d=document.createElement('div');d.id='film-cursor';d.style.cssText='position:fixed;width:23px;height:23px;border:2px solid #12bdcc;background:#12bdcc33;border-radius:50%;pointer-events:none;z-index:2147483647;left:-50px;top:-50px;transform:translate(-50%,-50%);box-shadow:0 0 0 4px #12bdcc16';document.body.appendChild(d);document.addEventListener('mousemove',e=>{d.style.left=e.clientX+'px';d.style.top=e.clientY+'px'});document.addEventListener('mousedown',()=>{d.style.background='#12bdccaa';setTimeout(()=>d.style.background='#12bdcc33',220)});})()"""
def hold(p,s):p.wait_for_timeout(s*1000)
def click(p,loc):
 loc.scroll_into_view_if_needed();bb=loc.bounding_box()
 if bb:p.mouse.move(bb['x']+bb['width']/2,bb['y']+bb['height']/2,steps=16)
 hold(p,.25);loc.click()
def top(p,name):
 p.get_by_role('button',name=name,exact=True).click();hold(p,.8)
def tab(p,name):click(p,p.get_by_role('tab',name=re.compile(name)))
def align(loc):loc.evaluate('(e)=>e.scrollIntoView({block:"start",behavior:"smooth"})')
def save_text(p,key):
 (OUT/f'capture-{key}.txt').write_text(p.locator('body').inner_text(),encoding='utf-8')
 p.screenshot(path=str(OUT/f'capture-{key}.jpg'))

with sync_playwright() as pw:
 browser=pw.chromium.launch(channel='chrome',headless=True)
 keys=sys.argv[1:] or ['03_home','04_apps','05_knowledge','06_simulation','07_decision','08_learning']
 for key in keys:
  ctx=browser.new_context(viewport={'width':1728,'height':810},storage_state=str(ROOT/'tmp/video-auth-scoped.json'),record_video_dir=str(CAP),record_video_size={'width':1728,'height':810})
  p=ctx.new_page();t0=time.monotonic();video=p.video
  p.goto('http://127.0.0.1:5173',wait_until='domcontentloaded');p.get_by_role('button',name='경영 홈',exact=True).wait_for();hold(p,1)
  p.evaluate(CURSOR);actions=[];crop=None;note='실제 제품 화면 · 시연 데이터'
  def mark(action):actions.append({'at':round(time.monotonic()-t0,3),'action':action})
  try:
   if key=='03_home':
    start=time.monotonic()-t0;mark('경영 홈 조회');hold(p,2)
    click(p,p.locator('.process').nth(3));mark('생산 단계 선택');hold(p,3)
    click(p,p.get_by_role('button',name='TWIN 예측',exact=True));mark('Twin 보조 정보 레이어 전환');hold(p,3)
    click(p,p.get_by_role('button',name='TWIN 예측',exact=True));hold(p,4)
   elif key=='04_apps':
    top(p,'앱 운영');align(p.get_by_label('선택한 앱 운영 상세'));hold(p,1)
    start=time.monotonic()-t0;mark('원료 도입 앱 운영 상태 확인');hold(p,1.3)
    click(p,p.get_by_role('button',name='앱 열기',exact=True));hold(p,1)
    align(p.get_by_role('button',name='발주 현황',exact=True));hold(p,1)
    mark('발주 현황 실제 데이터 조회');hold(p,3)
    click(p,p.get_by_role('button',name='선적 현황',exact=True));mark('선적 데이터 조회');hold(p,6)
    crop=[220,74,1208,566]
   elif key=='05_knowledge':
    p.get_by_role('button',name='전체 메뉴',exact=True).click();p.get_by_role('menuitem',name='업무 온톨로지',exact=False).click();hold(p,1)
    p.locator('.chip-row').get_by_role('button',name='승인',exact=True).click();hold(p,.7)
    graph=p.get_by_label('업무 온톨로지 상관 그래프');graph.scroll_into_view_if_needed();hold(p,2)
    p.locator('.react-flow__node').filter(has_text='선적 1').wait_for(state='visible',timeout=15000)
    p.locator('.react-flow__controls-fitview').click();hold(p,.7)
    start=time.monotonic()-t0;mark('실제 승인 관계 그래프 조회');hold(p,2)
    click(p,p.locator('.react-flow__node').filter(has_text='선적 1'));mark('선적 객체를 영향 경로 시작점으로 선택');hold(p,3)
    click(p,p.locator('.react-flow__node').filter(has_text='생산 계획행 2').first);mark('생산 객체 선택');hold(p,3)
    click(p,p.locator('.react-flow__controls-fitview'));mark('승인 관계 전체 보기');hold(p,5)
    crop=[220,74,1208,566]
   elif key=='06_simulation':
    top(p,'시뮬레이션');tab(p,'1. 기준선');p.get_by_role('button',name=re.compile('첫 수직 시연 — 비철 제련')).click();hold(p,.5)
    mark('기존 인증 판 7개를 명시적으로 선택')
    for i in range(7):p.get_by_role('checkbox').nth(i).check();hold(p,.12)
    vals={'생산량':'12000','기말재고':'2200','구매지급':'84000000000','기말현금':'52000000000','영업이익':'18000000000','전력비':'7200000000','기간':'30'}
    tab(p,'2. 기준값');hold(p,.8);mark('시연 기준값 수동 입력')
    for name,val in vals.items():
     field=p.get_by_role('textbox',name=re.compile('^'+name+r'\s*\('));click(p,field);field.fill(val);hold(p,.25)
    tab(p,'3. 변화 가정');hold(p,.8)
    start=time.monotonic()-t0;mark('변화 가정 입력 시작');hold(p,.8)
    for name,val in {'환율':'3.5','도입 지연':'12','전력단가':'8'}.items():
     field=p.get_by_role('textbox',name=re.compile('^'+name+r'\s*\('));click(p,field);field.press_sequentially(val,delay=100);hold(p,.15)
    click(p,p.get_by_role('button',name='시뮬레이션 실행',exact=True));mark('서버 시뮬레이션 실행')
    p.get_by_text('계산 완료',exact=True).wait_for(timeout=20000);tab(p,'4. 비교 결과');hold(p,.8);mark('실제 계산 결과 조회');hold(p,9)
    crop=[220,74,1208,566];note='실제 실행 · 시연 기준값 수동 입력'
   elif key=='07_decision':
    top(p,'결정·보고');p.get_by_role('button',name='전체',exact=True).click();hold(p,.5)
    start=time.monotonic()-t0;mark('기존 의사결정 안건 목록');hold(p,1)
    click(p,p.get_by_role('button',name=re.compile('원료 도입 지연 대응안과 생산')));hold(p,1)
    mark('기존 원료 도입 지연 대응 안건 열기');hold(p,2.5)
    click(p,p.get_by_role('button',name='영향부서 검토서',exact=True));mark('영향부서 관점으로 기존 근거 조회');hold(p,2.5)
    click(p,p.get_by_role('button',name='의사결정자 검토서',exact=True));mark('의사결정자 관점으로 조회');hold(p,6)
    crop=[220,74,1208,566];note='기존 안건 조회 · 시연 데이터'
   else:
    top(p,'결정·보고');p.get_by_role('button',name='전체',exact=True).click();hold(p,.4)
    p.get_by_role('button',name=re.compile('2공정 정련로')).click();hold(p,.7)
    align(p.get_by_text('결정 기록',exact=True));hold(p,.8)
    start=time.monotonic()-t0;mark('기존 조건부 승인 기록 조회');hold(p,3)
    align(p.get_by_text('실행과제와 효과',exact=True));mark('기존 실행 과제와 효과 기록 조회');hold(p,8)
    crop=[220,74,1208,566];note='기존 실행·효과 기록 · 시연 데이터'
   save_text(p,key);end=time.monotonic()-t0
   ctx.close();target=CAP/f'{key}.webm';video.save_as(str(target))
   manifest[key]={'file':target.relative_to(OUT).as_posix(),'start':round(start,3),'end':round(end,3),'crop':crop,'note':note,'actions':actions,'source':'Real local browser recording; no API or data stubs','viewport':[1728,810]}
   MAN.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
   print('RECORDED',key,'usable',round(end-start,2),'sec',flush=True)
  except Exception as exc:
   save_text(p,key+'-failure');ctx.close();print('FAILED',key,str(exc),flush=True);raise
 browser.close()
