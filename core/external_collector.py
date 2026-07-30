"""[§12.3] 외부환경 인텔리전스 **수집기** — 파일(CSV) · 네트워크(API/RSS).

## 2026-07-29 판단을 뒤집지 않고 채운 방식

당시 수집기를 만들지 않은 이유는 정당했다: **승인된 원천이 하나도 없는데** 수집기를 만들면
아무도 호출하지 않는 죽은 코드이거나, "돌아가는 것처럼 보이려고" 값을 지어내는 경로가 된다.

그 함정을 피하는 방법은 수집기를 안 만드는 것이 아니라, **값을 지어낼 수 없는 구조로** 만드는
것이다. 이 모듈의 모든 경로는 다음을 지킨다:

  1. **원천 없이는 아무것도 적재하지 않는다.** 승인된(`enabled=1`) 원천의 `source_id` 가
     필수다. 미승인 원천이면 `external_intelligence.record_observation()` 이 거부한다 —
     그 검증을 여기서 **다시 구현하지 않는다**(두 곳에서 판정하면 어긋난다).
  2. **등급은 원천에서 온다.** 호출자가 `grade` 를 올려 보낼 수 없다. 출처보다 값이 더
     신뢰될 수는 없다.
  3. **vintage 는 데이터에서 온다.** 없으면 그 행을 **건너뛰고 이유를 보고**한다. 수집기가
     `vintage=오늘` 을 자동으로 채우면 §12.5 의 재현성이 조용히 깨진다 — "그 계획이 당시
     어떤 발표값을 썼는지"가 영원히 불명확해진다.
  4. **파싱 실패를 0 으로 만들지 않는다.** 빈 칸·문자열은 건너뛴다. 0 으로 채우면 지표가
     "값이 0" 으로 보이고, 그것은 결손보다 나쁘다(결손은 보이지만 0 은 계산에 섞인다).
  5. **`dry_run` 이 기본이다.** 적재 전에 "무엇이 들어가고 무엇이 왜 빠지는지"를 먼저 본다.
  6. **범용 웹 크롤러를 만들지 않는다**(§12.4 명시). 네트워크 수집은 **등록된 원천의
     `base_url`** 만 호출한다. 임의 URL 을 인자로 받지 않는다 — 그것이 크롤러의 정의다.

## 왜 두 어댑터인가 (2026-07-30 사용자 결정)

  · **CSV** — 현업이 올린 파일. 전사 파일럿의 실제 유입 경로이고 네트워크·인증이 필요 없다.
  · **API/RSS** — 승인된 원천의 주기 수집. 원천이 승인될 때까지는 호출되지 않지만, 골격이
    있어야 원천 승인 즉시 배선만으로 돌아간다.

⚠️ 스케줄러는 여기 없다. 주기 실행은 운영 스케줄러(cron/Task Scheduler)가 `collect_source()`
  를 부르는 것으로 충분하고, 프로세스 안에 타이머를 두면 다중 워커에서 같은 수집이 N배로 돈다.

LLM 0콜.
"""
import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

#: CSV 열 이름 후보. 현업이 만든 파일의 머리글은 통일돼 있지 않다 — 매핑을 강요하면
#: 사람들이 파일을 고치다 지쳐 시스템 밖에서 값을 주고받는다.
_COL_ALIASES = {
    "indicator": ("indicator", "indicator_code", "code", "지표", "지표코드"),
    "observed_at": ("observed_at", "date", "period", "관측일", "기준일", "일자"),
    "value": ("value", "amount", "값", "수치"),
    "vintage": ("vintage", "published", "published_at", "발표일", "빈티지"),
    "unit": ("unit", "단위"),
}


