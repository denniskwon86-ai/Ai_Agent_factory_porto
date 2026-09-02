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
    auth = _read("api/routes/auth_control.py")

    assert "factory:session-changed" in api
    assert '"company_name": _effective_company_name()' in auth
    assert "String(me?.company_name || '').trim()" in ctx
    assert "COMPANY_NAME_CACHE_KEY = 'factory.companyNameByTenant'" in ctx
    assert "verifiedCompanyName || cachedCompanyName(company)" in ctx
    assert "addEventListener('factory:session-changed'" in ctx
    assert "listTenants()" in ctx
    assert "getCompanyTree()" in ctx
    assert "node_type === 'legal_entity'" in ctx
    assert "path[path.length - 1]?.entity_id" in ctx
    assert "realEntities.find((e) => e.entity_id === entityId)" in ctx
    assert "realEntities.length === 1" in ctx


def test_상단_회사문맥은_조직도_관리와_분리된_검증형_선택기를_연다():
    app = _read("frontend/src/App.tsx")
    switcher = _read("frontend/src/components/OperatingContextSwitcher.tsx")

    assert "onContext={() => setShowContextSwitcher(true)}" in app
    assert "onContext={() => setShowOrgChart(true)}" not in app
    assert "selectContext(scopeNodeId" in switcher
    assert "verifiedScope !== scopeNodeId" in switcher
    assert "setEnterpriseContext({" in switcher
    assert "window.location.reload()" not in switcher
    assert "조직 코드를 직접 입력하지 않습니다" in switcher


def test_1280_제품셸은_사용자이름만_접고_핵심행동을_화면안에_남긴다():
    session = _read("frontend/src/components/SessionBar.tsx")
    shell_css = _read("frontend/src/design/product-shell.css")

    assert 'className="afs-session-name afs-muted"' in session
    assert "title={me ? (me.display_name || me.user_id) : '사용자 확인 중'}" in session
    assert ".afs-session-name { max-width: 48px !important; }" in shell_css
    assert "grid-template-columns: 160px 210px minmax(405px, 1fr) auto" in shell_css
    assert "gap: 6px;" in shell_css
    assert 'aria-label="로그아웃"' in session
    assert "＋ 새 업무" in _read("frontend/src/components/ProductShell.tsx")


def test_AI스킬_승인은_데이터관리자가_아니라_서버의_AI권한정본을_쓴다():
    scope = _read("frontend/src/lib/actingScope.ts")
    panel = _read("frontend/src/components/SkillEvolutionPanel.tsx")
    route = _read("api/routes/skill_control.py")

    assert "adminCapabilities" in scope
    assert "d?.admin?.capabilities" in scope
    assert "adminCapabilities.includes('skill.approve')" in panel
    assert "canManageStandard || scope?.unrestricted" not in panel
    assert "require_caps(p, SKILL_APPROVE" in route
    assert "assert_can_manage_standard(p)" not in route


def test_Viewer에게_온톨로지와_대외정보_쓰기버튼을_활성으로_약속하지_않는다():
    ontology = _read("frontend/src/components/OntologyExplorerView.tsx")
    external = _read("frontend/src/components/ExternalIntelligenceView.tsx")

    assert "disabled={proposalContext.status !== 'ok' || !proposalContext.value?.ready}" in ontology
    assert "const canManage = Boolean(scope?.canManageStandard || scope?.unrestricted)" in external
    assert 'title="조회만 가능합니다"' in external
    assert "const canWrite = canManage && !loadUnavailable" in external
    assert 'disabled={!canWrite}' in external
    assert "<fieldset disabled={!canWrite}" in external
    assert "canWrite && showResearchForm" in external
    assert "canWrite && showSourceForm" in external
    assert "canWrite && showObservationForm" in external


def test_대외정보_조회장애는_0건이나_기술문구로_보이지_않고_쓰기를_차단한다():
    state = _read("frontend/src/design/DataState.tsx")
    external = _read("frontend/src/components/ExternalIntelligenceView.tsx")

    assert "failed to fetch|networkerror|network request failed|load failed" in state
    assert "현재 서비스에 연결할 수 없습니다" in state
    assert "const loadUnavailable = [ready, indicators, sources, collectable, researchProfiles" in external
    assert "const canWrite = canManage && !loadUnavailable" in external
    assert "화면의 수치는 0건이 아니라 조회 불가 상태입니다" in external
    assert "disabled={!canWrite}" in external
    assert "<fieldset disabled={!canWrite}" in external
    assert "ready.status === 'loading' ? '확인 중' : '조회 불가'" in external


def test_회사문맥_변경은_온톨로지의_객체와_관계_양쪽을_다시_읽는다():
    ontology = _read("frontend/src/components/OntologyExplorerView.tsx")

    assert "addEventListener('factory:enterprise-context-changed', refresh)" in ontology
    assert "const refresh = () => { load(); loadGovernance(); };" in ontology


def test_업무_온톨로지는_표뿐_아니라_실제_조회관계를_상관그래프로_보여준다():
    view = _read("frontend/src/components/OntologyExplorerView.tsx")
    graph = _read("frontend/src/components/OntologyGraphPanel.tsx")

    assert '<OntologyGraphPanel relations={relationRows}' in view
    assert 'aria-label="업무 온톨로지 상관 그래프"' in graph
    assert "onSelectRoot(node.data.ref as OntologyObject)" in graph
    assert "onSelectRelation(String(edge.data?.relationId || edge.id))" in graph
    assert "현재 조회 조건에서 시각화할 관계가 없습니다" in graph
    assert "보이지 않는 관계의 존재나 수를" in view
    assert "relations: OntologyRelation[]" in graph


def test_회사문맥_변경은_업무키트_목록과_열린_앱을_새_증명으로_다시_읽는다():
    operations = _read("frontend/src/components/KitOperationsPanel.tsx")
    app_panel = _read("frontend/src/components/KitAppPanel.tsx")

    assert "addEventListener('factory:enterprise-context-changed', refresh)" in operations
    assert "setRevision((value) => value + 1)" in operations
    assert "next.tenantId !== contextRef.current.tenantId" in operations
    assert "addEventListener('factory:enterprise-context-changed', refresh)" in app_panel
    assert "proofRef.current = ''" in app_panel
    assert "if (open) void load()" in app_panel


def test_계산승인화면은_살아있는_승인을_승인없음으로_표시하지_않는다():
    panel = _read("frontend/src/components/CalcApprovalPanel.tsx")

    assert "activeApprovalCount" in panel
    assert "현재 ${activeApprovalCount}건이 실행 승인되어 있습니다" in panel
    assert 'title="아직 아무것도 승인되지 않았습니다"' not in panel


def test_경로계산_객체재조회가_성공하면_이전_실패표시를_지운다():
    panel = _read("frontend/src/components/PathCalcPanel.tsx")

    success = panel.index("const got = await listOntologyObjects")
    clear = panel.index("setError(null);", success)
    populate = panel.index("setObjects(got.objects);", success)
    assert success < clear < populate


def test_경로계산_기한은_내장_날짜선택기의_input_commit도_받는다():
    panel = _read("frontend/src/components/PathCalcPanel.tsx")

    assert 'type="date" value={due}' in panel
    assert "onInput={(e) => setDue((e.target as HTMLInputElement).value)}" in panel
    assert "onChange={(e) => setDue(e.target.value)}" in panel


def test_경로계산_안건을_시뮬레이션_연결없음으로_오표시하지_않는다():
    center = _read("frontend/src/features/collaboration/DecisionCenter.tsx")
    hub = _read("frontend/src/features/collaboration/CollaborationHub.tsx")

    assert "d.evidence?.query_id" in center
    assert "'업무 영향 경로 계산'" in center
    assert "queryId.slice(0, 14)" not in center
    assert "시뮬레이션 ${d.simulation_run_id || '(연결 없음)'}" not in center
    assert "시뮬레이션 결과를 하나의 Decision Package" not in center
    assert "시뮬레이션 결과를 하나의 문서" not in center
    assert "시뮬레이션·경로 계산 결과" in hub


