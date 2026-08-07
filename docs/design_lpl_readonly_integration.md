# LPL 연계 Reference Profile

> 상태: LS 환경 Reference Profile 초안  
> 기준일: 2026-08-03  
> 상위 SSOT: [`design_external_engagement_system_integration.md`](design_external_engagement_system_integration.md)

LPL(LS Partner's Lounge)은 거래처·관세사·포워더·운송사 등 외부 참여자가 데이터를 입력하는 LS 환경의 기존 시스템이다.

이 문서는 LPL 전용 제품 기능을 정의하지 않는다. LPL은 범용 외부 협업 레거시 연계 표준을 검증하는 첫 Adapter Profile이다.

## 확정 원칙

- 외부 참여자는 계속 LPL만 사용한다.
- AI Factory Studio를 외부에 열지 않는다.
- 외부 사용자·게스트 조직·파트너 앱을 만들지 않는다.
- 첫 연계는 읽기 전용 API/MCP/DB View/Export 중 LPL이 공식 제공하는 방식으로 한다.
- LPL 시스템명·필드·인증은 Profile에만 존재하고 제품 코어에 하드코딩하지 않는다.

## Discovery 대기 항목

- 공식 API 또는 MCP 제공 여부
- 인증·네트워크·테스트 환경
- 계약·선적·통관·운송 관련 엔터티와 필드
- 사건 ID·버전·수정·취소·증분 조회 방식
- pagination·rate limit·SLA
- 데이터·시스템 오너와 사용 승인 범위

## 최초 논리 계약 후보

- `partner_submission`
- `shipment_milestone`
- `customs_clearance`
- `transport_milestone`

실제 LPL 물리 이름은 Discovery 이후 Profile의 `query_contracts.json`, `field_crosswalk.json`, `status_mapping.json`으로 매핑한다.

## 완료 기준

- `ls_lpl` Profile을 제거해도 제품 코어 테스트가 통과한다.
- 다른 Mock 외부 포털 Profile이 동일 Query Contract 테스트를 통과한다.
- LPL 값은 원천키·버전·`as_of`와 함께 추적된다.
- Twin은 TTL 조회값이 아니라 CERTIFIED Snapshot을 사용한다.

