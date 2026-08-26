# -*- coding: utf-8 -*-
"""경영 홈의 사용자 관측 계약.

브라우저에서 실제로 발견된 회귀를 소스 구조로 잠근다. 이 시험은 시각적 완성도를 대신하지
않지만, 회사명이 로그인 전 실패에 고착되거나 Jarvis 입력창이 본문 위에 다시 겹치는 식의
구조적 퇴행은 즉시 잡는다.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_로그인_뒤_회사명을_다시_읽는다():
    api = _read("frontend/src/lib/api.ts")
    ctx = _read("frontend/src/lib/operatingContext.ts")

    assert "factory:session-changed" in api
    assert "addEventListener('factory:session-changed'" in ctx
    assert "listTenants()" in ctx
    assert "getCompanyTree()" in ctx
    assert "node_type === 'legal_entity'" in ctx
    assert "realEntities.length === 1" in ctx


def test_로그인_세션의_tenant로_이전_브라우저_회사와_범위를_교체한다():
    app = _read("frontend/src/App.tsx")
    ctx = _read("frontend/src/lib/operatingContext.ts")

    assert "payload?.data?.tenant_id" in app
    assert "setEnterpriseContext({ tenantId: sessionTenant, scopeNodeId: '' })" in app
    assert "selected.tenantId !== sessionTenant" in ctx
    assert "setEnterpriseContext({ tenantId: sessionTenant, scopeNodeId: '' })" in ctx


def test_LAXS_확정_B안이_제품셸과_로그인에_적용되고_파비콘은_별도_마크를_쓴다():
    shell = _read("frontend/src/components/ProductShell.tsx")
    login = _read("frontend/src/components/LoginPage.tsx")
    index = _read("frontend/index.html")

    approved = '/brand/laxs-logo-primary-on-navy-v2.png'
    inverse = '/brand/laxs-logo-primary-on-white-v3.png'
    assert approved in shell
    assert '>AF</i>' not in shell
    assert inverse in login and approved not in login
    assert 'PRODUCT_NAME_KO' not in login
    assert 'href="/brand/laxs-mark-64.png"' in index
    assert (ROOT / "frontend/public/brand/laxs-logo-primary-on-navy-v2.png").is_file()
    assert (ROOT / "frontend/public/brand/laxs-mark-64.png").is_file()


def test_보조정보_카드의_두_텍스트_행은_카드_중앙에_정렬된다():
    css = _read("frontend/src/design/enterprise-canvas.css")

    assert ".le-canvas .overlay-item{position:relative;display:grid" in css
    assert "align-content:center;justify-items:stretch" in css
    assert ".overlay-item small, .le-canvas .overlay-item b{display:block;width:100%;text-align:center}" in css


def test_설치본_회사명은_기동시_회사_정본에_동기화된다():
    import json

    instance = json.loads(_read("data/instance.json"))
    runner = _read("run.py")

    assert instance["tenant_id"] == "tenant-afs-demo-materials"
    assert instance["company_name"] == "LS MnM"
    assert "apply_file(path)" in runner


def test_설치본_회사와_데이터_범위는_같은_tenant의_조직으로_선언된다():
    import json

    instance = json.loads(_read("data/instance.json"))
    org = instance["organization"]
    assert org["legal_node_id"] == "org-laxs-mnm"
    assert org["legal_dept_id"] == "hq"
    scopes = {row["node_id"]: row for row in org["scope_nodes"]}
    assert "plant-afs-smelting-01" in scopes
    assert "plant-afs-battery-02" in scopes
    assert scopes["plant-afs-smelting-01"]["dept_id"] == "demo_smelting"


def test_새_업무는_조직에_적용된_업무키트와_일반_제작을_명시적으로_가른다():
    dialog = _read("frontend/src/components/BuildStartDialog.tsx")
    app = _read("frontend/src/App.tsx")

    assert "'kit' | 'general'" in dialog
    assert "업무키트 기반 앱" in dialog
    assert "일반 앱 제작" in dialog
    assert "listInstances()" in dialog
    assert "<KitAppPanel instanceId={selected}" in dialog
    assert "적용본을 고르면 만들 수 있는 업무 앱" in dialog
    assert "onOpenDataPrep={() => { setBuildStart(false); setShowDataPrep(true); }}" in app
    assert 'placeholder="kit_instance_id' not in dialog


def test_업무키트_앱은_새업무_창뿐_아니라_앱운영에서_직접_찾고_연다():
    app = _read("frontend/src/App.tsx")
    panel = _read("frontend/src/components/KitOperationsPanel.tsx")
    kit_apps = _read("frontend/src/components/KitAppPanel.tsx")

    assert "if (id === 'operate') { setShowKitOperations(true); return; }" in app
    assert "<KitOperationsPanel" in app
    assert "listInstances()" in panel
    assert '<KitAppPanel instanceId={selected} mode="operate" />' in panel
    assert "현재 운영 가능한 앱" in panel
    assert "새 업무키트 앱 만들기" in panel
    assert "mode === 'build' ? '키트로 앱 만들기' : '업무 앱 운영'" in kit_apps
    assert "운영 중인 앱을 열고, 후보 앱의 운영 전환 상태를 확인합니다." in kit_apps


def test_회사문맥_화면에서_조직을_실제_실행범위로_전환할_수_있다():
    org = _read("frontend/src/components/OrgChartPanel.tsx")

    assert "이 조직으로 전환" in org
    assert "setEnterpriseContext({ scopeNodeId });" in org
    assert "disabled={!String(selectedDept.scope_node_id || '').trim()}" in org
    assert "window.location.reload();" in org


def test_릴리스_카드는_키트_앱_이름과_운영상태를_앞세우고_내부_id는_접는다():
    page = _read("frontend/src/components/BuildPage.tsx")

    assert "listKitApps" in page
    assert "kitApp?.label || r.project_name" in page
    assert "업무 앱 {kitApp.app_id}" in page
    assert "운영 중" in page and "운영 후보" in page
    assert "게시 {localTime(r.created_at)}" in page
    assert "<summary style={{ cursor: 'pointer' }}>식별 정보</summary>" in page
    assert ">앱 실행</button>" in page
    assert ">릴리스 관리</button>" in page


def test_릴리스_관리도_사람용_이름_상태_시각을_우선하고_감사원문은_보존한다():
    page = _read("frontend/src/components/BuildPage.tsx")
    app = _read("frontend/src/App.tsx")
    admin = _read("frontend/src/components/ProgramAdminPanel.tsx")

    assert "display_name: displayName" in page
    assert "r.display_name || r.project_name || r.release_id" in app
    assert 'kicker="프로그램"' in admin
    assert 'kicker="상태"' in admin
    assert 'kicker="영향 범위"' in admin
    assert 'kicker="상태 변경"' in admin
    assert 'kicker="변경 이력"' in admin
    assert "localTime(data!.changed_at)" in admin
    assert "actorLabel(data!.changed_by, actorNames)" in admin
    assert "title={data!.changed_by}" in admin
    assert "candidate: '운영 후보'" in admin
    assert "historyStatusLabel(h.from_status)" in admin
    assert "historyStatusLabel(h.to_status)" in admin
    assert "<summary className=\"afs-muted\" style={{ cursor: 'pointer' }}>식별 정보</summary>" in admin


def test_프로젝트_제작_화면은_사람용_명칭과_자비스_역할을_쓴다():
    app = _read("frontend/src/App.tsx")
    control = _read("frontend/src/components/ControlPanel.tsx")
    timeline = _read("frontend/src/components/TimelinePanel.tsx")
    flow = _read("frontend/src/components/WorkflowStrip.tsx")
    preview = _read("frontend/src/components/PreviewPanel.tsx")
    hotl = _read("frontend/src/components/HOTLInput.tsx")

    assert "· 앱 제작 작업공간" in app
    assert "◀ 앱 목록" in app
    assert "🧪 병렬 검증" in app
    assert "⚙️ 작업 실행" in control
    assert "❌ 실패" in control and '"TODO"' not in control
    assert "🧭 자비스 · AI 제작 감독" in timeline
    assert "🔭 제작 단계" in flow
    assert "🖥️ 앱 미리보기" in preview
    assert "자비스에게 질문·지시" in hotl
    assert "Target Task:" not in hotl


def test_앱_제작_프로젝트는_URL로_새로고침_복원된다():
    app = _read("frontend/src/App.tsx")

    assert "new URLSearchParams(window.location.search).get('project')" in app
    assert "setCurrentProject(initialProject.current)" in app
    assert "next.searchParams.set('space', 'build')" in app
    assert "next.searchParams.set('project', currentProjectId)" in app
    assert "window.history.replaceState" in app


def test_비서의_화면_이름은_Jarvis_한곳에서_관리한다():
    brand = _read("frontend/src/lib/brand.ts")
    rail = _read("frontend/src/components/CanvasJarvisRail.tsx")

    assert "ASSISTANT_NAME = '자비스'" in brand
    assert "<b>{ASSISTANT_NAME}</b>" in rail
    assert "회사 전체를 이해하는 AI 경영비서" in rail


def test_선택한_빠른질문으로_강조가_이동한다():
    rail = _read("frontend/src/components/CanvasJarvisRail.tsx")
    css = _read("frontend/src/design/enterprise-canvas.css")

    assert "setSelectedAction(q)" in rail
    assert "aria-pressed={selectedAction === q}" in rail
    assert ".atlas-actions button.selected" in css
    assert ".atlas-actions button.recommend" not in css


def test_대화_본문과_입력창은_서로_다른_그리드_행이다():
    rail = _read("frontend/src/components/CanvasJarvisRail.tsx")
    css = _read("frontend/src/design/enterprise-canvas.css")

    assert 'style={{ paddingBottom: 104 }}' not in rail
    assert "grid-template-rows:auto minmax(0,1fr) auto" in css
    assert ".le-canvas .atlas-input{position:static" in css
    assert ".le-canvas .atlas-body{min-height:0" in css


def test_Digital_Thread는_장식_점선이_아니라_회사별_구성이다():
    page = _read("frontend/src/components/EnterprisePage.tsx")
    css = _read("frontend/src/design/enterprise-canvas.css")

    assert '회사 등록 · 연결구성' in page
    assert "onOpenMenu('company')" in page
    assert "회사별 승인 구성" in page
    assert 'className="flow-live"' in page
    assert 'className="flow-pulse"' in page
    assert 'className="flow-data"' not in page
    assert ".flow-live{" in css
    assert ".flow-pulse{" in css
    assert ".flow-data{" not in css
    assert "@media (prefers-reduced-motion:reduce)" in css
    assert "gridTemplateColumns: `repeat(${processCount}" in page


def test_회사_구성_저장_뒤_홈이_즉시_갱신된다():
    panel = _read("frontend/src/components/CompanySetupPanel.tsx")
    page = _read("frontend/src/components/EnterprisePage.tsx")

    event = "factory:company-configuration-changed"
    assert f"new CustomEvent('{event}')" in panel
    assert f"addEventListener('{event}'" in page


def test_업무_연결구성에_현재_회사와_대상_법인이_보인다():
    panel = _read("frontend/src/components/CompanySetupPanel.tsx")

    assert 'title="현재 회사와 적용 구성"' in panel
    assert "현재 회사" in panel
    assert "현재 문맥" in panel
    assert "연결구성 대상" in panel
    assert "findNodePath" in panel
    assert "node_type === 'legal_entity'" in panel


def test_현재_회사_승인구성과_편집초안이_한_화면에서_이어진다():
    panel = _read("frontend/src/components/CompanySetupPanel.tsx")
    api = _read("frontend/src/lib/companyApi.ts")
    page = _read("frontend/src/components/EnterprisePage.tsx")
    css = _read("frontend/src/design/afs.css")

    assert "COMPANY_SCOPE = '__company__'" in panel
    assert 'title="현재 회사와 적용 구성"' in panel
    assert "현재 적용 중인 연결구성" in panel
    assert "회사 전체 ·" in panel
    assert "fetchCanvas()" in panel, "홈 기본 흐름과 편집 초안이 다른 원천이면 안 된다"
    assert "편집 초안 저장" in panel
    assert "승인하고 홈에 적용" in panel
    assert "이 단계의 역할·설명" in panel
    assert 'className="afs-dialog-body company-setup-body"' in panel
    assert 'className="company-thread-actions"' in panel
    assert ".company-thread-actions" in css
    action_css = css.split(".company-thread-actions", 1)[1].split("}", 1)[0]
    assert "position: sticky" not in action_css
    assert "company_wide" in api
    assert "listProfiles('', 'process_profile', true)" in page


def test_긴_결정_내용은_상단_컨트롤을_밀지_않고_패널_안에서_스크롤된다():
    page = _read("frontend/src/components/EnterprisePage.tsx")
    css = _read("frontend/src/design/enterprise-canvas.css")

    panel_css = css.split(".le-canvas .focus-panel", 1)[1].split("}", 1)[0]
    copy_css = css.split(".le-canvas .focus-copy{", 1)[1].split("}", 1)[0]
    content_css = css.split(".le-canvas .focus-content{", 1)[1].split("}", 1)[0]
    assert 'className="focus-content"' in page
    assert "height:210px" in panel_css
    assert "overflow:hidden" in panel_css
    assert "min-height:0" in copy_css
    assert "overflow:hidden" in copy_css
    assert "overflow-y:auto" in content_css
    assert "flex:0 0 auto" in css, "해결 버튼은 스크롤 내용 밖에서 항상 보여야 한다"


def test_DATA_SW_TWIN은_업무단계가_아니라_보조정보_레이어로_설명된다():
    page = _read("frontend/src/components/EnterprisePage.tsx")

    assert "DATA 근거" in page
    assert "SW 도구" in page
    assert "TWIN 예측" in page
    assert 'aria-label="업무 흐름 위에 표시할 보조 정보 레이어"' in page
    assert "aria-pressed={layers.includes(l.id)}" in page
    assert "overlaySlots" in page
    assert "data-node-key" in page
    assert "gridTemplateColumns: `repeat(${processCount}" in page


def test_모든_업무단계는_보조정보가_없어도_빈_카드_구역을_유지한다():
    page = _read("frontend/src/components/EnterprisePage.tsx")
    css = _read("frontend/src/design/enterprise-canvas.css")

    assert "const overlaySlots: (ThreadOverlay | null)[] = processKeys.map" in page
    assert 'className="overlay-item empty"' in page
    assert "등록된 정보 없음" in page
    assert "DEFAULT_THREAD_OVERLAY_BY_NODE[key] || null" in page
    assert ".le-canvas .overlay-item.empty{" in css


def test_회사별_연결구성에서_단계별_보조정보를_편집하고_같은_프로필에_저장한다():
    panel = _read("frontend/src/components/CompanySetupPanel.tsx")
    api = _read("frontend/src/lib/companyApi.ts")

    assert "overlay?: ThreadOverlay" in api
    assert "DEFAULT_THREAD_OVERLAY_BY_NODE" in api
    assert "＋ 보조정보 카드 연결" in panel
    assert "카드 삭제" in panel
    assert "DATA 근거" in panel and "SW 도구" in panel and "TWIN 예측" in panel
    assert "node.overlay = r.overlay ?" in panel
    assert "overlay: null" in panel, "삭제한 카드가 기본값으로 되살아나면 안 된다"
    assert "payload: { nodes: rows.map" in panel