def test_결정과_발간은_구조화값을_JSON_한줄이_아닌_공통_카드로_보여준다():
    decision = _read("frontend/src/features/collaboration/DecisionCenter.tsx")
    publication = _read("frontend/src/features/collaboration/PublicationCenter.tsx")
    renderer = _read("frontend/src/design/StructuredValue.tsx")
    css = _read("frontend/src/design/afs.css")

    assert "<StructuredValue value={s.value}" in decision
    assert "<StructuredValue value={v}" in publication
    assert "JSON.stringify" not in decision
    assert "JSON.stringify" not in publication
    assert "structured-value-card" in renderer
    assert "delta_pct: '변화율'" in renderer
    assert ".structured-value-kv > div" in css
    assert "internalReference(key)" in renderer
    assert "key.endsWith('_id')" in renderer
    assert "key.endsWith('_ids')" in renderer
    assert "key.endsWith('_code')" in renderer
    assert "`${value.length}개 결속됨`" in renderer
    assert "key === 'key' && typeof record.label === 'string'" in renderer


def test_발간물_대량목록은_전체건수를_유지한채_20건씩_나눠_보여준다():
    publication = _read("frontend/src/features/collaboration/PublicationCenter.tsx")
    css = _read("frontend/src/design/afs.css")

    assert "const pageSize = 20" in publication
    assert "const pageRows = shown.slice" in publication
    assert "{pageRows.map((p)" in publication
    assert 'aria-label="발간물 목록 페이지"' in publication
    assert "Math.min(safePage * pageSize, shown.length)" in publication
    assert ".list-pagination" in css


def test_로그인_세션의_tenant로_이전_브라우저_회사와_범위를_교체한다():
    app = _read("frontend/src/App.tsx")
    ctx = _read("frontend/src/lib/operatingContext.ts")

    assert "payload?.data?.tenant_id" in app
    assert "setEnterpriseContext({ tenantId: sessionTenant, scopeNodeId: '' })" in app
    assert "selected.tenantId !== sessionTenant" in ctx
    assert "setEnterpriseContext({ tenantId: sessionTenant, scopeNodeId: '' })" in ctx


def test_백엔드_연결장애는_로그아웃이나_빈화면으로_오인시키지_않는다():
    app = _read("frontend/src/App.tsx")

    assert "'checking' | 'in' | 'out' | 'offline'" in app
    assert "setState('offline')" in app
    assert 'aria-label="서비스 연결 장애"' in app
    assert "저장된 로그인 정보는 유지됩니다" in app
    assert "비밀번호를 다시 입력할 필요가 없습니다" in app
    assert ">\n            다시 연결하기\n          </button>" in app
    offline = app[app.index("if (state === 'offline')"):app.index("if (state === 'out')")]
    assert '<LoginPage' not in offline


def test_화면_실행오류는_내부스택을_노출하지_않고_복구행동을_제공한다():
    boundary = _read("frontend/src/components/ErrorBoundary.tsx")

    assert 'aria-label="화면 표시 오류"' in boundary
    assert "저장된 업무 데이터가 삭제된 것은 아닙니다" in boundary
    assert "경영 홈으로" in boundary and "다시 시도" in boundary
    assert 'window.location.href = "/?space=enterprise"' in boundary
    assert "this.state.error?.stack" not in boundary
    assert "System Crash Prevented" not in boundary


def test_LAXS_확정_B안이_제품셸과_로그인에_적용되고_파비콘은_별도_마크를_쓴다():
    shell = _read("frontend/src/components/ProductShell.tsx")
    login = _read("frontend/src/components/LoginPage.tsx")
    index = _read("frontend/index.html")

    approved = '/brand/laxs-logo-primary-on-navy-v2.png'
    inverse = '/brand/laxs-logo-primary-on-white-v5.png'
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

    assert "if (id === 'operate') { setShowKitOperations(false); setSpace('operate'); return; }" in app
    assert "<KitOperationsPanel" in app
    assert "listInstances()" in panel
    assert '<KitAppPanel instanceId={selected} mode="operate" statusFilter={view}' in panel
    assert 'onOpenSimulation={onOpenSimulation}' in panel
    assert "현재 회사의 업무 앱" in panel
    assert "＋ 새 업무키트 앱" in panel
    assert '<ProductShell module="operate"' in app
    assert "<KitOperationsPanel page" in app
    assert "OPERATIONS_ITEMS" in panel
    assert "운영 전환', hint: '검토·승격이 필요한 앱'" in panel
    assert 'statusFilter={view}' in panel
    assert "aria-pressed={on}" in panel
    assert "mode === 'build' ? '키트로 앱 만들기' : '앱 현황'" in kit_apps
    assert "운영 중인 앱을 열고, 후보 앱의 운영 전환 상태를 확인합니다." in kit_apps
    assert "contextLabel(row.entity_mode)" in panel
    assert "instanceStatusLabel(row.status)" in panel
    assert 'aria-label="앱 운영 상태 요약"' in kit_apps
    assert 'className="afs-master-detail"' in kit_apps
    assert 'aria-label="업무 앱 목록"' in kit_apps
    assert 'aria-label="선택한 앱 운영 상세"' in kit_apps
    assert "setSelectedAppId(row.app_id)" in kit_apps
    assert "운영 전환 필요" in kit_apps
    assert "운영 전환 검토" in kit_apps
    assert "setShowPromotion(false)" in kit_apps
    assert "shownRows.map" in kit_apps
    assert "setRevision((value) => value + 1)" in panel
    assert "setTick((value) => value + 1)" in kit_apps


def test_앱제작과_앱운영은_같은_목록_상세_탐색문법을_쓴다():
    build = _read("frontend/src/components/BuildPage.tsx")
    operate = _read("frontend/src/components/KitAppPanel.tsx")

    assert 'className="afs-master-detail"' in build
    assert 'aria-label={bucket === \'releases\' ? \'릴리스 목록\' : \'제작 프로젝트 목록\'}' in build
    assert "setSelectedKey(project.id)" in build
    assert "setSelectedKey(releaseId)" in build
    assert "selectedProject &&" in build
    assert "selectedRelease &&" in build
    assert 'className="afs-master-detail"' in operate
    assert 'aria-label="업무 앱 목록"' in operate


def test_시뮬레이션은_공통셸_아래_조건과_결과가_나뉜_독립화면이다():
    app = _read("frontend/src/App.tsx")
    scenario = _read("frontend/src/components/ScenarioPanel.tsx")

    assert "| 'twin'" in app
    assert "if (id === 'twin') { setShowScenario(false); setSpace('twin'); return; }" in app
    assert 'space === \'twin\'' in app
    assert '<ProductShell module="twin"' in app
    assert '<ScenarioPanel page' in app
    assert 'className="scenario-workspace"' in scenario
    assert 'aria-label="시나리오 조건 설정"' in scenario
    assert 'aria-label="시뮬레이션 비교 결과"' in scenario
    assert "실행 전에는 결과를 0이나 빈 차트로 그리지 않습니다" in scenario


def test_앱제작_앱운영_시뮬레이션은_좌측메뉴_본문_자비스_3열을_공유한다():
    build = _read("frontend/src/components/BuildPage.tsx")
    operate = _read("frontend/src/components/KitOperationsPanel.tsx")
    scenario = _read("frontend/src/components/ScenarioPanel.tsx")
    shell = _read("frontend/src/design/HubShell.tsx")
    css = _read("frontend/src/design/afs.css")

    for source in (build, operate, scenario):
        assert '<HubShell layoutClassName="product-page-shell' in source
        assert '<JarvisRail' in source

    assert "items={railItems} activeId={bucket}" in build
    assert "items={railItems} activeId={view}" in operate
    assert "items={SCENARIO_ITEMS} activeId={stage}" in scenario
    assert "layoutClassName?: string" in shell
    assert ".hub-layout.product-page-shell" in css
    assert ".product-page-shell > .jarvis-rail { display: flex; }" in css
    assert "grid-template-columns: 220px minmax(0, 1fr) 300px" in css
    assert "grid-template-columns: 190px minmax(0, 1fr) 280px" in css


