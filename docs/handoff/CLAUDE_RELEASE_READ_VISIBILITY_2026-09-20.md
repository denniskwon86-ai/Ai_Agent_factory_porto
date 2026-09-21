# RELEASE-READ-VISIBILITY-01 — 릴리스 단건 조회 열람 경계 (P1)

작성: Claude Code · 2026-09-20 KST. 지시: `CODEX_D01_REVIEW_NEXT_2026-09-20.md` §2.
**커밋·푸시 없음 · LLM 0 · 운영 무접촉 · 권한표/역할/CORS 무변경.**
전체 **21/40=52.5%** 마지막 인정치 유지.

## 수정 파일

| 파일 | 무엇 |
|---|---|
| `api/routes/factory_control.py` — `get_release` | ① 목록과 **같은** 가시성 판정 적용(fail-closed) ② 상태 확인 실패 시 실행 payload 차단 ③ 읽기 오류의 예외 원문·경로 비노출 |
| `tests/test_release_item_visibility.py` (신규) | 8건 |
| `frontend/src/components/ControlPanel.tsx` | 주석의 실측 주장만 정정(§아래) |

순서는 지시대로입니다 — 경로 ID 검증 → `assert_identified` → JSON 로드(소유 project_id 용)
→ **가시성 확인** → 그 다음에야 승격·lifecycle 조회. 응답은 **없는 릴리스와 같은 404** 이고
사유를 「타 회사」·「소유자 없음」으로 세분하지 않습니다. 자료는 건드리지 않습니다.

## 정상 / 거절 대조 (수정 «후» 측정)

```
API            rel_sent_synthetic_01(소유 프로젝트 비가시)  → 404 「결과물을 찾을 수 없습니다.」 · 코드 0
               rel_no_such_thing_9999(없는 릴리스)          → 404 «같은 문구»
               prj_…_150809(가시)                           → 200 · 본문 정상
               library/list                                  → 2건 그대로(회귀 없음)
화면 직접링크  비가시 → 「현재 회사·권한에서 결과물을 찾을 수 없습니다.」 · 내용 0
               가시   → 결과물 실행 화면 정상(미리보기·문서 탭 전부)
```

## 시험

```
tests/test_release_item_visibility.py        8 passed   (격리 러너, strict-writes)
tests/test_release_list_visibility.py        2 passed   (기존, 회귀 없음)
sources_unchanged: true · protected_assets_unchanged: true · blocked_file_writes: []

극성  ① 가시성 가드 제거      → 6 failed / 2 passed   (음성 실패·양성 통과) 원복✔
      ② payload 차단 되돌림   → 1 failed / 7 passed                        원복✔
```

8건에는 **대역이 아닌 실제 판정 경로** 1건이 포함됩니다 — `project_meta.json` →
`project_visibility.project_visible` 을 그대로 태우고 테넌트 축만 갈라 가시/비가시를 만듭니다.

## ⚠️ 이번에 걸린 함정 3가지

1. **주트리를 고치고 격리 화면으로 재면 «옛 코드» 를 잰다.** 격리 서버는 워크트리
   `C:\sentwt` 의 사본을 실행합니다. 서버를 재기동해도 200 이 그대로라 처음엔 「수정이
   안 먹었다」로 보였습니다. → 그 **한 파일만** 워크트리에 동기화한 뒤 재기동하니 404.
   **원복 대상에 추가**: `C:\sentwt\api\routes\factory_control.py`.
2. **시험 `scope` 대역이 실제 `AccessScope` 모양과 달랐다.** `unrestricted` 가 없어
   `ownership_visible` 이 예외 → 차단으로 답했고, **양성 대조가 제품 결함처럼 빨강**이었습니다.
3. **`enterprise_scope_id` 를 비워 두면 `RESOURCE_UNBOUND` 로 비노출.** 「범위 미지정은
   전사 공용이 아니라 비노출」이라는 규칙 그대로입니다. 역시 양성 대조가 먼저 죽었습니다.

②③ 둘 다 **내가 지어낸 fixture 가 정본 계약과 달라서** 난 실패입니다. 고치기 전에 정본
판정 함수를 직접 호출해 사유(`RESOURCE_UNBOUND`)를 찍어 확인했습니다.

## 주석 정정 (지시 §1)

`ControlPanel` 상단 `tellCommandResult` 주석의 「유료 LLM 재실행 … 둘 다 실측했다」를
**「위험 가능성이며 실측된 사건이 아니다」** 로 고쳤습니다 — 재전송은 공용 계층이 이미
막고, 이 파일은 LLM 을 한 번도 실행하지 않았습니다. 위험과 관찰을 섞지 않습니다.

## 남은 조건 / 다음 예상

```
이번 마감      릴리스 단건 조회 열람 경계 (P1)
남은 지시 항목 A 재개 후 상태 의미 조사        10~15분
               B 라벨(생성 시각 + release_id)  10~15분
               C 문서 이탈 보호 미발동 «원인 확인»  (원인 미확인으로 기록 중)
D01 잔여       반복 업무(사용자·자료 필요) · 권한은 이번 보완 후 재검증 대상
```

**주의:** 이 보완으로 **「다른 회사 자료 유출」을 실증한 것은 아닙니다.** fixture 의 소유
프로젝트가 «없는» 경우와 «실재하는 타 문맥» 은 다르며, 후자의 격리 fixture 는
`test_item_uses_the_real_visibility_decision` 안에서만 만들었습니다(실서버 아님).
