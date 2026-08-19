// [Wave H / H-2] 계산 입력의 **한 벌 정의** — 시나리오·의사결정 화면이 함께 쓴다.
//
// ★★★ 왜 한 곳에 두나
//   의사결정 화면은 기준값 7개를 **띄어쓰기로 순서대로** 받고 있었다. 순서가 하나
//   어긋나도 오류가 나지 않는다 — 「기말현금」 자리에 「영업이익」이 들어간 채 결과가
//   그럴듯하게 나오고, 그 표가 회의에 올라간다. **조용한 거짓말**이다.
//   화면마다 제 나름의 순서를 들고 있으면 이 사고는 다시 난다.
//
// ⚠️ 이름·단위는 서버(`core/calc_graph.py`)의 `DRIVER_KEYS` · `_require` 가 읽는 키와
//   **같아야 한다.** 여기서만 바꾸면 화면은 채웠는데 서버는 「없다」고 답한다.

export type FieldSpec = { key: string; label: string; unit: string; hint?: string };

//: 기준값 — 사용자가 회사 실적에서 채운다.
//: ⚠️ 기본값을 «그럴듯한 숫자» 로 채우지 않는다. 채우면 사용자가 그것을 자기 회사
//:   값으로 착각한 채 회의에 들고 간다.
export const BASE_FIELDS: FieldSpec[] = [
  { key: 'production_qty', label: '생산량', unit: 'ton' },
  { key: 'ending_inventory', label: '기말재고', unit: 'ton' },
  { key: 'purchase_payment', label: '구매지급', unit: '원' },
  { key: 'ending_cash', label: '기말현금', unit: '원' },
  { key: 'operating_profit', label: '영업이익', unit: '원' },
  { key: 'power_cost', label: '전력비', unit: '원' },
  { key: 'period_days', label: '기간', unit: '일' },
];

//: 가정(Driver). ★ 서버 `core/calc_graph.DRIVER_KEYS` 와 같아야 한다.
export const DRIVER_FIELDS: FieldSpec[] = [
  { key: 'fx_rate_pct', label: '환율', unit: '%', hint: '오르면 수입 원료 대금이 늘어납니다' },
  { key: 'lead_time_days', label: '도입 지연', unit: '일', hint: '늦어진 만큼 생산이 줄어듭니다' },
  { key: 'power_price_pct', label: '전력단가', unit: '%', hint: '생산량에 비례해 원가에 붙습니다' },
];

/** 빈 칸은 `null`. ⚠️ 빈 칸을 0으로 읽지 않는다 — 「모른다」와 「0이다」는 다르다. */
export function num(v: string): number | null {
  if (!v.trim()) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