def test_제품화면_자비스는_정보구조와_넓은_질문입력을_유지한다():
    rail = _read("frontend/src/design/JarvisRail.tsx")
    css = _read("frontend/src/design/afs.css")

    assert "LAXS-M · AI 경영비서" in rail
    assert "jarvis-context" in rail
    assert "jarvis-evidence" in rail
    assert "jarvis-zero-quick" in rail
    assert "현재 화면과 선택한 객체에 대해 질문하세요." in rail
    assert ".product-page-shell > .jarvis-rail .jarvis-input" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css
    assert "turns.length ? log.scrollHeight : 0" in rail


def test_업무키트_조회실패는_0건으로_접지_않고_화면에서_다시_확인한다():
    dialog = _read("frontend/src/components/BuildStartDialog.tsx")

    assert "const [revision, setRevision] = useState(0);" in dialog
    assert "setError(null);" in dialog
    assert "if (rows.length === 1) setSelected" in dialog
    assert "다시 확인" in dialog
    assert "setRevision((value) => value + 1)" in dialog


def test_계약작성자는_승인버튼을_눌러서야_자기승인_불가를_알게하지_않는다():
    panel = _read("frontend/src/components/KitAppPanel.tsx")

    assert "apiFetch('/api/v1/auth/me')" in panel
    assert "currentUser === row.drafted_by" in panel
    assert "현재 로그인 사용자가 계약 작성자입니다" in panel
    assert "disabled={draftedByCurrentUser}" in panel
    assert "disabled={draftedByCurrentUser || !rationale.trim()" in panel


def test_회사문맥_화면에서_조직을_실제_실행범위로_전환할_수_있다():
    org = _read("frontend/src/components/OrgChartPanel.tsx")

    assert "이 조직으로 전환" in org
    assert "setEnterpriseContext({ scopeNodeId });" in org
    assert "disabled={!String(selectedDept.scope_node_id || '').trim()}" in org
    assert "window.location.reload();" in org


def test_릴리스_상세는_키트_앱_이름과_운영상태를_앞세우고_내부_id는_접는다():
    page = _read("frontend/src/components/BuildPage.tsx")

    assert "listKitApps" in page
    assert "kitApp?.label || row.project_name" in page
    assert "kitApp?.label || selectedRelease.project_name" in page
    assert "업무 앱 {kitApp.app_id}" not in page
    assert "{selectedRelease.release_id}" not in page
    assert "{selectedProject.id}" not in page
    assert "운영 중" in page and "운영 후보" in page
    assert "게시 {localTime(selectedRelease.created_at)}" in page
    assert "<summary style={{ cursor: 'pointer' }}>식별 정보</summary>" not in page
    assert ">앱 실행</button>" in page
    assert ">릴리스 관리</button>" in page


def test_워크스페이스는_릴리스와_프로젝트_id를_직접_입력받지_않는다():
    panel = _read("frontend/src/components/WorkspacePanel.tsx")
    app = _read("frontend/src/App.tsx")

    assert 'aria-label="점검할 릴리스"' in panel
    assert 'placeholder="release_id"' not in panel
    assert 'placeholder="project_id' not in panel
    assert "releaseOptions.find" in panel
    assert "releaseOptions={releases.filter" in app
    assert 'aria-label="소유 조직"' in panel
    assert 'aria-label="공유 대상 조직"' in panel
    assert 'placeholder="소유 조직"' not in panel
    assert 'placeholder="공유 대상 조직"' not in panel
    assert "scopeLabel(s.to_scope)" in panel


def test_협업_전달은_사람용_릴리스_이름을_선택하고_내부_id를_보이지_않는다():
    hub = _read("frontend/src/features/collaboration/CollaborationHub.tsx")

    assert "releaseOptions: CollaborationReleaseOption[]" in hub
    assert "r.label || '이름 미등록 앱'" in hub
    assert 'placeholder="release_id"' not in hub
    assert "{d.release_id}</b>" not in hub
    assert "{a.release_id} ·" not in hub
    assert "받는 사람 계정" not in hub
    assert "조직 사용자 선택" in hub
    assert "orgApi.users()" in hub
    assert "계정 코드를 직접 입력해 우회할 수 없습니다" in hub
    assert "{d.sender_user_id}</b>" not in hub
    assert "{d.recipient_user_id}</b>" not in hub
    assert "{a.source_user_id || '확인 불가'}" not in hub
    assert "userName(d.sender_user_id)" in hub
    assert "userName(d.recipient_user_id)" in hub
    assert "deptName(d.sender_dept_id)" in hub


def test_발간화면은_원천과_검토자를_내부_id가_아닌_사람용_이름으로_보여준다():
    publication = _read("frontend/src/features/collaboration/PublicationCenter.tsx")
    hub = _read("frontend/src/features/collaboration/CollaborationHub.tsx")

    assert "<PublicationCenter onJarvis={setPubCtx} userName={userName}" in hub
    assert "decisionNames.get(p.source_id)" in publication
    assert "description={`${PUB_TYPE_KO[p.publication_type] || p.publication_type} · 원천 ${sourceName}`}" in publication
    assert "userName(r.reviewer_id)" in publication
    assert "원본({p.supersedes_id})" not in publication
    assert "${current.source_type} ${current.source_id}" not in publication


def test_경영계획은_조직_시나리오_계정코드를_사람용_이름으로_대체한다():
    panel = _read("frontend/src/components/PlanningPanel.tsx")

    assert 'placeholder="조직 코드"' not in panel
    assert 'aria-label="계획 조직"' in panel
    assert "fetchOrgNodeOptions()" in panel
    assert "candidate.code === id || candidate.node_id === id" in panel
    assert "조직 코드를 직접 입력해 우회할 수 없습니다" in panel
    assert "{s.scenario_id}</span>" not in panel
    assert "scenarioNames.get(s.scenario_id)" in panel
    assert "<td>{r.account_code}</td>" not in panel
    assert "accountName(r.account_code)" in panel
    assert "approverName(apprV.approved_by)" in panel


def test_에이전트_거버넌스는_조직과_사람과_자산_id를_표시명으로_대체한다():
    panel = _read("frontend/src/components/AgentGovernancePanel.tsx")

    assert "fetchOrgNodeOptions().then(setOrgNodes)" in panel
    assert "orgApi.users().then" in panel
    assert "a.name_ko || a.asset_id" not in panel
    assert "scopeName(a.owner_scope_id)" in panel
    assert "personName(a.approved_by)" in panel
    assert "personName(a.created_by)" in panel
    assert "personName(a.promotion_requested_by)" in panel
    assert "ctx.tenantId ? ` · ${ctx.tenantId}`" not in panel


def test_지식_원본등록부는_팩과_조직과_승인자를_표시명으로_보여준다():
    panel = _read("frontend/src/components/KnowledgeHubPanel.tsx")

    assert "<ReferenceTable packs={packs || []}" in panel
    assert "packName(open.pack_id)" in panel
    assert "scopeName(a.scope_code)" in panel
    assert "scopeName(a.owner_org_id)" in panel
    assert "personName(open.approved_by)" in panel
    assert "{open.pack_id || '지식팩 미지정'}" not in panel
    assert "{open.scope_code || '미지정'}" not in panel
    assert "{a.owner_org_id || '미지정'}" not in panel


def test_회사_연결구성은_단계_코드를_입력받지_않고_회사_id도_보이지_않는다():
    panel = _read("frontend/src/components/CompanySetupPanel.tsx")

    assert "allocateSystemIds('process_stage')" in panel
    assert 'placeholder="단계 코드"' not in panel
    assert "{ctx.company}</span>" not in panel
    assert "companyId || '회사 ID 확인 불가'" not in panel
    assert "원본 {e.base_entity_id}" not in panel
    assert "selected_object_label: ctx.companyName" in panel


