# C. 문서 이탈 보호 — 미발동 «원인 확인»

작성: Claude Code · 2026-09-20 KST. 지시: `CODEX_D01_REVIEW_NEXT_2026-09-20.md` §3-C.
**제품 코드 변경 0 · 새 `beforeunload` 추가 0 · LLM 0 · 운영 무접촉.**
전체 **21/40=52.5%** 마지막 인정치 유지.

---

## 결론

**제품 보호는 등록되고, 발화하고, `preventDefault()` 까지 한다.**
이동이 그대로 진행된 것은 **자동화가 확인창을 처리(무시)했기 때문**이다.
사용자에게 실제로 확인창이 뜨는지는 **NOT_VERIFIED** — 내 도구가 그 창을 띄우지 못한다.
**의도된 무보호가 아니다.** 앞 보고의 「앱 안만 보호하는 설계」 해석을 **철회한다.**

## 어디에 등록되어 있나 (소스)

| 컴포넌트 | 조건 |
|---|---|
| `components/BuildStartDialog.tsx` | `hasInput && !saved`, 또는 `creationState` 가 `PENDING`·`UNKNOWN` |
| `factory/AdaptiveProductionStudio.tsx` | `projectId && studioInputMemory.hasInputs(projectId)` |

둘 다 `event.preventDefault(); event.returnValue = ''`.
`studioLeaveGuard` 주석의 뜻은 **「문서 이탈 보호가 앱 내부 보호를 대신하지 못한다」** 이지
「문서 이탈을 보호하지 않는다」가 아니다 — Codex 지적이 맞다.

## 제한 재현 (BuildStartDialog)

측정기는 **제품 핸들러 «뒤»** 에 붙인 `beforeunload` 리스너 하나다. 값을 바꾸지 않고
`defaultPrevented` 만 읽어 `sessionStorage` 에 남긴다(문서가 바뀌어도 살아남게).

```
① 미저장 입력 있음 — 앱 안에서 「＋ 새 앱」 → 편집기 → 입력 «값 확인»(B6-BEFOREUNLOAD-PROBE)
   문서 이동(navigate, force 미지정=기본)
   → {"fired": true, "defaultPrevented": true}      ← 제품 보호가 실제로 막았다
   → 그럼에도 이동함 · 입력 사라짐

② ★ 음성 대조 — 편집기 없음(입력 0)
   같은 문서 이동
   → {"fired": true, "defaultPrevented": false}     ← 보호가 «등록되지 않았다»
```

**두 경우가 갈린다** — 계측기가 늘 `true` 를 내는 것이 아니다. 즉 `defaultPrevented: true` 는
제품 보호가 그 조건에서만 작동한다는 증거다.

## 무엇이 확인되고 무엇이 아닌가

| 층 | 판정 |
|---|---|
| 조건에 맞을 때 `beforeunload` **등록** | **확인** |
| 문서 이탈 시 **발화** | **확인** |
| 핸들러가 **`preventDefault()`** 호출 | **확인**(`defaultPrevented: true`) |
| 브라우저가 **사용자에게 확인창**을 띄움 | **NOT_VERIFIED** — 도구가 그 창을 띄우지/보여주지 않음 |
| 사용자가 **취소**하면 남는가 / **계속**하면 가는가 | **NOT_VERIFIED** — 확인창이 없으니 고를 수 없음 |
| 자동화가 확인창을 처리했는가 | **그렇다** — `force` 를 주지 않았는데도 이동했다 |

★ 앞선 「입력이 사라졌다」 관찰은 **보존한다.** 다만 원인은 **보호 부재가 아니라 자동화**다.
그리고 문서 이동에서 입력이 사라지는 것 자체는 예상 동작이다 — `studioInputMemory` 는
모듈 Map 이라 **문서 새로고침을 넘기지 못한다**(영구 저장을 보장하지 않는다).

## 하지 않은 것

- **새 `beforeunload` 를 추가하지 않았다**(중복 금지 지시).
- `AdaptiveProductionStudio` 쪽 등록은 **소스로만 확인**했고 따로 태우지 않았다.
- `localStorage` 등 영속 저장을 새로 넣지 않았다. 새로고침·종료·강제 종료의 보존은
  여전히 보장하지 않는다.

## 남은 것

```
A 재개 상태 최소안 구현     지시 대기
B 확인창 렌더 문자열        NOT_VERIFIED(도구 한계) — 다음 브라우저 차례 재시도
C 사용자 확인창 실물        NOT_VERIFIED — 자동화가 띄우지 못함. 사람이 한 번 눌러 보면 닫힌다
```
