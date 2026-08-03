(() => {
  "use strict";

  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const standaloneRoutes = {
    enterprise: "../master-concept/",
    build: "../revision-v2-2/factory/",
    simulate: "../revision-v2/v9/",
    agent: "../revision-v2/v10/"
  };

  const screenMeta = {
    enterprise: {
      nav: "enterprise",
      kicker: "EXECUTIVE WORKLIST",
      title: "지금 결정해야 할<br>회사 업무입니다.",
      description: "사용자 권한과 현재 회사 범위에서 우선순위를 계산했습니다.",
      atlas: {
        context: "CURRENT CONTEXT · 생산계획",
        title: "지금은 생산계획과 원료 발주를 함께 보는 것이 핵심입니다.",
        text: "현재 화면의 업무, 데이터, 진행 중인 SW와 시뮬레이션을 함께 사용해 설명합니다.",
        brief: "발주량 -4%와 재고 3.2일 축소 조합을 권고합니다.",
        bullets: ["납기 준수율 96.8%를 유지할 수 있습니다.", "장기 원료계약 2건은 담당자 확인이 필요합니다.", "예상 영업이익률은 기준안보다 0.7%p 낮습니다."]
      }
    },
    context: {
      nav: "enterprise",
      kicker: "COMPANY UNIVERSE",
      title: "회사 구조와 문맥을<br>먼저 설정합니다.",
      description: "실제 회사·사업부·공장과 가상회사를 권한·데이터 격리 원칙으로 관리합니다.",
      menu: [["01", "Enterprise Structure", "회사·사업부·공장", "context"], ["02", "Company Profile", "업종·업태·브랜드", "context"], ["03", "Access Scope", "내 접근 범위 9", "context"], ["04", "Industry Playbook", "활성 5", "context"], ["05", "Virtual Sandbox", "가상회사 1", "context"]],
      atlas: {
        context: "CURRENT CONTEXT · COMPANY UNIVERSE",
        title: "회사 문맥을 선택하면 업무·데이터·Agent 구성이 함께 바뀝니다.",
        text: "Atlas 답변과 SW·Twin·보고서 생성도 사용자가 읽을 수 있는 회사 범위 안에서만 수행됩니다.",
        brief: "LS MnM에는 비철금속 제조 플레이북과 9개 Agent 제조 시뮬레이션 템플릿을 추천합니다.",
        bullets: ["상위 회사 권한은 허용된 하위 범위에만 상속됩니다.", "가상회사는 REAL 데이터와 자동 합산되지 않습니다.", "기존 회사를 복사해 신사업·신공장·경쟁환경을 검토할 수 있습니다."]
      }
    },
    advisor: {
      nav: "advisor",
      kicker: "GUIDED START",
      title: "무엇을 만들지<br>함께 정리합니다.",
      description: "긴 설명 대신 추천 방향을 선택하고 필요한 정보만 보완하세요.",
      menu: [["01", "업무 설계 상담", "현재 2 / 6 단계", "advisor"], ["02", "프로젝트 포트폴리오", "독립·Mega 프로젝트", "advisor"], ["03", "SW Production", "진행 프로젝트 3", "build"], ["04", "Release Library", "운영 릴리스 12", "operate"]],
      atlas: {
        context: "CURRENT CONTEXT · 업무 설계 상담",
        title: "경영계획 업무에는 먼저 계획 단위와 승인 구조가 필요합니다.",
        text: "보유 데이터와 부족 데이터를 동시에 확인해 구현 가능한 범위를 선제안합니다.",
        brief: "전사 손익·현금·KPI 통합 관리안을 추천합니다.",
        bullets: ["현재 기준정보 5종 중 4종을 사용할 수 있습니다.", "계획 동인과 외부지표는 다음 단계에서 확인합니다.", "답변 완료 시 기능·데이터·Agent 청사진을 생성합니다."]
      }
    },
    build: {
      nav: "advisor",
      kicker: "SOFTWARE PRODUCTION",
      title: "현업 SW를<br>생산하고 있습니다.",
      description: "기획·아키텍처·UI·개발·검증의 흐름과 중단 원인을 함께 봅니다.",
      menu: [["01", "업무 설계 상담", "신규 요구 정리", "advisor"], ["02", "프로젝트 포트폴리오", "진행 3 · 대기 1", "build"], ["03", "SW Production", "AABB-PLAN 실행 중", "build"], ["04", "Artifacts & Trace", "산출물 18개", "build"]],
      atlas: {
        context: "CURRENT CONTEXT · AABB-PLAN",
        title: "Frontend 재작업은 정상 진행 중이며 사용자 개입은 필요하지 않습니다.",
        text: "Reviewer가 현금흐름의 ‘계산 불가’를 0으로 표시할 위험을 차단했습니다.",
        brief: "예상 4분 후 Reviewer 재제출이 가능합니다.",
        bullets: ["실행 태스크 2건, 대기 태스크 3건입니다.", "결정론적 테스트 24건이 통과했습니다.", "현재까지 LLM 호출 비용은 추정 하한 ₩68K입니다."]
      }
    },
    report: {
      nav: "report",
      kicker: "REPORT STUDIO",
      title: "보고서를 근거와 함께<br>검토하고 승인합니다.",
      description: "SW가 아닌 문서형 산출물의 목차·버전·근거·주석·승인·배포를 관리합니다.",
      menu: [["01", "Report Library", "보고서 18개", "report"], ["02", "Management Plan", "v0.8 · 검토 중", "report"], ["03", "Analysis Reports", "분석보고서 7개", "report"], ["04", "Simulation Reports", "Twin 연결 4개", "report"], ["05", "Review & Approval", "내 승인 대기 1", "report"], ["06", "Published Outputs", "배포 9개", "report"]],
      atlas: {
        context: "CURRENT CONTEXT · REPORT-BP-2027-001",
        title: "보고서의 전력 단가 근거를 최신 확정값으로 보정할 수 있습니다.",
        text: "현재 문단의 수치·가정·표·Digital Twin 결과를 원천 데이터까지 역추적해 검토합니다.",
        brief: "최신 전력 단가를 연결하면 근거 충실도가 92%에서 96%로 높아집니다.",
        bullets: ["경영환경 장의 공동 검토자는 3명 중 2명이 승인했습니다.", "미해결 검토 의견은 2건입니다.", "승인 시 조직 범위와 보고서 v0.8이 Ledger에 고정됩니다."]
      }
    },
    operate: {
      nav: "operate",
      kicker: "DEPARTMENT OPERATIONS",
      title: "만든 SW를<br>안전하게 운영합니다.",
      description: "부서 공유부터 전사 승격까지 자산·계약·품질·오너 승인을 확인합니다.",
      menu: [["01", "Department Workspace", "경영관리팀 6개", "operate"], ["02", "Promotion & Readiness", "승격 대기 1", "operate"], ["03", "Program Lifecycle", "운영 12개", "operate"], ["04", "Shadow Validation", "검증 중 2", "operate"], ["05", "Quality & Operations", "이상 1건", "operate"]],
      atlas: {
        context: "CURRENT CONTEXT · 전사 승격",
        title: "승격 조건 5개 중 데이터 오너 승인만 남았습니다.",
        text: "보안·계보·계약·품질은 모두 통과했고 미승인 자산의 전사 노출은 차단됩니다.",
        brief: "재무회계팀 데이터 오너에게 검토를 요청하세요.",
        bullets: ["영향 범위는 8개 부서, 사용자 64명입니다.", "릴리스와 연결된 데이터 자산은 6개입니다.", "승인 전에는 전사 승격 버튼이 활성화되지 않습니다."]
      }
    },
    simulate: {
      nav: "simulate",
      kicker: "MANAGEMENT DIGITAL TWIN",
      title: "변화가 경영 결과에<br>미치는 영향을 봅니다.",
      description: "같은 기준선에서 외부·내부 동인을 바꾸고 손익·현금·운영 영향을 비교합니다.",
      menu: [["01", "Baseline Manager", "PLAN v3", "simulate"], ["02", "Scenario Lab", "3개 시나리오", "simulate"], ["03", "Assumption Registry", "가정 22개", "simulate"], ["04", "Forecast & Backtest", "MAPE 6.4%", "simulate"], ["05", "Decision Ledger", "대기 4건", "enterprise"]],
      atlas: {
        context: "CURRENT CONTEXT · 2027 PLAN",
        title: "원료와 전력 가격 상승이 수요 증가 효과를 상쇄합니다.",
        text: "슬라이더를 바꾸면 손익·현금·납기 영향과 사용한 가정을 함께 갱신합니다.",
        brief: "현재 조합은 매출 증가에도 영업이익률이 0.7%p 하락합니다.",
        bullets: ["원료 장기계약 2건은 검증이 필요합니다.", "CAPEX 일정 미입력으로 공격성장안 FCF는 확정할 수 없습니다.", "Backtest MAPE는 6.4%입니다."]
      }
    },
    knowledge: {
      nav: "knowledge",
      kicker: "KNOWLEDGE FOUNDATION",
      title: "데이터를 신뢰 가능한<br>회사 지식으로 만듭니다.",
      description: "원본·MDM·카탈로그·연계·외부지표를 범위와 승인 상태로 관리합니다.",
      menu: [["01", "Source Registry", "검토 대기 68", "knowledge"], ["02", "Knowledge Packs", "활성 7", "knowledge"], ["03", "Master Data", "도메인 24", "knowledge"], ["04", "Data Catalog", "자산 126", "knowledge"], ["05", "Integration & MCP", "연결 7 / 8", "knowledge"], ["06", "External Signals", "공식 지표 12", "knowledge"]],
      atlas: {
        context: "CURRENT CONTEXT · 원본자료 등록부",
        title: "원본 68건은 아직 승인 전이라 생성 품질에 사용되지 않습니다.",
        text: "오너·조직 범위·분류·지식팩을 확정한 자료만 색인되도록 Fail-closed로 관리합니다.",
        brief: "동제련 운영자료 16건부터 오너와 범위를 일괄 확인하세요.",
        bullets: ["15건은 바로 추출할 수 있고 1건은 변환이 필요합니다.", "오너 미지정 문서는 승인할 수 없습니다.", "승인 후 본문 추출과 지식팩 색인이 시작됩니다."]
      }
    },
    agent: {
      nav: "agent",
      kicker: "AGENT OPERATING SYSTEM",
      title: "Agent를 업무 목적에<br>맞게 설계합니다.",
      description: "역할·스킬·모델·HOTL·비용·품질 게이트를 하나의 실행 그래프로 관리합니다.",
      menu: [["01", "Workflow Templates", "활성 4", "agent"], ["02", "Agent Registry", "기본 15", "agent"], ["03", "Skill Library", "스킬 29", "agent"], ["04", "Model & Cost Policy", "공급자 5", "agent"], ["05", "Quality Telemetry", "미분류 0", "agent"], ["06", "Skill Evolution", "제안 2", "agent"]],
      atlas: {
        context: "CURRENT CONTEXT · SW 제품 개발",
        title: "Master PM은 강한 추론과 사용자 승인에 비용을 집중합니다.",
        text: "단순 분류는 Flash, 설계·리뷰는 Pro, 재작업 시에만 Swarm을 확장하는 정책입니다.",
        brief: "현재 그래프는 유효하며 예상 호출은 28회입니다.",
        bullets: ["HOTL 승인 지점은 5개입니다.", "미단가 모델 1개 때문에 비용 총액은 하한으로 표시됩니다.", "품질 게이트는 결정론 검증을 먼저 수행합니다."]
      }
    },
    admin: {
      nav: "",
      kicker: "SETTINGS & ADMINISTRATION",
      title: "개인 환경과 회사 정책을<br>안전하게 관리합니다.",
      description: "권한별 설정, 적용 범위, 영향과 승인 상태를 한곳에서 확인합니다.",
      menu: [["01", "Personal Settings", "표시·알림·Atlas", "admin"], ["02", "Enterprise & Brand", "CI·문맥·상속", "admin"], ["03", "Users & Access", "64명 · 역할 12", "admin"], ["04", "Model & Cost", "공급자 5 · 예산 63%", "admin"], ["05", "Data Connections", "정상 7 / 8", "admin"], ["06", "Audit & Operations", "플랫폼 정상", "admin"]],
      atlas: {
        context: "CURRENT CONTEXT · ADMINISTRATION",
        title: "현재 변경이 누구와 어떤 업무에 영향을 주는지 먼저 확인합니다.",
        text: "Atlas는 설정값을 임의로 바꾸지 않고 범위·의존성·되돌림·필요 승인을 설명합니다.",
        brief: "개인 설정은 즉시 저장할 수 있고 전사 정책은 검토 요청 후 예약 적용합니다.",
        bullets: ["범위 미지정 데이터는 누구에게도 노출되지 않습니다.", "비밀정보 원문은 화면과 로그에 표시하지 않습니다.", "전사 변경은 영향 분석과 감사 이력을 남깁니다."]
      }
    }
  };

  const adminSectionMeta = {
    personal: ["개인 설정 변경", "현재 변경은 나에게만 적용되며 별도 승인 없이 되돌릴 수 있습니다.", "김민수 · 개인 계정", "영향 사용자 1명 · 서비스 중단 없음", "내 설정 저장", false],
    brand: ["회사 브랜드 변경", "Top Bar와 회사 문맥 표시가 LS MnM 전사 사용자에게 변경됩니다.", "LS MnM · 전사 및 하위 상속", "영향 사용자 64명 · 하위 프로필 4개", "검토 요청 후 저장", true],
    access: ["권한 정책 변경", "사용자의 데이터 읽기·쓰기·승인 범위가 변경될 수 있습니다.", "LS MnM · 사용자 및 역할", "영향 사용자 64명 · 정책 12개", "보안 검토 요청", true],
    ai: ["AI 모델 정책 변경", "새 Sprint의 모델 라우팅·예상 품질·비용에 영향을 줍니다.", "플랫폼 · 전체 Agent Workflow", "활성 템플릿 4개 · 진행 Sprint 제외", "AI 정책 검토 요청", true],
    integration: ["데이터 연계 변경", "연결 자산·계보·생성 SW 입력 데이터에 영향을 줄 수 있습니다.", "LS MnM · 명시적 연결 범위", "연계 8개 · 데이터 자산 126개", "Data Owner 검토 요청", true],
    operations: ["플랫폼 운영 정책 변경", "감사·보존·복구·운영 중지 기준은 전사 플랫폼에 적용됩니다.", "AI Factory Studio · 운영 환경", "전체 사용자 · 서비스 5개", "운영 변경 검토 요청", true]
  };

  const adminAtlasMeta = {
    personal: ["내 환경설정", "개인 설정은 즉시 저장할 수 있고 언제든 기본값으로 되돌릴 수 있습니다.", ["회사 데이터와 업무 결과에는 영향을 주지 않습니다.", "글자 크기·언어·알림·Atlas 응답 방식을 설정합니다.", "저장 이력은 내 계정 감사 기록에 남습니다."]],
    brand: ["회사 브랜드", "CI 변경은 현재 회사와 승인된 하위 조직의 제품 Shell에 적용됩니다.", ["상태색과 CI 색의 대비 충돌을 먼저 검사합니다.", "하위 회사의 승인된 예외 프로필은 보존합니다.", "검토 승인 전에는 다른 사용자에게 배포되지 않습니다."]],
    access: ["사용자·권한", "권한 변경은 읽기·쓰기·승인 범위와 하위 상속 영향을 먼저 확인해야 합니다.", ["미바인딩 자원은 누구에게도 노출되지 않습니다.", "접근 불가 자원은 404로 존재를 은폐합니다.", "모든 역할 변경은 감사 Ledger에 기록됩니다."]],
    ai: ["AI 모델·비용", "품질 게이트를 유지하면서 작업 난이도와 예산에 맞는 모델을 선택합니다.", ["진행 중 Sprint에는 새 정책을 소급하지 않습니다.", "미단가 모델은 비용 총액에서 제외하고 하한으로 표시합니다.", "Golden Benchmark 미달 모델은 강한 작업에 배정하지 않습니다."]],
    integration: ["데이터·연계", "연계 변경은 명시적 회사 범위와 Data Owner 승인이 있어야 적용됩니다.", ["비밀정보 원문은 화면과 로그에 표시하지 않습니다.", "계약 변경 전 영향 자산과 Lineage를 확인합니다.", "미승인 원본은 지식 색인과 생성 입력에서 차단됩니다."]],
    operations: ["보안·감사·운영", "운영 정책은 복구 경로와 담당 승인을 확인한 뒤 예약 적용합니다.", ["감사 적재 완전성과 보존 정책을 함께 검증합니다.", "긴급 중지와 정책 변경 권한은 분리합니다.", "복구훈련 결과가 오래되면 고영향 변경을 차단합니다."]]
  };

  const decisionContent = {
    plan: ["DECISION POINT · 생산계획", "원가 상승을 반영한 생산·구매계획을 함께 승인하세요.", "원재료 가격과 전력 단가 상승이 수요 증가 효과를 상쇄합니다. 재고를 3.2일 줄이고 발주량을 조정하면 납기 수준을 유지할 수 있습니다.", "₩428억", "8.0%", "96.8%", "89%"],
    quality: ["DECISION POINT · 품질", "전해공정 이상 패턴의 조치 순서를 확인하세요.", "QMS와 MES에서 동일한 변동이 확인됐습니다. 전류밀도 확인과 설비 점검을 먼저 수행하면 품질 손실 위험을 낮출 수 있습니다.", "₩421억", "8.3%", "96.1%", "94%"],
    planning: ["DECISION POINT · 경영관리", "2027 사업계획 기준선과 충돌 가정을 확정하세요.", "8개 부서 계획은 취합됐지만 환율·원료가격·CAPEX 일정에서 3개 가정이 충돌합니다. 기준선을 확정해야 전사 시뮬레이션을 시작할 수 있습니다.", "₩5,620억", "8.7%", "95.9%", "86%"],
    factory: ["DECISION POINT · SW FACTORY", "Reviewer 피드백 이후의 복구 진행을 확인하세요.", "구매 최적화 Workbench는 재작업 중입니다. 현금흐름 계산 불가 상태를 숫자 0과 구분하도록 수정하고 있습니다.", "63%", "2건", "4분", "91%"]
  };

  const nodeContent = {
    order: ["DECISION POINT · 수주·판매", "수요 증가가 생산·재고에 미치는 영향을 확인하세요.", "신규 주문 증가율은 3%이며 현재 생산 여력으로 대응 가능하지만 원료 리드타임을 함께 조정해야 합니다.", "₩428억", "8.4%", "97.1%", "93%"],
    purchase: ["DECISION POINT · 원료조달", "원료 가격 상승에 대응할 계약·발주 조합을 선택하세요.", "장기계약 2건의 단가 검증이 남아 있습니다. 현물 비중을 낮추고 재고일수를 조정하는 안이 가장 안정적입니다.", "₩426억", "7.9%", "96.6%", "87%"],
    plan: decisionContent.plan,
    production: ["DECISION POINT · 제련·생산", "가동률 94%에서 추가 물량을 수용할지 검토하세요.", "병목 설비의 예방정비 일정을 유지하면 추가 수요의 70%를 내부 생산으로 대응할 수 있습니다.", "₩430억", "8.2%", "96.3%", "91%"],
    quality: decisionContent.quality,
    logistics: ["DECISION POINT · 물류·출하", "납기 준수율을 유지할 출하 우선순위를 확정하세요.", "재고 축소 시 동남아향 2개 주문의 완충시간이 감소합니다. 선적 슬롯을 먼저 확보해야 합니다.", "₩427억", "8.1%", "96.8%", "90%"],
    profit: ["DECISION POINT · 손익·경영", "매출 성장과 수익성 하락 사이의 선택을 검토하세요.", "수요 증가는 매출을 높이지만 원료와 전력비 상승으로 이익률은 0.7%p 감소합니다. 가격 전가와 생산성 개선을 함께 비교해야 합니다.", "₩5,620억", "8.0%", "96.8%", "92%"]
  };

  const reportSections = {
    summary: ["00. 경영진 요약", "전사 계획의 핵심 수치, 의사결정 요청사항과 주요 위험을 한눈에 제시합니다."],
    environment: ["Ⅰ. 2027년 경영환경과 핵심 가정", "확인된 내부 운영 데이터와 검증된 공식 외부지표를 기준으로 계획의 전제를 명시합니다."],
    sales: ["Ⅱ. 판매·수주계획", "고객·제품·시장별 수요 전망과 수주 파이프라인을 생산능력 및 가격 전략과 연결합니다."],
    production: ["Ⅲ. 구매·생산계획", "원료 계약, 재고, 생산능력과 납기를 같은 기준선에서 조정한 실행계획을 제시합니다."],
    investment: ["Ⅳ. 인력·투자계획", "채용·CAPEX·정비계획이 생산성, 현금흐름과 향후 사업역량에 미치는 영향을 설명합니다."],
    profit: ["Ⅴ. 손익·현금 전망", "부서 계획과 Digital Twin 시나리오를 연결해 매출·이익·현금 전망 및 변동 범위를 제시합니다."],
    actions: ["Ⅵ. 실행과제·리스크", "계획 달성을 위한 부서별 실행과제, 선행조건, 책임자와 위험 대응 트리거를 정의합니다."],
    approval: ["승인·배포", "검토 의견의 해결 상태와 승인 Ledger를 확인하고 배포 대상·형식·보안등급을 확정합니다."]
  };

  const companyProfiles = {
    group: ["LS", "LS · 지주사 · REAL", "지주·사업 포트폴리오", "계열사별 경영성과와 투자·리스크를 연결해 관리합니다.", "그룹 경영·포트폴리오 플레이북"],
    cable: ["LS전선", "LS / LS전선 · REAL", "전선·케이블 제조", "수주 프로젝트, 원재료, 생산, 품질과 납기를 프로젝트 손익에 연결합니다.", "수주형 제조·프로젝트 손익 플레이북"],
    electric: ["LS ELECTRIC", "LS / LS ELECTRIC · REAL", "전력·자동화 제조", "제품·프로젝트·서비스 데이터를 전력시장과 자동화 설비 운영에 연결합니다.", "전력기기·자동화 제조 플레이북"],
    mnm: ["LS MnM", "LS / LS MnM · REAL", "비철금속·소재 제조", "원료 조달부터 제련·정련·품질·물류·판매·손익까지 연속공정 기반으로 운영합니다.", "비철금속 제조 운영체계"],
    common: ["LS MnM 전사공통", "LS / LS MnM / 전사공통 · REAL", "경영관리·재무회계", "사업부 계획·실적을 연결해 손익·현금·투자·인력 전망을 전사 기준으로 집계합니다.", "전사 경영관리·계획 플레이북"],
    copper: ["동제련 사업부", "LS / LS MnM / 동제련 사업부 · REAL", "동·은·금 제련 제조", "원료 배합, 제련·전련, 귀금속 회수와 품질·에너지·원가를 통합 관리합니다.", "동제련 공정·원가 Twin 플레이북"],
    battery: ["배터리소재 사업부", "LS / LS MnM / 배터리소재 사업부 · REAL", "배터리 소재 제조", "황산화물 생산과 신규 라인 확장, 원료·품질·수요 변동을 함께 관리합니다.", "배터리소재 생산·확장 플레이북"],
    plant1: ["온산 제1공장", "LS / LS MnM / 동제련 / 온산 제1공장 · REAL", "동제련 운영공장", "설비·공정·품질·에너지 데이터를 현장 SW와 공정 Twin에 연결합니다.", "공장 운영·설비·품질 플레이북"],
    plant2: ["배터리소재 제2공장", "LS / LS MnM / 배터리소재 / 제2공장 · REAL", "신규 확장공장", "Ramp-up, 생산능력, 수율, 인력과 투자회수 계획을 통합 검증합니다.", "신공장 Ramp-up 플레이북"],
    virtual: ["Recycling Pilot", "가상 신사업 법인 / Recycling Pilot · VIRTUAL", "배터리 재활용 신사업", "기존 회사의 공정·Master 구조를 복사하되 모든 수치와 결과는 REAL 실적과 격리합니다.", "신사업 타당성·가상회사 플레이북"]
  };

  let currentScreen = "enterprise";
  let selectedCompanyKey = "mnm";
  let atlasCreateMode = null;
  let toastTimer;

  function toast(message) {
    let el = $("#sampleToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "sampleToast";
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2300);
  }

  function renderAtlas(meta) {
    if (!meta?.atlas) return;
    $("#atlasContext").textContent = meta.atlas.context;
    $("#atlasTitle").textContent = meta.atlas.title;
    $("#atlasText").textContent = meta.atlas.text;
    $("#atlasBrief").textContent = meta.atlas.brief;
    $("#atlasBullets").innerHTML = meta.atlas.bullets.map(item => `<li>${item}</li>`).join("");
  }

  function renderRail(meta, screen) {
    $("#railKicker").textContent = meta.kicker;
    $("#railTitle").innerHTML = meta.title;
    $("#railDescription").textContent = meta.description;
    const enterpriseRail = $("#enterpriseRail");
    const sectionRail = $("#sectionRail");
    const showEnterprise = screen === "enterprise";
    enterpriseRail.hidden = !showEnterprise;
    sectionRail.hidden = showEnterprise;
    if (!showEnterprise) {
      const adminKeys = ["personal", "brand", "access", "ai", "integration", "operations"];
      sectionRail.innerHTML = `<div class="rail-label"><span>기능 모듈</span><b>${meta.menu?.length ?? 0}</b></div>` + (meta.menu || []).map(([n, title, sub, target], index) => `
        <button class="${target === screen && index === 0 ? "active" : ""}" data-screen-link="${target}" ${screen === "admin" ? `data-admin-section="${adminKeys[index]}"` : ""}>
          <span>${n}</span><div><b>${title}</b><small>${sub}</small></div><em>›</em>
        </button>`).join("");
      bindScreenLinks(sectionRail);
      bindAdminSectionLinks(sectionRail);
    }
  }

  function showScreen(screen, updateHash = true) {
    if (!screenMeta[screen]) screen = "enterprise";
    if (standaloneRoutes[screen]) {
      location.href = standaloneRoutes[screen];
      return;
    }
    currentScreen = screen;
    $$("[data-screen-view]").forEach(view => view.classList.toggle("active", view.dataset.screenView === screen));
    $$(".primary-nav [data-screen]").forEach(button => button.classList.toggle("active", button.dataset.screen === screenMeta[screen].nav));
    renderRail(screenMeta[screen], screen);
    renderAtlas(screenMeta[screen]);
    if (screen === "admin") selectAdminSection("personal");
    $(".main-stage").scrollTop = 0;
    window.scrollTo(0, 0);
    if (updateHash) history.replaceState(null, "", `#${screen}`);
    closePalette();
  }

  function bindScreenLinks(root = document) {
    $$('[data-screen-link]', root).forEach(button => {
      if (button.dataset.bound) return;
      button.dataset.bound = "true";
      button.addEventListener("click", () => showScreen(button.dataset.screenLink));
    });
  }

  function setDecision(content, source) {
    if (!content) return;
    ["focusTag", "focusTitle", "focusDescription", "impactSales", "impactProfit", "impactDelivery", "impactTrust"].forEach((id, index) => {
      const element = $(`#${id}`);
      if (element) element.textContent = content[index];
    });
    $$(".domain-node").forEach(node => node.classList.toggle("selected", node.dataset.node === source));
    const atlas = {...screenMeta.enterprise.atlas, context: `CURRENT CONTEXT · ${content[0].replace("DECISION POINT · ", "")}`, title: content[1], text: content[2]};
    renderAtlas({atlas});
  }

  function updateScenario() {
    const fx = Number($("#fxRange").value);
    const raw = Number($("#rawRange").value);
    const power = Number($("#powerRange").value);
    const labor = Number($("#laborRange").value);
    $("#fxValue").textContent = `${fx.toLocaleString("ko-KR")}원`;
    $("#rawValue").textContent = `${raw >= 0 ? "+" : ""}${raw}%`;
    $("#powerValue").textContent = `+${power}%`;
    $("#laborValue").textContent = `${labor >= 0 ? "+" : ""}${labor}명`;

    const fxImpact = (fx - 1350) * 0.11;
    const revenue = 5510 + labor * 2.2 + Math.max(0, fxImpact * .5);
    const costPressure = raw * 2.4 + power * 1.3 + Math.max(0, fxImpact * .38) + Math.max(0, labor) * .35;
    const profit = Math.max(240, 506 - costPressure + labor * .45);
    const margin = Math.max(4.2, profit / revenue * 100);
    const cash = Math.max(40, profit * .58 - Math.max(0, labor) * 1.7);
    $("#twinSales").textContent = `₩${Math.round(revenue).toLocaleString("ko-KR")}억`;
    $("#twinProfit").textContent = `₩${Math.round(profit).toLocaleString("ko-KR")}억`;
    $("#twinMargin").textContent = `${margin.toFixed(1)}%`;
    $("#twinCash").textContent = `₩${Math.round(cash).toLocaleString("ko-KR")}억`;

    const base = [172,165,168,148,140,132,135,119,111,104,108,92];
    const shift = Math.min(55, Math.max(-18, costPressure / 2.2 - labor / 6));
    const points = base.map((y, i) => `${40 + i * 61},${Math.max(36, Math.min(205, y + shift * (0.55 + i / 24)))}`).join(" ");
    $("#scenarioLine").setAttribute("points", points);
  }

  function runKnowledgeSearch(query) {
    const normalized = query.trim();
    if (!normalized) return toast("찾고 싶은 업무·데이터·근거를 자연어로 입력해 주세요.");

    let result = {
      title: "원가 동인과 손익 영향의 연결 근거를 찾았습니다.",
      count: "관련 근거 7건",
      summary: "전력비·원료단가 → 생산원가 → 제품별 기여이익 → 전사 손익의 연결 경로로 검색했습니다.",
      path: ["전력 단가", "동제련 공정", "제조원가", "영업이익"],
      meta: "승인 근거 5건 · 검토 대기 2건 · 의미 유사도 92%",
      atlas: "승인된 자료 5건을 우선 근거로 찾았고, 장기 원료계약 2건은 검토 대기로 분리했습니다."
    };
    if (/품질|이상|전해|조치/.test(normalized)) {
      result = {
        title: "전해공정 이상과 과거 조치 사례를 찾았습니다.",
        count: "관련 근거 11건",
        summary: "공정 이상 코드와 QMS 용어의 동의어를 확장하고, 설비·품질·조치결과 관계를 따라 검색했습니다.",
        path: ["전류밀도 이상", "전해공정", "품질 편차", "조치 사례"],
        meta: "승인 근거 8건 · 검토 대기 3건 · 의미 유사도 95%",
        atlas: "가장 유사한 과거 사례 3건에서는 전류밀도 확인 후 설비 점검 순서가 효과적이었습니다."
      };
    } else if (/구매|최적화|오너|계보|SW/.test(normalized)) {
      result = {
        title: "원료 구매 Optimizer의 데이터 계보를 찾았습니다.",
        count: "연결 자산 6건",
        summary: "SW 릴리스에서 입력 데이터·Master Data·원천 시스템·데이터 오너를 역방향으로 추적했습니다.",
        path: ["구매 Optimizer", "원료 계약", "ERP 구매", "원료팀 오너"],
        meta: "운영 자산 4건 · 기준정보 2건 · 계약 정상 4/4",
        atlas: "원료 계약·재고·공급사 Master가 연결되어 있고 최종 데이터 오너는 원료팀입니다."
      };
    } else if (/환율|공식|지표|경영계획/.test(normalized)) {
      result = {
        title: "경영계획 기준선에 사용할 공식 외부지표를 찾았습니다.",
        count: "공식 지표 5건",
        summary: "계획 가정과 동일한 단위·주기·유효기간을 가진 공식 확정값만 우선 검색했습니다.",
        path: ["한국은행 환율", "LME 원료가격", "계획 동인", "2027 기준선"],
        meta: "공식 출처 5건 · D+1 확정값 · 기준선 사용 4건",
        atlas: "환율은 한국은행, 원료가격은 공식 시장지표를 사용하고 출처와 기준시각을 함께 고정하는 것이 적합합니다."
      };
    }

    const resultBox = $("#knowledgeSemanticResult");
    resultBox.hidden = false;
    $("#semanticResultTitle").textContent = result.title;
    $("#semanticResultCount").textContent = result.count;
    $("#semanticResultSummary").textContent = result.summary;
    $(".graph-path", resultBox).innerHTML = result.path.map((item, index) => `${index ? "<i>→</i>" : ""}<span>${item}</span>`).join("");
    $("#knowledgeRegistryTitle").textContent = `자연어 검색 결과 · ${normalized.length > 22 ? normalized.slice(0, 22) + "…" : normalized}`;
    $("#knowledgeRegistryMeta").textContent = result.meta;
    $$(".registry-table .table-row").forEach((row, index) => row.classList.toggle("selected", index < 2));
    $("#atlasBrief").textContent = result.atlas;
    $("#atlasTitle").textContent = "질문의 의미와 업무 관계를 해석해 근거를 찾았습니다.";
    const resultTop = resultBox.getBoundingClientRect().top + window.scrollY - 110;
    window.scrollTo({ top: Math.max(0, resultTop), left: 0, behavior: "smooth" });
    toast("자연어 의미 검색과 Graph 관계 탐색을 완료했습니다.");
  }

  function selectCompany(key, button) {
    const profile = companyProfiles[key];
    if (!profile) return;
    selectedCompanyKey = key;
    $$(".company-node").forEach(item => item.classList.toggle("active", item === button));
    $("#companyDetailTitle").textContent = profile[0];
    $("#companyDetailPath").textContent = profile[1];
    $("#companyIndustry").textContent = profile[2];
    $("#companyDescription").textContent = profile[3];
    $("#companyPlaybookTitle").textContent = profile[4];
    renderAtlas({atlas: {
      context: `CURRENT CONTEXT · ${profile[0]}`,
      title: `${profile[0]}의 특성에 맞는 업무·데이터·Agent 구성을 적용합니다.`,
      text: profile[3],
      brief: `${profile[4]}을 기준으로 SW·Twin·보고서 생성을 시작할 수 있습니다.`,
      bullets: ["선택 문맥은 모든 검색과 생성 요청에 적용됩니다.", "사용자 권한 밖의 하위·상위 데이터는 답변에서 제외됩니다.", key === "virtual" ? "가상회사 결과는 REAL 실적과 자동 합산되지 않습니다." : "실제 회사 데이터는 승인된 범위와 기준시각을 유지합니다."]
    }});
  }

  function bindCompanyNodes(root = document) {
    $$('[data-company-node]', root).forEach(button => {
      if (button.dataset.companyBound) return;
      button.dataset.companyBound = "true";
      button.addEventListener("click", () => selectCompany(button.dataset.companyNode, button));
    });
  }

  function openPalette() {
    $("#commandPalette").hidden = false;
    setTimeout(() => $("#paletteInput").focus(), 0);
  }
  function closePalette() {
    $("#commandPalette").hidden = true;
    $("#paletteInput").value = "";
  }

  function selectAdminSection(section) {
    const meta = adminSectionMeta[section];
    if (!meta) return;
    $$('[data-admin-section]').forEach(button => button.classList.toggle("active", button.dataset.adminSection === section));
    $$('[data-admin-view]').forEach(view => view.classList.toggle("active", view.dataset.adminView === section));
    $("#adminImpactTitle").textContent = meta[0];
    $("#adminImpactText").textContent = meta[1];
    $("#adminImpactScope").textContent = meta[2];
    $("#adminImpactCount").textContent = meta[3];
    $("#adminImpactAction").textContent = meta[4];
    $("#adminApprovalCheck").textContent = meta[5] ? "담당 관리자 승인 필요" : "개인 설정은 추가 승인 불필요";
    $("#adminApprovalCheck").classList.toggle("required", meta[5]);
    $("#adminPendingCount").textContent = "변경사항 없음";
    $("#adminPendingText").textContent = "값을 수정하면 적용 전 영향이 여기에 표시됩니다.";
    const atlasMeta = adminAtlasMeta[section];
    renderAtlas({atlas: {
      context: `CURRENT CONTEXT · ${atlasMeta[0].toUpperCase()}`,
      title: meta[0] + "의 영향을 먼저 확인합니다.",
      text: meta[1],
      brief: atlasMeta[1],
      bullets: atlasMeta[2]
    }});
  }

  function markAdminChanged(label = "설정") {
    $("#adminPendingCount").textContent = "저장 대기 1건";
    $("#adminPendingText").textContent = `${label} 변경을 검토 중입니다. 적용 전 영향과 승인 조건을 확인하세요.`;
  }

  function bindAdminSectionLinks(root = document) {
    $$('[data-admin-section]', root).forEach(button => {
      if (button.dataset.adminBound) return;
      button.dataset.adminBound = "true";
      button.addEventListener("click", () => selectAdminSection(button.dataset.adminSection));
    });
  }

  bindScreenLinks();
  bindCompanyNodes();
  $$(".primary-nav [data-screen]").forEach(button => button.addEventListener("click", () => showScreen(button.dataset.screen)));

  $("#contextSwitch").addEventListener("click", event => {
    event.stopPropagation();
    $("#contextMenu").hidden = !$("#contextMenu").hidden;
  });
  $$("#contextMenu [data-context]").forEach(button => button.addEventListener("click", () => {
    $("#contextLabel").textContent = button.dataset.context;
    document.documentElement.dataset.theme = button.dataset.theme;
    if (button.dataset.theme === "virtual") {
      document.documentElement.style.setProperty("--brand", "#34266d");
      document.documentElement.style.setProperty("--accent", "#8b49d7");
      document.documentElement.style.setProperty("--data", "#1d9aa6");
    } else if (button.dataset.theme === "battery") {
      document.documentElement.style.setProperty("--brand", "#103d42");
      document.documentElement.style.setProperty("--accent", "#e85d21");
      document.documentElement.style.setProperty("--data", "#2b9f8c");
    } else {
      document.documentElement.style.setProperty("--brand", "#0a1e5a");
      document.documentElement.style.setProperty("--accent", "#fa002d");
      document.documentElement.style.setProperty("--data", "#009bb4");
    }
    $("#contextMenu").hidden = true;
    toast(`${button.dataset.context} 문맥으로 전환했습니다.`);
  }));
  document.addEventListener("click", event => {
    if (!$("#contextMenu").contains(event.target) && !$("#contextSwitch").contains(event.target)) $("#contextMenu").hidden = true;
  });
  $("#openVirtualCreator").addEventListener("click", () => {
    const target = $("#virtualCreator");
    const top = target.getBoundingClientRect().top + window.scrollY - 95;
    window.scrollTo({top: Math.max(0, top), left: 0, behavior: "smooth"});
    setTimeout(() => $("#virtualCompanyName").focus(), 280);
  });
  $("#useCompanyContext").addEventListener("click", () => {
    const profile = companyProfiles[selectedCompanyKey];
    $("#contextLabel").textContent = profile[1].replace(" · REAL", "").replace(" · VIRTUAL", "");
    toast(`${profile[0]} 문맥을 전역 검색·생성·시뮬레이션에 적용했습니다.`);
    showScreen("enterprise");
  });
  $("#createVirtualCompany").addEventListener("click", () => {
    const name = $("#virtualCompanyName").value.trim();
    const year = $("#virtualCompanyHorizon").value;
    const purpose = $("#virtualCompanyPurpose").value;
    if (!name) return toast("가상회사 이름을 입력해 주세요.");
    const key = `virtual_${Date.now()}`;
    companyProfiles[key] = [name, `가상회사 / ${name} · VIRTUAL`, `${purpose} Sandbox`, `${year}년을 기준으로 기존 회사의 구조를 복사해 ${purpose}를 검토합니다. 실제 운영 수치와 결과는 REAL 회사에서 격리됩니다.`, `${purpose} 가상 시뮬레이션 플레이북`];
    const button = document.createElement("button");
    button.className = "company-node virtual-node active";
    button.dataset.companyNode = key;
    const icon = document.createElement("i"); icon.textContent = "V";
    const copy = document.createElement("span");
    const title = document.createElement("b"); title.textContent = name;
    const sub = document.createElement("small"); sub.textContent = `${year} · ${purpose}`;
    copy.append(title, sub);
    const badge = document.createElement("em"); badge.textContent = "VIRTUAL";
    button.append(icon, copy, badge);
    $("#virtualCompanyList").appendChild(button);
    bindCompanyNodes(button.parentElement);
    selectCompany(key, button);
    const companyCount = $(".company-summary > div:first-child b");
    companyCount.textContent = String(Number(companyCount.textContent) + 1);
    toast(`${name} 가상회사 Sandbox를 생성했습니다. REAL 데이터와 분리됩니다.`);
  });

  $$(".layer-switch [data-layer]").forEach(button => button.addEventListener("click", () => {
    button.classList.toggle("active");
    $(".enterprise-canvas").classList.toggle(`hide-${button.dataset.layer}`, !button.classList.contains("active"));
  }));
  $$(".domain-node[data-node]").forEach(button => button.addEventListener("click", () => setDecision(nodeContent[button.dataset.node], button.dataset.node)));
  $$(".decision-item[data-decision]").forEach(button => button.addEventListener("click", () => {
    $$(".decision-item").forEach(item => item.classList.toggle("active", item === button));
    const key = button.dataset.decision;
    setDecision(decisionContent[key], key === "planning" || key === "factory" ? null : key);
  }));
  $("#draftDecision").addEventListener("click", () => toast("의사결정 초안을 만들었습니다. 근거 48개가 함께 연결됩니다."));

  $$('[data-option]').forEach(option => option.addEventListener("click", () => {
    $$('[data-option]').forEach(item => {
      const selected = item === option;
      item.classList.toggle("selected", selected);
      $(".option-check", item).textContent = selected ? "✓" : "";
    });
  }));
  $("#advisorNext").addEventListener("click", () => {
    const progress = $(".question-progress span");
    progress.style.width = "60%";
    $(".question-meta span").textContent = "질문 3 / 5";
    $(".question-workspace h3").textContent = "계획에 반영할 외부·내부 동인을 선택해 주세요.";
    $(".why-text").innerHTML = "<b>왜 묻나요?</b> 환율·원료단가·전력비·인력계획을 같은 기준선에 연결해야 실제 경영 시뮬레이션으로 이어질 수 있습니다.";
    toast("선택을 반영했습니다. 데이터 준비 질문으로 이동합니다.");
  });

  ["fxRange", "rawRange", "powerRange", "laborRange"].forEach(id => $(`#${id}`).addEventListener("input", updateScenario));
  $("#resetScenario").addEventListener("click", () => {
    $("#fxRange").value = 1350;
    $("#rawRange").value = 0;
    $("#powerRange").value = 0;
    $("#laborRange").value = 0;
    updateScenario();
    toast("PLAN v3 기준선 값으로 초기화했습니다.");
  });

  $$("[data-knowledge-tab]").forEach(button => button.addEventListener("click", () => {
    $$("[data-knowledge-tab]").forEach(item => item.classList.toggle("active", item === button));
    toast(`${$("span", button).textContent} 등록부를 선택했습니다. 이 샘플에서는 원본자료 상세 레이아웃을 유지합니다.`);
  }));
  $("#knowledgeNaturalSearch").addEventListener("click", () => runKnowledgeSearch($("#knowledgeNaturalQuery").value));
  $("#knowledgeNaturalQuery").addEventListener("keydown", event => {
    if (event.key === "Enter") runKnowledgeSearch(event.currentTarget.value);
  });
  $$('[data-knowledge-query]').forEach(button => button.addEventListener("click", () => {
    $("#knowledgeNaturalQuery").value = button.dataset.knowledgeQuery;
    runKnowledgeSearch(button.dataset.knowledgeQuery);
  }));
  $$(".program-card").forEach(button => button.addEventListener("click", () => {
    $$(".program-card").forEach(item => item.classList.toggle("selected", item === button));
    toast(`${$("b", button).textContent} 운영 상태를 선택했습니다.`);
  }));
  $$("[data-report-section]").forEach(button => button.addEventListener("click", () => {
    $$("[data-report-section]").forEach(item => item.classList.toggle("active", item === button));
    const content = reportSections[button.dataset.reportSection];
    $("#reportSectionTitle").textContent = content[0];
    $("#reportSectionLead").textContent = content[1];
    const paperTop = $("#reportPaper").getBoundingClientRect().top + window.scrollY - 92;
    window.scrollTo({ top: Math.max(0, paperTop), left: 0, behavior: "smooth" });
  }));
  function approveCurrentReport() {
    $("#approveReport").textContent = "승인 완료 ✓";
    $("#approveReportSide").textContent = "승인 완료 ✓";
    $("#approveReport").disabled = true;
    $("#approveReportSide").disabled = true;
    $$(".report-approval div span").forEach(item => item.classList.add("done"));
    toast("REPORT-BP-2027-001 v0.8 검토 승인을 Ledger에 기록했습니다.");
  }
  $("#approveReport").addEventListener("click", approveCurrentReport);
  $("#approveReportSide").addEventListener("click", approveCurrentReport);
  $("#compareReport").addEventListener("click", () => toast("v0.7과 v0.8의 변경 12건을 문단·수치·근거 단위로 비교합니다."));
  $("#exportReport").addEventListener("click", () => toast("PDF·Word 내보내기 옵션을 준비했습니다. 승인 워터마크와 근거 부록을 포함할 수 있습니다."));
  $$(".template-list > button:not(.new-template)").forEach(button => button.addEventListener("click", () => {
    $$(".template-list > button").forEach(item => item.classList.toggle("active", item === button));
    toast(`${$("b", button).textContent} 워크플로우를 선택했습니다.`);
  }));
  $$(".toggle").forEach(toggle => toggle.addEventListener("click", () => toggle.classList.toggle("on")));

  bindAdminSectionLinks();
  $$('.admin-settings-panel input, .admin-settings-panel select').forEach(control => control.addEventListener("change", () => markAdminChanged(control.closest(".admin-view")?.querySelector("h3")?.textContent || "설정")));
  $$('.admin-settings-panel .toggle').forEach(control => control.addEventListener("click", () => markAdminChanged("정책")));
  $$('[data-admin-toast]').forEach(button => button.addEventListener("click", () => toast(button.dataset.adminToast)));
  $("#adminFontScale").addEventListener("input", event => {
    $("#adminFontScaleValue").textContent = `${event.currentTarget.value}%`;
    markAdminChanged("글자 크기");
  });
  const brandControls = [
    ["adminBrandColor", "--brand"],
    ["adminAccentColor", "--accent"],
    ["adminDataColor", "--data"]
  ];
  brandControls.forEach(([id, property]) => $("#" + id).addEventListener("input", event => {
    document.documentElement.style.setProperty(property, event.currentTarget.value);
    event.currentTarget.nextElementSibling.textContent = event.currentTarget.value.toUpperCase();
    markAdminChanged("회사 테마");
  }));
  $("#resetAdminBrand").addEventListener("click", () => {
    const defaults = [["adminBrandColor", "--brand", "#0a1e5a"], ["adminAccentColor", "--accent", "#fa002d"], ["adminDataColor", "--data", "#009bb4"]];
    defaults.forEach(([id, property, value]) => {
      $("#" + id).value = value;
      $("#" + id).nextElementSibling.textContent = value.toUpperCase();
      document.documentElement.style.setProperty(property, value);
    });
    markAdminChanged("회사 테마 기본값");
    toast("승인된 LS MnM 기본 테마로 복원했습니다.");
  });
  const saveAdmin = () => {
    const section = $('[data-admin-section].active')?.dataset.adminSection || "personal";
    const requiresReview = adminSectionMeta[section][5];
    $("#adminPendingCount").textContent = requiresReview ? "검토 요청 1건" : "저장 완료 ✓";
    $("#adminPendingText").textContent = requiresReview ? "영향 분석과 담당 승인 후 예약 적용됩니다." : "개인 설정을 저장하고 감사 이력에 기록했습니다.";
    toast(requiresReview ? "고영향 변경을 담당자 검토 대기열에 등록했습니다." : "내 환경설정을 저장했습니다.");
  };
  $("#saveAdminSettings").addEventListener("click", saveAdmin);
  $("#adminImpactAction").addEventListener("click", saveAdmin);
  $("#adminRequestReview").addEventListener("click", () => toast("현재 설정 변경의 범위·영향·되돌림 정보를 포함해 검토를 요청했습니다."));
  $("#adminHistory").addEventListener("click", () => toast("설정 변경 이력과 승인·적용·되돌림 기록을 엽니다."));
  $("#adminDiscard").addEventListener("click", () => {
    $("#adminPendingCount").textContent = "변경사항 없음";
    $("#adminPendingText").textContent = "값을 수정하면 적용 전 영향이 여기에 표시됩니다.";
    toast("저장하지 않은 설정 변경을 취소했습니다.");
  });

  $("#searchButton").addEventListener("click", openPalette);
  $("#commandPalette").addEventListener("click", event => { if (event.target === $("#commandPalette")) closePalette(); });
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openPalette(); }
    if (event.key === "Escape") closePalette();
  });

  $$('[data-atlas-prompt]').forEach(button => button.addEventListener("click", () => {
    const answers = {
      why: "이 판단은 승인된 원료계약·재고·생산계획과 공식 외부지표를 같은 기준선에 연결해 계산했습니다.",
      data: "현재 오래되거나 부족한 데이터는 원료 장기계약 2건과 공격성장안 CAPEX 일정 1건입니다.",
      control: "AABB-PLAN은 WBS·개발 63%이며 Frontend Agent가 Reviewer 피드백을 반영하고 있습니다."
    };
    $("#atlasBrief").textContent = answers[button.dataset.atlasPrompt];
    toast("Atlas가 현재 회사 문맥과 화면 근거를 사용해 답변했습니다.");
  }));
  $$('[data-atlas-create]').forEach(button => button.addEventListener("click", () => {
    atlasCreateMode = button.dataset.atlasCreate;
    const flows = {
      sw: ["업무 SW 공동설계", "하고 싶은 업무를 설명하면 필요한 기능·화면·데이터·Agent·구현 순서를 정리합니다.", "업무 SW 설계 상담 시작", ["현재 회사 플레이북에서 유사 업무를 먼저 찾습니다.", "보유 데이터와 부족 데이터를 나눠 제안합니다.", "확인된 요구로 RFP와 WBS를 생성합니다."]],
      twin: ["시뮬레이터 공동설계", "바꾸어 볼 동인과 확인할 KPI를 정하고 기준선·계산식·검증 데이터를 함께 설계합니다.", "시뮬레이터 설계 상담 시작", ["기준선과 시나리오 값을 분리합니다.", "내부·외부 동인과 영향 경로를 연결합니다.", "Backtest와 불확실성 표시 방법을 정합니다."]],
      report: ["보고서 공동설계", "보고 목적과 독자를 확인해 목차·필요 데이터·근거·검토·승인 흐름을 설계합니다.", "보고서 설계 상담 시작", ["경영진·실무자별 정보 밀도를 구분합니다.", "수치와 문단의 근거 계보를 연결합니다.", "PDF·Word 배포와 승인 조건을 정합니다."]]
    };
    const flow = flows[atlasCreateMode];
    $("#atlasTitle").textContent = flow[0];
    $("#atlasText").textContent = flow[1];
    $("#atlasBrief").textContent = "긴 요구사항을 작성하지 않아도 추천 선택지를 통해 필요한 방향을 함께 확정합니다.";
    $("#atlasBullets").innerHTML = flow[3].map(item => `<li>${item}</li>`).join("");
    $("#atlasRecommend").textContent = flow[2];
    toast(`${flow[0]} 모드로 전환했습니다.`);
  }));
  $("#atlasRecommend").addEventListener("click", () => {
    if (atlasCreateMode) {
      const labels = {sw: "업무 SW", twin: "시뮬레이터", report: "보고서"};
      showScreen("advisor");
      $("#atlasInput").value = `${labels[atlasCreateMode]}를 만들고 싶습니다. 필요한 기능과 데이터를 함께 정리해 주세요.`;
      toast(`${labels[atlasCreateMode]} 생성 상담으로 이동했습니다.`);
      atlasCreateMode = null;
      $("#atlasRecommend").textContent = "추천안으로 의사결정안 작성";
      return;
    }
    toast("Atlas 추천안을 의사결정 Ledger 초안으로 생성했습니다.");
  });
  $("#sendAtlas").addEventListener("click", () => {
    const value = $("#atlasInput").value.trim();
    if (!value) return toast("Atlas에게 질문할 내용을 입력해 주세요.");
    $("#atlasBrief").textContent = `“${value}”에 대해 현재 회사·업무·데이터 범위를 확인해 분석을 시작했습니다.`;
    $("#atlasInput").value = "";
    toast("Task ID 없이 Atlas 전역 질의를 실행했습니다.");
  });
  $("#atlasInput").addEventListener("keydown", event => { if (event.key === "Enter") $("#sendAtlas").click(); });

  const initial = location.hash.slice(1);
  showScreen(screenMeta[initial] ? initial : "enterprise", false);
  updateScenario();
  setTimeout(() => window.scrollTo(0, 0), 0);
  window.addEventListener("hashchange", () => {
    const target = location.hash.slice(1);
    if (screenMeta[target] && target !== currentScreen) showScreen(target, false);
  });
})();