def test_자비스는_서버_문맥_id_대신_사람용_이름을_표시한다():
    rail = _read("frontend/src/design/JarvisRail.tsx")
    api = _read("frontend/src/lib/jarvisApi.ts")

    assert "selected_object_label?: string" in api
    assert "context.selected_object_label || contextTitle" in rail
    assert "<dd>{context.selected_object_id\n                  ||" not in rail


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


def test_1280_세로스크롤바가_생겨도_경영홈은_가로로_넘치지_않는다():
    css = _read("frontend/src/design/enterprise-canvas.css")

    responsive = css.split("@media(max-width:1280px){", 1)[1].split("}", 1)[0]
    assert "grid-template-columns:252px minmax(0,1fr) 320px" in responsive


def test_좁은_화면에서는_영향카드가_결정_행동을_덮지_않는다():
    css = _read("frontend/src/design/enterprise-canvas.css")

    responsive = css.split("@media(max-width:900px){", 1)[1].split("\n}", 1)[0]
    assert "grid-template-columns:180px minmax(0,1fr) 260px" in responsive
    assert "grid-template-rows:minmax(0,1fr) 72px" in responsive
    assert "height:286px" in responsive
    assert ".le-canvas .impact{" in responsive
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in responsive
    assert ".le-canvas .impact{display:none}" not in responsive


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


def test_결정보고는_독립_3열_페이지와_첫화면_자비스를_쓴다():
    app = _read("frontend/src/App.tsx")
    hub = _read("frontend/src/features/collaboration/CollaborationHub.tsx")

    assert "| 'report'" in app
    assert "space === 'report'" in app
    assert '<ProductShell module="report"' in app
    assert '<CollaborationHub page initialView={collaborationInitialView}' in app
    assert "layoutClassName={page ? 'product-page-shell' : ''}" in hub
    assert "product-page-content product-hub-page decision-report-page" in hub
    assert "<JarvisRail" in hub
    assert "if (page) return hub;" in hub


def test_홈_하단_업무공간과_데이터준비상태는_서로_다른_목적으로_연결된다():
    app = _read("frontend/src/App.tsx")
    page = _read("frontend/src/components/EnterprisePage.tsx")
    prep = _read("frontend/src/components/DataPrepPanel.tsx")

    assert "onOpenMenu('workspace')}>전체 업무 공간" in page
    assert '<button onClick={onOpenDataReadiness}>데이터 준비 상태</button>' in page
    assert "setDataPrepInitialView('readiness')" in app
    assert "initialView={dataPrepInitialView}" in app
    assert "initialView?: 'overview' | 'readiness'" in prep
    assert "if (initialView === 'readiness' && visible.length === 1)" in prep
    assert "if (initialView === 'overview')" in prep
    assert "준비 상태를 확인할 적용본" in prep


def test_전체메뉴의_정식_제품화면은_레거시_모달을_다시_열지_않는다():
    app = _read("frontend/src/App.tsx")

    assert "setCollaborationInitialView('inbox');" in app
    assert "setCollaborationInitialView('decisions');" in app
    assert "setShowCollaboration(false);" in app
    assert "setShowKnowledgeHub(false); setSpace('knowledge')" in app
    assert "setShowScenario(false); setSpace('twin')" in app
    assert "closeAgentPanel(); setSpace('agent')" in app


def test_결정보고_본문은_다른_제품화면과_같은_타이포와_컨트롤_비율을_쓴다():
    css = _read("frontend/src/design/afs.css")

    scope = css.split(".afs-scope .product-hub-page .screen-head {", 1)[1]
    assert "font-size: 26px" in scope
    assert "font-size: 14px" in scope
    assert "color: var(--ls-red)" in scope
    assert "min-height: 38px !important" in scope
    assert "min-height: 62px" in scope


def test_지식은_모달이_아닌_독립_제품화면에서_근거형_자비스를_쓴다():
    app = _read("frontend/src/App.tsx")
    panel = _read("frontend/src/components/KnowledgeHubPanel.tsx")

    assert "| 'knowledge'" in app
    assert "space === 'knowledge'" in app
    assert '<ProductShell module="knowledge"' in app
    assert '<KnowledgeHubPanel page' in app
    assert "layoutClassName={page ? 'product-page-shell' : ''}" in panel
    assert "product-page-content product-hub-page knowledge-page" in panel
    assert "<JarvisRail" in panel
    assert "if (page) return hub;" in panel


def test_에이전트_화면은_워크플로우_템플릿을_먼저_선택하게_한다():
    panel = _read("frontend/src/components/AgentMasterPanel.tsx")
    store = _read("frontend/src/store/useFactoryStore.ts")

    assert "useState<View>('templates')" in panel
    menu = panel.split("const railItems: RailItem[] = [", 1)[1].split("];", 1)[0]
    assert menu.index("id: 'templates'") < menu.index("id: 'agents'") < menu.index("id: 'flow'")
    assert "에이전트 셋을 먼저 고른다" in menu
    assert "const [confirmedTemplateId, setConfirmedTemplateId]" in panel
    assert "id !== 'templates' && !selectionReady" in panel
    assert "먼저 워크플로우 템플릿을 선택하십시오" in panel
    assert "selectedId={confirmedTemplateId || ''}" in panel
    assert "agentRegistry: null, agentRegistryError:" in store
    assert "selectEditingTemplate: (id: string) => Promise<boolean>" in store
    assert "if (dirty) { switchTpl.ask(tid); return; }" in panel
    assert 'title="저장하지 않은 변경이 사라집니다"' in panel
    assert "이미 이 템플릿에 결속된 프로젝트도 새 실행과" in panel


def test_새_에이전트는_선택한_템플릿_편집판에만_추가된다():
    panel = _read("frontend/src/components/AgentMasterPanel.tsx")

    assert "＋ 새 에이전트" in panel
    assert "if (!selectionReady)" in panel
    assert "allocateSystemIds('agent')" in panel
    assert "existingAgent.name_ko" in panel
    assert 'label="에이전트 식별자"' not in panel
    assert "agents: [...(d?.agents || []), next]" in panel
    assert "setSelectedAgentId(id)" in panel
    assert "실행 흐름에서 연결하고 변경사항을 저장하십시오" in panel


def test_프로젝트_생성은_이름만_받고_내부_id를_화면에서_받지_않는다():
    dialog = _read("frontend/src/components/BuildStartDialog.tsx")
    advisor = _read("frontend/src/components/AdvisorPanel.tsx")
    api = _read("frontend/src/lib/advisorApi.ts")
    store = _read("frontend/src/store/useFactoryStore.ts")

    assert "업무 이름" in dialog
    assert "projectName" in dialog
    assert "업무 식별자" not in dialog
    create_block = store.split("createProject: async", 1)[1].split("createMegaProject:", 1)[0]
    assert "project_id:" not in create_block
    assert "project_name: name" in store
    assert "새 프로젝트 ID" not in advisor
    assert "createdProjectId" in advisor
    assert "JSON.stringify({ project_name, template_id })" in api


def test_company_knowledge_and_format_creation_use_central_hidden_ids():
    company = _read("frontend/src/components/CompanySetupPanel.tsx")
    knowledge = _read("frontend/src/components/KnowledgeHubPanel.tsx")
    output_format = _read("frontend/src/components/FormatMasterPanel.tsx")
    node = _read("frontend/src/components/AgentFlow/AgentNode.tsx")

    assert "allocateSystemIds('company')" in company
    assert "회사 식별자" not in company
    assert "{t.tenant_id}</span>" not in company
    assert "allocateSystemIds('knowledge_pack')" in knowledge
    assert 'label="팩 ID"' not in knowledge
    assert "allocateSystemIds('output_format')" in output_format
    assert "새로운 포맷 ID" not in output_format
    assert "{data.id}" not in node