class CollectorError(ValueError):
    """정책 위반·형식 오류 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pick(row: Dict[str, Any], key: str) -> str:
    """머리글 별칭을 흡수해 값을 꺼낸다(대소문자·공백 무시)."""
    norm = {(k or "").strip().lower(): v for k, v in row.items()}
    for cand in _COL_ALIASES[key]:
        if cand in norm and str(norm[cand]).strip():
            return str(norm[cand]).strip()
    return ""


def _num(text: str) -> Optional[float]:
    """숫자 파싱. **실패는 None 이고 0 이 아니다.**

    ★ 0 으로 채우면 지표가 "값이 0"으로 보인다. 결손은 리포트에 드러나지만 0 은 계산에 섞여
      들어가 아무도 눈치채지 못한다 — 결손보다 나쁘다."""
    t = (text or "").replace(",", "").replace("%", "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


class ExternalCollector:
    def __init__(self, intel=None):
        if intel is None:
            from core.external_intelligence import external_intelligence
            intel = external_intelligence
        self.intel = intel

    # ── 공통 적재 ─────────────────────────────────────────────────────────
    def _source_or_raise(self, source_id: str) -> Dict[str, Any]:
        """승인된 원천인지 확인한다.

        ★ 여기서 미리 막는 이유는 **오류 메시지의 품질**이다. 적재 단계에서 행마다 같은 이유로
          실패하면 사용자는 "파일이 잘못됐나"를 의심한다. 단 최종 강제는 여전히
          `record_observation()` 이 한다 — 검증을 두 곳에서 구현하지 않는다."""
        if not (source_id or "").strip():
            raise CollectorError(
                "source_id 는 필수입니다 — 출처 없는 값은 적재하지 않습니다(§12.4). "
                "원천을 먼저 등록·승인하십시오.")
        src = self.intel.get_source(source_id)
        if not src:
            raise CollectorError(f"존재하지 않는 원천입니다: {source_id}")
        if not src["enabled"]:
            raise CollectorError(
                f"승인되지 않은 원천입니다: {src['name']}. `approve_source()` 로 먼저 "
                f"승인하십시오 — 승인은 '이 출처의 값을 회사 계획에 쓴다'는 결정입니다(§12.4).")
        return src

    def _ingest(self, records: List[Dict[str, Any]], src: Dict[str, Any],
                dry_run: bool, origin: str) -> Dict[str, Any]:
        """정규화된 레코드를 적재한다. **건너뛴 것은 이유와 함께 돌려준다.**"""
        loaded, skipped = [], []
        for i, rec in enumerate(records, start=1):
            why = rec.get("_skip")
            if why:
                skipped.append({"row": i, "reason": why, "raw": rec.get("_raw", "")})
                continue
            if dry_run:
                loaded.append({"row": i, **{k: v for k, v in rec.items()
                                            if not k.startswith("_")}})
                continue
            try:
                out = self.intel.record_observation(
                    indicator_code=rec["indicator"], observed_at=rec["observed_at"],
                    value=rec["value"], vintage=rec["vintage"],
                    # ★ 등급은 **원천에서** 온다. 호출자가 올려 보낼 수 없다.
                    grade=src["trust_grade"], source_id=src["source_id"],
                    unit=rec.get("unit", ""), published_at=rec.get("vintage", ""),
                    source_record_ref=f"{origin}#{i}",
                    note=f"수집기 적재({origin})")
                loaded.append({"row": i, "observation_id": out["observation_id"],
                               "indicator": rec["indicator"],
                               "observed_at": rec["observed_at"], "value": rec["value"],
                               "vintage": rec["vintage"], "grade": out["grade"]})
            except Exception as e:
                # 한 행의 실패가 전체를 죽이지 않는다. 단 **조용히 넘기지 않는다.**
                skipped.append({"row": i, "reason": f"적재 거부: {e}",
                                "raw": rec.get("_raw", "")})
        return {
            "source_id": src["source_id"], "source_name": src["name"],
            "grade": src["trust_grade"], "origin": origin,
            "dry_run": bool(dry_run), "collected_at": _now(),
            "loaded": len(loaded), "skipped": len(skipped),
            "items": loaded, "skipped_items": skipped,
            "note": (("[예행] 실제로 적재하지 않았습니다. "
                      if dry_run else "")
                     + f"적재 {len(loaded)}건 · 건너뜀 {len(skipped)}건. "
                     + ("건너뛴 행은 `skipped_items` 의 이유를 확인하십시오 — 값을 0 이나 "
                        "오늘 날짜로 채우지 않습니다(그렇게 채우면 결손이 계산에 섞입니다)."
                        if skipped else "")),
        }

    # ── ① 파일(CSV) 수집 ─────────────────────────────────────────────────
    def collect_csv(self, text: str, source_id: str, dry_run: bool = True,
                    default_indicator: str = "") -> Dict[str, Any]:
        """현업이 올린 CSV 를 적재한다.

        열 이름은 별칭을 흡수한다(`지표`·`code`·`indicator_code` 등). 필수는
        지표·관측일·값·vintage 이며, **vintage 가 없으면 그 행을 건너뛴다** — 자동으로 오늘
        날짜를 넣으면 §12.5 재현성이 조용히 깨진다."""
        src = self._source_or_raise(source_id)
        if not (text or "").strip():
            raise CollectorError("빈 파일입니다 — 적재할 내용이 없습니다.")
        try:
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        except csv.Error as e:
            raise CollectorError(f"CSV 를 읽을 수 없습니다: {e}")
        if not rows:
            raise CollectorError("머리글만 있고 데이터 행이 없습니다.")

        recs: List[Dict[str, Any]] = []
        for row in rows:
            raw = json.dumps({k: v for k, v in row.items() if k}, ensure_ascii=False)[:200]
            code = _pick(row, "indicator") or default_indicator
            observed = _pick(row, "observed_at")
            value = _num(_pick(row, "value"))
            vintage = _pick(row, "vintage")
            rec: Dict[str, Any] = {"_raw": raw}
            if not code:
                rec["_skip"] = "지표 코드가 없습니다(열 이름: indicator/code/지표)."
            elif not observed:
                rec["_skip"] = "관측일이 없습니다(열 이름: observed_at/date/기준일)."
            elif value is None:
                rec["_skip"] = ("값이 비었거나 숫자가 아닙니다 — 0 으로 채우지 않습니다"
                                "(결손이 계산에 섞이면 아무도 눈치채지 못합니다).")
            elif not vintage:
                rec["_skip"] = ("vintage(발표일)가 없습니다 — 자동으로 오늘 날짜를 넣지 "
                                "않습니다(§12.5: 그 계획이 당시 어떤 발표값을 썼는지 재현할 "
                                "수 없게 됩니다).")
            else:
                rec.update({"indicator": code, "observed_at": observed, "value": value,
                            "vintage": vintage, "unit": _pick(row, "unit")})
            recs.append(rec)
        return self._ingest(recs, src, dry_run, origin="csv")

    # ── ② 네트워크(API/RSS) 수집 ─────────────────────────────────────────
    def collect_source(self, source_id: str, dry_run: bool = True,
                       fetcher: Optional[Callable[[str], str]] = None,
                       path: str = "", indicator_map: Optional[Dict[str, str]] = None,
                       timeout: float = 10.0) -> Dict[str, Any]:
        """**등록된 원천의 `base_url`** 을 호출해 적재한다.

        ⚠️ 임의 URL 을 받지 않는다 — 그것이 범용 웹 크롤러이고 §12.4 가 금지한 것이다.
          `path` 는 등록된 `base_url` 아래 상대 경로만 허용한다(절대 URL·`..` 거부).

        `fetcher` 는 테스트·오프라인 주입용이다. 주지 않으면 표준 라이브러리로 GET 한다 —
        의존성을 늘리지 않는다.

        지원 형식: JSON(관측 배열) · CSV · RSS(제목만 있으므로 **수치로 적재하지 않는다**)."""
        src = self._source_or_raise(source_id)
        stype = (src["source_type"] or "").upper()
        if stype == "RSS":
            # RSS 는 기사 제목·링크다. 수치가 아니므로 관측값으로 적재하지 않는다 —
            #   기사에서 숫자를 추출해 적재하는 것이 정확히 §12.1 이 금지한 경로다.
            raise CollectorError(
                "RSS 원천은 관측값으로 적재하지 않습니다 — 기사 본문에서 수치를 추출해 지표로 "
                "쓰는 것은 §12.1 이 금지한 경로입니다(bronze 등급 '사건 후보'로만 씁니다). "
                "사건 후보 적재는 지표 수집이 아니라 별도 경로입니다.")
        if stype not in ("API", "CSV", "PROVIDER_API"):
            raise CollectorError(
                f"이 원천 형식은 자동 수집을 지원하지 않습니다: {stype}. "
                f"REPORT·WEB 은 사람이 확인해 CSV 로 올리십시오(§12.4 — 범용 크롤러 금지).")

        url = self._resolve_url(src, path)
        if fetcher is None:
            fetcher = self._http_get_factory(timeout)
        try:
            body = fetcher(url)
        except Exception as e:
            raise CollectorError(
                f"원천을 호출할 수 없습니다({url}): {e}. 네트워크·인증을 확인하십시오 — "
                f"호출 실패를 빈 결과로 처리하지 않습니다(빈 결과는 '값이 없다'로 읽힙니다).")

        text = body if isinstance(body, str) else str(body)
        if stype in ("API", "PROVIDER_API") and text.strip().startswith(("{", "[")):
            recs = self._from_json(text, indicator_map or {})
            return self._ingest(recs, src, dry_run, origin=f"api:{url}")
        # 원천이 CSV 를 주는 경우 — 파일 경로와 같은 파서를 쓴다(두 파서는 반드시 어긋난다).
        out = self.collect_csv(text, source_id, dry_run=dry_run)
        out["origin"] = f"{stype.lower()}:{url}"
        return out

    @staticmethod
    def _resolve_url(src: Dict[str, Any], path: str) -> str:
        base = (src.get("base_url") or "").strip()
        if not base:
            raise CollectorError(
                f"원천에 base_url 이 없습니다: {src['name']}. 등록 정보를 보완하십시오 — "
                f"수집기는 **등록된 주소만** 호출합니다(임의 URL 수집은 크롤러입니다).")
        p = (path or "").strip()
        if not p:
            return base
        if "://" in p or p.startswith("//"):
            raise CollectorError(
                "path 에 절대 URL 을 줄 수 없습니다 — 등록된 원천 밖을 호출하는 것은 "
                "범용 크롤러이고 §12.4 가 금지합니다.")
        if ".." in p:
            raise CollectorError("path 에 '..' 를 쓸 수 없습니다(등록 주소 이탈 방지).")
        return base.rstrip("/") + "/" + p.lstrip("/")

    @staticmethod
    def _http_get_factory(timeout: float) -> Callable[[str], str]:
        def _get(url: str) -> str:
            # 표준 라이브러리만 쓴다 — 수집기 하나 때문에 의존성을 늘리지 않는다.
            from urllib.request import Request, urlopen
            req = Request(url, headers={"User-Agent": "AIFactory-ExternalCollector/1.0"})
            with urlopen(req, timeout=timeout) as resp:      # nosec - 등록된 원천 주소만
                return resp.read().decode("utf-8", errors="replace")
        return _get

    @staticmethod
    def _from_json(text: str, indicator_map: Dict[str, str]) -> List[Dict[str, Any]]:
        """JSON 응답을 관측 레코드로 정규화한다.

        받아들이는 형태: 배열, 또는 `data`/`observations`/`results` 키 아래 배열.
        원천마다 필드명이 다르므로 `indicator_map` 으로 **명시 매핑**을 받는다 — 추측해서
        맞추면 조용히 엉뚱한 열을 값으로 읽는다."""
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as e:
            raise CollectorError(f"JSON 을 해석할 수 없습니다: {e}")
        rows: Iterable = ()
        if isinstance(doc, list):
            rows = doc
        elif isinstance(doc, dict):
            for k in ("data", "observations", "results", "items"):
                if isinstance(doc.get(k), list):
                    rows = doc[k]
                    break
            else:
                raise CollectorError(
                    "JSON 에서 관측 배열을 찾지 못했습니다(허용 키: data·observations·"
                    "results·items 또는 최상위 배열).")
        recs: List[Dict[str, Any]] = []
        inv = {v: k for k, v in (indicator_map or {}).items()}
        for item in rows:
            if not isinstance(item, dict):
                recs.append({"_skip": "객체가 아닌 항목", "_raw": str(item)[:120]})
                continue
            mapped = {std: item.get(src_key) for src_key, std in (indicator_map or {}).items()}
            get = (lambda key: (mapped.get(key) if mapped.get(key) is not None
                                else item.get(key)))
            code, observed = get("indicator"), get("observed_at")
            value, vintage = _num(str(get("value") or "")), get("vintage")
            raw = json.dumps(item, ensure_ascii=False)[:200]
            if not code:
                recs.append({"_skip": f"지표 코드가 없습니다(매핑: {inv or '없음'})", "_raw": raw})
            elif not observed:
                recs.append({"_skip": "관측일이 없습니다", "_raw": raw})
            elif value is None:
                recs.append({"_skip": "값이 숫자가 아닙니다 — 0 으로 채우지 않습니다", "_raw": raw})
            elif not vintage:
                recs.append({"_skip": "vintage(발표일)가 없습니다(§12.5)", "_raw": raw})
            else:
                recs.append({"indicator": str(code), "observed_at": str(observed),
                             "value": value, "vintage": str(vintage),
                             "unit": str(get("unit") or ""), "_raw": raw})
        return recs

    # ── 진단 ─────────────────────────────────────────────────────────────
    def collectable(self) -> Dict[str, Any]:
        """지금 수집할 수 있는 원천이 무엇인가 — **없으면 없다고 말한다.**

        ★ 2026-07-29 에 수집기를 만들지 않은 이유가 "승인된 원천이 0" 이었다. 그 상태를 이제
          숨기지 않고 이 함수가 답한다 — 수집기가 있는데 아무것도 안 들어오는 이유를 사람이
          추측하게 두면, 다음 사람은 "수집기가 고장났다"로 결론짓는다."""
        try:
            sources = self.intel.list_sources(enabled_only=True)
        except Exception as e:
            return {"ready": False, "sources": [], "note": f"원천 조회 실패: {e}"}
        auto = [s for s in sources
                if (s.get("source_type") or "").upper() in ("API", "CSV", "PROVIDER_API")]
        return {
            "ready": bool(sources),
            "approved_total": len(sources),
            "auto_collectable": len(auto),
            "sources": [{"source_id": s["source_id"], "name": s["name"],
                         "source_type": s["source_type"], "trust_grade": s["trust_grade"],
                         "auto": (s.get("source_type") or "").upper()
                                 in ("API", "CSV", "PROVIDER_API")}
                        for s in sources],
            "note": ("승인된 외부 원천이 없습니다 — 수집기는 준비돼 있으나 적재할 출처가 "
                     "없습니다. `register_source()` 로 등록하고 `approve_source()` 로 "
                     "승인하십시오(승인은 '이 출처의 값을 회사 계획에 쓴다'는 결정입니다). "
                     "그전까지는 CSV 업로드도 거부됩니다 — 출처 없는 값을 받지 않는 것이 "
                     "이 모듈의 계약입니다." if not sources else
                     f"승인된 원천 {len(sources)}건 중 {len(auto)}건이 자동 수집 대상입니다"
                     f"(REPORT·WEB·RSS 는 사람이 확인해 CSV 로 올립니다 — §12.4 범용 크롤러 "
                     f"금지)."),
        }


external_collector = ExternalCollector()
