# 🎨 디자인 시스템 가이드 (Tailwind 토큰 — 샌드박스 자기완결형)

화면 전체가 **일관된 색·간격·타이포·컴포넌트 모양**을 갖도록 아래 토큰·레시피를 그대로 사용하라.
외부 UI 라이브러리(Shadcn/MUI 등) 금지 — 샌드박스가 Tailwind CDN 만 로드한다. 아래는 모두 Tailwind 유틸 클래스다.

## 색상 토큰
- Primary(주요 동작): `bg-indigo-600 hover:bg-indigo-700 text-white` / 텍스트 강조 `text-indigo-600`
- Neutral(본문/테두리/배경): 텍스트 `text-slate-800` / 보조 `text-slate-500` / 테두리 `border-slate-200` / 페이지 배경 `bg-slate-50` / 카드 `bg-white`
- Danger(삭제/경고): `bg-rose-600 hover:bg-rose-700 text-white` / 텍스트 `text-rose-600`
- Success(완료/성공): `bg-emerald-600 text-white` / 텍스트 `text-emerald-600`

## 간격·반경·그림자
- 간격 스케일(일관 사용): `gap-2`/`gap-4`, 패딩 `p-4`/`p-6`, 섹션 간 `space-y-4`/`space-y-6`
- 모서리: 카드/입력 `rounded-lg`, 버튼 `rounded-md`, 알약 `rounded-full`
- 그림자: 카드 `shadow-sm`, 떠 있는 요소 `shadow-md`

## 타이포
- 페이지 제목 `text-2xl font-bold text-slate-900` · 섹션 제목 `text-lg font-semibold text-slate-800`
- 본문 `text-sm text-slate-700` · 보조/캡션 `text-xs text-slate-500`

## 레이아웃
- 페이지 루트: `min-h-screen bg-slate-50 text-slate-800` + 가운데 컨테이너 `max-w-3xl mx-auto p-6`
- 반응형: 모바일 우선, 그리드는 `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4`

## 컴포넌트 클래스 레시피 (복사해서 사용)
- Primary 버튼: `className="inline-flex items-center justify-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"`
- Secondary 버튼: `className="inline-flex items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"`
- Danger 버튼: `className="inline-flex items-center rounded-md bg-rose-600 px-3 py-2 text-sm font-medium text-white hover:bg-rose-700"`
- 카드: `className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm"`
- 텍스트 입력: `className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"`
- 라벨: `className="block text-sm font-medium text-slate-700 mb-1"`
- 빈 상태(목록 0건): 가운데 정렬 `className="text-center text-slate-400 py-12"` + 아이콘(이모지)+안내문

## 원칙
- 색은 위 팔레트 안에서만(임의 hex 난발 금지). 같은 의미의 요소는 같은 클래스로(버튼마다 색·크기 제각각 금지).
- 여백은 위 스케일로 일관되게. 빽빽하거나 들쭉날쭉하지 않게.