def test_지식_작업_시뮬레이션_화면은_내부_id를_사람용_표기로_대체한다():
    knowledge = _read("frontend/src/components/KnowledgeHubPanel.tsx")
    control = _read("frontend/src/components/ControlPanel.tsx")
    hotl = _read("frontend/src/components/HOTLInput.tsx")
    scenario = _read("frontend/src/components/ScenarioPanel.tsx")
    baseline = _read("frontend/src/components/BaselinePicker.tsx")

    assert "p.pack_id.toLowerCase().includes(q)" not in knowledge
    assert "팩 ID·이름만 찾습니다" not in knowledge
    assert "meta: `${p.pack_id}" not in knowledge
    assert "{ label: '팩 ID', value: pack.pack_id }" not in knowledge
    assert "<th>Task ID</th>" not in control
    assert "{task.task_id}</span>" not in control
    assert "타겟 태스크(Task ID)" not in hotl
    assert "현재 프로젝트 ID" not in hotl
    assert "Snapshot ID 를 지정" not in scenario
    assert "value: pick.instanceId" not in scenario
    assert "{it.scope_node_id}" not in baseline
    assert "{it.label || it.kit_id}" not in baseline


def test_결정_보고는_참여자와_담당자를_조직_표시명으로_선택한다():
    center = _read("frontend/src/features/collaboration/DecisionCenter.tsx")

    assert "orgApi.users()" in center
    assert 'placeholder="사용자 ID' not in center
    assert 'placeholder="담당자 ID"' not in center
    assert "personName(p.user_id)" in center
    assert "personName(a.owner_user_id)" in center
    assert "계정 문자열을 직접 입력해 우회하지 않습니다" in center
    assert "담당자 계정을 직접 입력하지 않습니다" in center
    assert 'placeholder="run_id"' not in center
    assert 'htmlFor="nc-base"' not in center
    assert 'htmlFor="nc-scn"' not in center
    assert "내부 식별자를 직접 입력해 우회하지 않습니다" in center
    assert "decisionApi.sources()" in center
    assert "selectedSource.scenario_label" in center
    assert "selectedSource.baseline_label" in center
    assert "baseline_id: head" not in center
    assert "scenario_id: head" not in center


def test_이름없는_조직_키트_작업은_내부_ID를_대체표기로_쓰지_않는다():
    asset = _read("frontend/src/components/AgentAssetWizard.tsx")
    prep = _read("frontend/src/components/DataPrepPanel.tsx")
    operations = _read("frontend/src/components/KitOperationsPanel.tsx")
    context = _read("frontend/src/components/OperatingContextSwitcher.tsx")
    company_bar = _read("frontend/src/components/CompanyContextBar.tsx")
    quality = _read("frontend/src/components/QualityOutcomesView.tsx")

    assert "ownerScopeLabel" in asset
    assert "d.owner_scope_id || '미지정'" not in asset
    assert "instance?.label || instance?.kit_id" not in prep
    assert "instance.scope_node_id || '미상'" not in prep
    assert "it.label || it.kit_id" not in prep
    assert "selectedInstance?.label || selectedInstance?.kit_id" not in operations
    assert "d.name_ko || d.dept_id" not in context
    assert "d.name_ko || d.dept_id" not in company_bar
    assert "{o.task_id}</span>" not in quality


def test_조직_화면은_부서와_범위의_내부_id를_직접_입력시키지_않는다():
    panel = _read("frontend/src/components/OrgChartPanel.tsx")
    api = _read("frontend/src/lib/orgApi.ts")

    assert 'label="부서 코드"' not in panel
    assert 'aria-label="조직 범위 코드"' not in panel
    assert "fetchOrgNodes()" in panel
    assert "scopeLabel(selectedDept.scope_node_id" in panel
    assert "<option key={d.dept_id} value={d.dept_id}>{d.name_ko}</option>" in panel
    assert "createDept: (body: { name_ko: string; parent_id?: string })" in api
    assert "dept_id: deptForm" not in panel
    # 사용자 계정은 SSO/사내 메일 정체성이므로 시스템 임의 채번 대상이 아니다.
    assert 'label="계정"' in panel and "사내 메일 주소를 그대로 씁니다" in panel


def test_데이터_준비_화면은_적용본_id를_입력하거나_노출하지_않는다():
    panel = _read("frontend/src/components/DataPrepPanel.tsx")

    assert 'aria-label="패키지 적용 식별자"' not in panel
    assert 'placeholder="적용 식별자"' not in panel
    assert "shortId(it.instance_id)" not in panel
    assert "title={it.instance_id}" not in panel
    assert "instances.map" in panel and "openInstance(it.instance_id)" in panel


def test_앱_제작_목록은_내부_프로젝트와_릴리스_id를_노출하지_않는다():
    page = _read("frontend/src/components/BuildPage.tsx")

    assert 'placeholder="업무 이름으로 찾기"' in page
    assert "project.name || '이름 미등록 프로젝트'" in page
    assert "{project.id} ·" not in page
    assert "{selectedProject.id}</div>" not in page
    assert "shortId(releaseId)" not in page
    assert "title={releaseId}" not in page


def test_integrated_project_creation_sends_name_not_user_chosen_id():
    app = _read("frontend/src/App.tsx")
    store = _read("frontend/src/store/useFactoryStore.ts")
    mega = store.split("createMegaProject: async", 1)[1].split("stopSprint:", 1)[0]
    copy = store.split("copyProject: async", 1)[1].split("// 🗑️", 1)[0]

    assert "r.isMega" in app and "createMegaProject(r.projectName" in app
    assert "mega_project_name: name" in mega
    assert "mega_project_id:" not in mega
    assert "new_project_name: newName" in copy
    assert "new_project_id:" not in copy


def test_지식화면에서_원문_온톨로지_대외지표를_직접_확인한다():
    app = _read("frontend/src/App.tsx")
    panel = _read("frontend/src/components/KnowledgeHubPanel.tsx")
    ontology = _read("frontend/src/components/OntologyExplorerView.tsx")
    ontology_api = _read("frontend/src/lib/ontologyApi.ts")
    external = _read("frontend/src/components/ExternalIntelligenceView.tsx")
    api = _read("frontend/src/lib/knowledgeApi.ts")
    external_api = _read("frontend/src/lib/externalIntelligenceApi.ts")

    assert "'contents'" in panel and "지식 내용 확인" in panel
    assert "documentContent" in api and "/content?offset=" in api
    assert "function formatExtractedContent(value: string)" in panel
    assert "(?:slide|page)" in panel
    assert "formatExtractedContent(content.value?.content || '')" in panel
    assert "<OntologyExplorerView />" in panel
    assert "ontologyApi.impact(root, asOf)" in ontology
    assert "승인된 의미만 표시합니다" in ontology
    assert "ontologyApi.modelContract" in ontology
    assert "설치된 계약 원문을 운영 기준으로 확인합니다" in ontology
    assert "ontologyApi.relations(relationFilter)" in ontology
    assert "ontologyApi.proposalContext()" in ontology
    assert "계약에 허용된 관계 제안" in ontology
    assert 'tone="warn" title="관계를 저장할 조직 범위를 선택하십시오"' in ontology
    assert "현재 ‘권한 범위 전체’는 조회 문맥입니다" in ontology
    assert "쓰기 가능한 소유 부서를 확인하지 못했습니다" in ontology
    assert "승인 버튼이 전용 원장 사건을 기록합니다" in ontology
    assert "임의 원장 ID를 입력하지 않습니다" in ontology
    assert "ontologyApi.decideApprove" in ontology
    assert "ontologyApi.decideRetire" in ontology
    assert "Decision Ledger 사건 ID" not in ontology
    assert "<ConfirmInline" in ontology
    assert "modelContract:" in ontology_api and "/api/v1/ontology/model/${" in ontology_api
    assert "relations:" in ontology_api and "/api/v1/ontology/relations?" in ontology_api
    assert "proposalContext:" in ontology_api and "/api/v1/ontology/proposal/context" in ontology_api
    assert "propose:" in ontology_api and "/api/v1/ontology/relations/propose" in ontology_api
    assert "decideApprove:" in ontology_api and "/decisions/approve`" in ontology_api
    assert "decideRetire:" in ontology_api and "/decisions/retire`" in ontology_api
    assert "<ExternalIntelligenceView />" in panel
    assert "externalIntelligenceApi.resolveBaseline(selected)" in external
    assert "발표 시점별 관측값" in external
    assert "externalIntelligenceApi.registerSource(sourceForm)" in external
    assert "externalIntelligenceApi.approveSource(sourceId)" in external
    assert "externalIntelligenceApi.recordObservation" in external
    assert "등록은 승인이 아닙니다" in external
    assert "승인된 원천이 없어 관측값을 기록할 수 없습니다" in external
    assert "quality_status: 'RAW'" in external
    assert "원천 승인 철회 경로가 없습니다" in external
    assert "registerSource:" in external_api and "/api/v1/external/sources" in external_api
    assert "approveSource:" in external_api and "/approve`" in external_api
    assert "recordObservation:" in external_api and "/api/v1/external/observations" in external_api
    assert "externalIntelligenceApi.collectable()" in external
    assert "externalIntelligenceApi.collectCsv" in external
    assert "externalIntelligenceApi.collectSource" in external
    assert "먼저 예행하기" in external
    assert "예행 결과대로 실제 적재 검토" in external
    assert "previewSnapshot === collectionSnapshot(collectionMode)" in external
    assert "indicator_map: Object.fromEntries" in external
    assert "추측 매핑은 하지 않습니다" in external
    assert "0이나 오늘 날짜로 보정하지 않음" in external
    assert "원천 값이 바뀔 수 있습니다" in external
    assert "collectCsv:" in external_api and "/api/v1/external/collect/csv" in external_api
    assert "collectSource:" in external_api and "/api/v1/external/collect/${" in external_api
    assert "회사 기준정보 기반 대외 조사" in external
    assert "웹에서 찾은 문장과 숫자는 확정 대외지표가 아닙니다" in external
    assert "externalIntelligenceApi.researchProfiles()" in external
    assert "externalIntelligenceApi.scheduleResearchJob" in external
    assert "externalIntelligenceApi.runResearchJob" in external
    assert "externalIntelligenceApi.decideResearchCandidate" in external
    assert "실행 가능한 봇" in external and 'value="1/4"' in external
    assert "어댑터 미연결 · 실행 차단" in external
    assert "researchProfiles:" in external_api and "/api/v1/external/research/profiles" in external_api
    assert "runResearchJob:" in external_api and "/run`" in external_api
    assert "decideResearchCandidate:" in external_api and "/decision`" in external_api
    assert "label: '업무 온톨로지'" in app
    assert "label: '대외 인텔리전스'" in app
    assert "setKnowledgeInitialView('ontology')" in app
    assert "setKnowledgeInitialView('external')" in app


def test_에이전트는_독립_제품화면에서_저장상태와_사람확인_통제를_보인다():
    app = _read("frontend/src/App.tsx")
    panel = _read("frontend/src/components/AgentMasterPanel.tsx")
    detail = _read("frontend/src/components/AgentFlow/AgentDetailSidebar.tsx")
    css = _read("frontend/src/design/afs.css")

    assert "| 'agent'" in app
    assert "space === 'agent'" in app
    assert '<ProductShell module="agent"' in app
    assert '<AgentMasterPanel page' in app
    assert "layoutClassName={page ? 'product-page-shell' : ''}" in panel
    assert "product-page-content product-hub-page agent-master-page" in panel
    assert "agent-page-actions" in panel
    assert "agent-master-detail-layout" in panel
    assert "변경사항 저장" in panel
    assert "사람 확인 지점은 통제입니다" in panel
    assert "추가하고 싶은 기능" in panel
    assert "AI로 에이전트 후보 추천" in panel
    assert "선택한 후보를 편집판에 추가" in panel
    assert "/api/v1/factory/ai-recommend/pipeline" in panel
    assert "const runRecommendAgents" in panel
    assert "const addRecommendedAgents" in panel
    assert "is_start: false" in panel and "is_end: false" in panel
    assert "기존 에이전트는 다시 만들지 마십시오" in panel
    assert "실행 흐름에서 연결을 정한 뒤" in panel
    id_api = _read("frontend/src/lib/systemIdApi.ts")
    assert "/api/v1/factory/identifiers/allocate" in id_api
    assert 'label="에이전트 식별자"' not in panel
    assert 'label="새 템플릿 식별자"' not in panel
    assert "<code>{candidate.id}</code>" not in panel
    assert "내부 식별자는 시스템이 자동" in panel
    assert '<span className="text-xs font-mono' not in detail
    assert "if (page) return hub;" in panel
    assert ".afs-scope .agent-page-actions" in css
    assert ".afs-scope .agent-master-detail-layout" in css
    assert "agent-detail-editor" in detail
    assert ".agent-master-page .agent-detail-editor" in css


def test_업무데이터_설계상담은_가로단계표가_아닌_3열_업무공간을_쓴다():
    panel = _read("frontend/src/components/AdvisorPanel.tsx")

    assert "<HubShell" in panel
    assert "<JarvisRail" in panel
    assert "BUSINESS & DATA DESIGN" in panel
    assert "업무 선택" in panel
    assert "선택형 상담" in panel
    assert "데이터 보유 확인" in panel
    assert "청사진·승인·생성" in panel
    assert "selectRailStep" in panel
    assert "selected_object_id: selectedObjectId" in panel
    assert "evidence_refs: ledger.status === 'ok'" in panel
    assert "진행 단계" in panel
    assert "현재 상담 문맥" in panel


def test_업무데이터_준비는_적용본부터_인증판까지_3열_업무공간으로_탐색한다():
    panel = _read("frontend/src/components/DataPrepPanel.tsx")
    css = _read("frontend/src/design/afs.css")

    assert "<HubShell" in panel
    assert "<JarvisRail" in panel
    assert "DATA READINESS" in panel
    assert "샘플 기업 패키지" in panel
    assert "조직 적용본" in panel
    assert "업무기능 준비도" in panel
    assert "원천·데이터 판" in panel
    assert "selectSection" in panel
    assert "sourceSectionRef.current.open = true" in panel
    assert "조직 적용본을 먼저 선택해야" in panel
    assert "evidence_refs: snapshots.map" in panel
    assert "못 읽은 것은 0건이 아닙니다" in panel
    assert ".afs-scope .data-prep-panel" in css


def test_계산실행_승인은_관문_승인_초기화를_3열_통제화면으로_구분한다():
    panel = _read("frontend/src/components/CalcApprovalPanel.tsx")
    css = _read("frontend/src/design/afs.css")

    assert "<HubShell" in panel
    assert "<JarvisRail" in panel
    assert "CALCULATION CONTROL" in panel
    assert "label: '준비 상태'" in panel
    assert "label: '계산 실행 승인'" in panel
    assert "label: '시연 실행 초기화'" in panel
    assert "APPROVAL REQUIRED" in panel
    assert "승인 전에는 계산하지 않습니다" in panel
    assert "current_module: `calculation-approval/${tab}`" in panel
    assert "binding_fingerprint: item.binding_fingerprint" in panel
    assert "정본과 승인 원장은 유지" in panel
    assert ".afs-scope .calc-approval-panel" in css


def test_경로계산은_질문부터_안건연결까지_3열_폐루프로_보인다():
    panel = _read("frontend/src/components/PathCalcPanel.tsx")
    css = _read("frontend/src/design/afs.css")

    assert "<HubShell" in panel
    assert "<JarvisRail" in panel
    assert "PATH CALCULATION" in panel
    assert "label: '질문·기준시점'" in panel
    assert "label: '영향 경로 선택'" in panel
    assert "label: '계산 결과·차단'" in panel
    assert "label: '의사결정 안건 연결'" in panel
    assert "NO SILENT ZERO" in panel
    assert "막힌 계산은 숫자가 아닙니다" in panel
    assert "selectSection" in panel
    assert "result.used_snapshots" in panel
    assert "result.result_fingerprint" in panel
    assert "계산이 완료되어야 의사결정 안건" in panel
    assert ".afs-scope .path-calc-panel" in css


def test_U1_핵심여정은_홈위_모달이_아니라_공통_제품상단바_아래에서_열린다():
    app = _read("frontend/src/App.tsx")
    shell = _read("frontend/src/components/ProductShell.tsx")
    dialog = _read("frontend/src/design/HubDialog.tsx")
    css = _read("frontend/src/design/afs.css")

    for space in ("advisor", "data", "calc", "path", "briefing"):
        assert f"space === '{space}'" in app
        assert f"setSpace('{space}')" in app
    assert "<AdvisorPanel page" in app
    assert "<DataPrepPanel page" in app
    assert "<CalcApprovalPanel page" in app
    assert "<PathCalcPanel page" in app
    assert "<BriefingPanel page" in app
    assert "<ProductShell module={journeyModule || foundationModule || decisionModule" in app
    assert "|| governanceModule || inspectionModule!}" in app
    assert "const NAV_PARENT" in shell
    assert "calc: 'twin'" in shell
    assert "briefing: 'report'" in shell
    assert "if (page) return <>{children}</>" in dialog
    assert ".afs-scope .journey-product-body" in css


def test_U1_독립페이지에서는_대화상자_전용_상단바를_중복해_그리지_않는다():
    for path in (
        "frontend/src/components/AdvisorPanel.tsx",
        "frontend/src/components/DataPrepPanel.tsx",
        "frontend/src/components/BriefingPanel.tsx",
    ):
        panel = _read(path)
        assert "!page && <div className=\"afs-dialog-bar\"" in panel

    for path in (
        "frontend/src/components/AdvisorPanel.tsx",
        "frontend/src/components/DataPrepPanel.tsx",
        "frontend/src/components/CalcApprovalPanel.tsx",
        "frontend/src/components/PathCalcPanel.tsx",
        "frontend/src/components/BriefingPanel.tsx",
    ):
        panel = _read(path)
        assert "page = false" in panel
        assert "page={page}" in panel
        assert "product-page-shell" in panel


def test_U2_근거화면_일곱개는_공통_제품상단바_아래에서_열린다():
    app = _read("frontend/src/App.tsx")
    shell = _read("frontend/src/components/ProductShell.tsx")

    for space in ("master", "terminology", "crosswalk", "governance"):
        assert f"setSpace('{space}')" in app
        assert f"{space}: 'knowledge'" in shell
    assert "<MasterDataPanel page" in app
    assert "<TerminologyGlossaryPanel page" in app
    assert "<CrosswalkPanel page" in app
    assert "<GovernanceConsole page" in app
    assert "setKnowledgeInitialView('ontology')" in app
    assert "setKnowledgeInitialView('external')" in app
    assert "<ProductShell module={journeyModule || foundationModule || decisionModule" in app
    assert "|| governanceModule || inspectionModule!}" in app


def test_용어집은_중복탭이_아니라_단계레일_본문_자비스_세영역을_쓴다():
    panel = _read("frontend/src/components/TerminologyGlossaryPanel.tsx")
    css = _read("frontend/src/components/terminology-glossary.css")

    assert "<HubShell" in panel
    assert "<JarvisRail" in panel
    assert "label: '전체 용어 사전'" in panel
    assert "label: 'P0 충돌과 권장안'" in panel
    assert "label: '사용 원칙'" in panel
    assert '<nav className="terminology-tabs"' not in panel
    assert "current_module: `knowledge/terminology/${tab}`" in panel
    assert "visible_count: filtered.length" in panel
    assert "표시명과 시스템 식별자는 다릅니다" in panel
    assert ".product-page-shell .term-controls" in css
    assert "grid-template-columns: minmax(230px, 1.35fr) minmax(150px, .85fr)" in css


def test_크로스워크는_제안과_승인주소록을_가르고_판독실패를_0건으로_접지_않는다():
    panel = _read("frontend/src/components/CrosswalkPanel.tsx")

    assert "<HubShell" in panel
    assert "<JarvisRail" in panel
    assert "label: '시스템·스키마'" in panel
    assert "label: '매핑 제안'" in panel
    assert "label: '승인된 매핑'" in panel
    assert "proposals.status === 'ok' ? pending.length : undefined" in panel
    assert "mappings.status === 'ok' ? (mappings.value || []).length : undefined" in panel
    assert "제안은 아직 조회 주소가 아닙니다" in panel
    assert "시스템을 먼저 선택해야 이 단계를 확인할 수 있습니다" in panel
    assert "ref={proposalsSection}" in panel
    assert "ref={confirmedSection}" in panel


def test_U3_경영계획과_Shadow_Mode는_팝업이_아니라_공통_제품상단바_아래에서_열린다():
    app = _read("frontend/src/App.tsx")
    shell = _read("frontend/src/components/ProductShell.tsx")
    planning = _read("frontend/src/components/PlanningPanel.tsx")
    shadow = _read("frontend/src/components/ShadowModePanel.tsx")
    workspace_shell = _read("frontend/src/components/SimulationGovernanceShell.tsx")

    for space in ("planning", "shadow"):
        assert f"setSpace('{space}')" in app
        assert f"{space}: 'twin'" in shell
    assert "<PlanningPanel page" in app
    assert "<ShadowModePanel page" in app
    assert "const decisionModule" in app
    assert "journeyModule || foundationModule || decisionModule" in app
    assert '<SimulationGovernanceShell kind="planning">' in app
    assert '<SimulationGovernanceShell kind="shadow">' in app
    assert "<HubShell" in workspace_shell
    assert "<JarvisRail" in workspace_shell
    assert "PLANNING_ITEMS" in workspace_shell
    assert "SHADOW_ITEMS" in workspace_shell
    assert "selected_object_id: active" in workspace_shell
    assert "panel.querySelector<HTMLElement>('.panel-head small')" in workspace_shell
    assert "useEffect(() => setActive(items[0].id), [kind])" in workspace_shell

    for panel in (planning, shadow):
        assert "page = false" in panel
        assert "page={page}" in panel
        assert "!page && <div className=\"afs-dialog-bar\"" in panel


def test_U4_운영승격과_워크스페이스는_공통_제품셸과_통제단계_자비스를_쓴다():
    app = _read("frontend/src/App.tsx")
    shell = _read("frontend/src/components/ProductShell.tsx")
    promotion = _read("frontend/src/components/ReleasePromotionPanel.tsx")
    workspace = _read("frontend/src/components/WorkspacePanel.tsx")
    operations_shell = _read("frontend/src/components/OperationsGovernanceShell.tsx")

    for space in ("promotion", "workspace"):
        assert f"setSpace('{space}')" in app
        assert f"{space}: 'operate'" in shell
    assert '<OperationsGovernanceShell kind="promotion">' in app
    assert '<OperationsGovernanceShell kind="workspace">' in app
    assert "<ReleasePromotionPanel page" in app
    assert "<WorkspacePanel page" in app

    for panel in (promotion, workspace):
        assert "page = false" in panel
        assert "page={page}" in panel
        assert "!page && <div className=\"afs-dialog-bar\"" in panel

    assert "<HubShell" in operations_shell
    assert "<JarvisRail" in operations_shell
    assert "PROMOTION_ITEMS" in operations_shell
    assert "WORKSPACE_ITEMS" in operations_shell
    assert "selected_object_id: active" in operations_shell
    assert "useEffect(() => setActive(items[0].id), [kind])" in operations_shell
    assert "승격 전 결과는 운영값이 아닙니다" not in operations_shell
    assert "검사를 통과해도 사람의 결정이 필요합니다" in operations_shell


def test_U5_회사조직표준에이전트_통제화면은_전체메뉴에서_독립_제품페이지로_열린다():
    app = _read("frontend/src/App.tsx")
    shell = _read("frontend/src/components/ProductShell.tsx")

    expected = {
        "company": "enterprise", "org": "enterprise", "standard": "knowledge",
        "agentgov": "agent", "skills": "agent",
    }
    for space, parent in expected.items():
        assert f"setSpace('{space}')" in app
        assert f"{space}: '{parent}'" in shell
    assert "const governanceModule" in app
    assert "journeyModule || foundationModule || decisionModule || governanceModule" in app
    assert "<CompanySetupPanel page" in app
    assert "<OrgChartPanel page" in app
    assert "<WorkStandardPanel page" in app
    assert "<AgentGovernancePanel page" in app
    assert "<SkillEvolutionPanel page" in app

    for path in (
        "frontend/src/components/OrgChartPanel.tsx",
        "frontend/src/components/WorkStandardPanel.tsx",
        "frontend/src/components/AgentGovernancePanel.tsx",
        "frontend/src/components/SkillEvolutionPanel.tsx",
    ):
        panel = _read(path)
        assert "page = false" in panel
        assert "page={page}" in panel
        assert "!page && <div className=\"afs-dialog-bar\"" in panel
        assert "layoutClassName={page ? 'product-page-shell' : ''}" in panel


def test_회사구성_제품페이지는_실제단계와_실행문맥을_자비스에_결속한다():
    panel = _read("frontend/src/components/CompanySetupPanel.tsx")

    assert "page = false" in panel
    assert "COMPANY_ITEMS" in panel
    assert '<HubShell layoutClassName="product-page-shell company-product-shell"' in panel
    assert "activeId={tab}" in panel
    assert "!page && <div role=\"tablist\"" in panel
    assert "<JarvisRail" in panel
    assert "current_module: `company_setup/${tab}`" in panel
    assert "selected_object_id: ctx.company || tab" in panel
    assert "company_name: ctx.companyName" in panel
    assert "실제와 가상은 섞지 않습니다" in panel


def test_회사구성은_일반사용자에게_쓰기행동을_약속하지_않는다():
    panel = _read("frontend/src/components/CompanySetupPanel.tsx")
    shell = _read("frontend/src/components/ProductShell.tsx")

    assert "actingScope.load()" in panel
    assert "const canEdit = Boolean(actorScope?.canEditOrg)" in panel
    assert "조직 편집 권한이 없어 회사 구성을 조회만 할 수 있습니다" in panel
    assert "available_actions: !canEdit" in panel
    assert "disabled={!canEdit || !name.trim()" in panel
    assert "allocateSystemIds('company')" in panel
    assert "disabled={!canEdit || !!busy || rows.length === 0" in panel
    assert 'aria-label="환경설정" title="환경설정"' in shell
    assert 'aria-label="환경설정 · 관리자"' not in shell


def test_U6_LLM_텔레메트리는_에이전트_제품셸_아래_독립페이지로_열린다():
    app = _read("frontend/src/App.tsx")
    shell = _read("frontend/src/components/ProductShell.tsx")
    panel = _read("frontend/src/components/TelemetryPanel.tsx")

    assert "setSpace('telemetry')" in app
    assert "telemetry: 'agent'" in shell
    assert "const inspectionModule = space === 'telemetry'" in app
    assert "<TelemetryPanel page" in app
    assert "page = false" in panel
    assert "page={page}" in panel
    assert "!page && <div className=\"afs-dialog-bar\"" in panel
    assert "layoutClassName={page ? 'product-page-shell' : ''}" in panel
    assert "<JarvisRail" in panel
    assert "cost_is_lower_bound" in panel


def test_대외조사_프로필은_내부_ID를_입력하거나_업무화면에_노출하지_않는다():
    panel = _read("frontend/src/components/ExternalIntelligenceView.tsx")
    api = _read("frontend/src/lib/externalIntelligenceApi.ts")

    assert "listEntities()" in panel and "orgApi.users()" in panel
    assert 'label="조사 대상 회사"' in panel
    assert 'label="조사 담당자"' in panel
    assert 'label="법인 ID"' not in panel
    assert 'label="담당자 ID"' not in panel
    assert 'placeholder="예: corp-ls-mnm"' not in panel
    assert "{p.legal_entity_id}" not in panel
    assert "{p.owner_id}" not in panel
    assert "ownerNameById.get(p.owner_id)" in panel
    assert "entityNameById.get(p.legal_entity_id)" in panel
    assert "'profile_id' | 'status'" in api


def test_대외조사_지표와_원천은_이름으로_선택하고_외부근거는_ID로_오해시키지_않는다():
    panel = _read("frontend/src/components/ExternalIntelligenceView.tsx")

    assert "required_indicators: e.target.checked" in panel
    assert "등록부 코드 기준, 쉼표로 구분합니다" not in panel
    assert "FX_USDKRW" not in panel
    assert 'label="원천 근거 위치"' in panel
    assert "공표문서 URL·표·행 위치" in panel
    assert 'label="원천 레코드 참조"' not in panel
    assert "sourceNameById.get(o.source_id)" in panel


def test_출력양식과_대체프로그램은_내부_ID를_표시하거나_직접_입력시키지_않는다():
    formats = _read("frontend/src/components/FormatMasterPanel.tsx")
    programs = _read("frontend/src/components/ProgramAdminPanel.tsx")

    assert "allocateSystemIds('output_format')" in formats
    assert "ID: <span" not in formats
    assert "{f.id}</div>" not in formats
    assert "내부 식별자는 시스템이 자동으로 관리합니다" in formats
    assert "replacementOptions" in programs
    assert '<select id="pa-replacement"' in programs
    assert "대체 프로그램 식별자" not in programs
    assert "placeholder=\"예: myapp_" not in programs
    assert "대체 프로그램: {replacementLabel}" in programs


def test_크로스워크_연계시스템은_이름만_받고_내부_ID를_자동발급한다():
    panel = _read("frontend/src/components/CrosswalkPanel.tsx")

    assert "allocateSystemIds('external_system')" in panel
    assert "system_id (예: sap, mes)" not in panel
    assert "system_id 를 입력하십시오" not in panel
    assert "시스템 이름 (예: SAP ERP)" in panel
    assert "내부 식별자는 시스템이 자동으로 발급하고 관리합니다" in panel
    assert "{s.system_id}</span>" not in panel
    assert "{selSys.system_id}" not in panel


def test_기준정보_유형은_이름만_받고_내부_ID를_자동발급한다():
    panel = _read("frontend/src/components/MasterDataPanel.tsx")

    assert "allocateSystemIds('master_type')" in panel
    assert 'label="type_id"' not in panel
    assert "typeForm.id" not in panel
    assert 'value="시스템 자동 발급" readOnly' in panel
    assert "{t.name_ko} ({t.type_id})" not in panel
    assert "{t.name_ko}</option>" in panel


def test_기준정보_주입범위는_조직_ID가_아니라_실제_조직명으로_선택한다():
    panel = _read("frontend/src/components/MasterDataPanel.tsx")

    assert "fetchOrgNodes()" in panel
    assert "(orgNodes as FlatNode[]).filter((node) => node.readable)" in panel
    assert 'label="조직 범위"' in panel
    assert "ECM 노드 ID를 지정" not in panel
    assert 'placeholder="예: MNM_BATTERY"' not in panel


def test_에이전트_자산_소유조직은_조직_ID를_직접_입력하지_않는다():
    wizard = _read("frontend/src/components/AgentAssetWizard.tsx")

    assert "fetchOrgNodes()" in wizard
    assert "orgNodes.filter((node) => node.readable)" in wizard
    assert 'placeholder={ctx.scopeNodeId' not in wizard
    assert "조직 노드 id" not in wizard
    assert "현재 실행 조직" in wizard
