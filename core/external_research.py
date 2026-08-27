"""회사 기준정보 기반 대외 조사 프로필과 수집 작업 상태.

이 모듈은 웹에서 무엇이든 찾는 크롤러를 만들지 않는다. 사람이 승인한 회사·도메인·목적을
먼저 봉인하고, 수집 작업은 그 봉인된 프로필만 참조한다. 실제 HTTP 수집과 후보 추출은 이
계약의 소비자이며 다음 단계에서 연결한다.

저장소는 기존 외부 인텔리전스와 같은 ``external_intelligence.db`` 를 사용하지만, 전역 객체를
import 하는 것만으로 파일을 만들지 않도록 스키마 준비는 최초 호출 시점까지 미룬다.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import sqlite3
import threading
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

from core.paths import data_path


_DB_PATH = data_path("external_intelligence.db")

PROFILE_STATUSES = ("DRAFT", "REVIEW_REQUIRED", "APPROVED", "PAUSED", "RETIRED")
BOT_KINDS = (
    "COMPANY_BASE_RESEARCH",
    "INDICATOR_COLLECTOR",
    "EXTERNAL_EVENT_MONITOR",
    "QUALITY_CHANGE_MONITOR",
)
JOB_STATUSES = (
    "SCHEDULED",
    "RUNNING",
    "CANDIDATE_READY",
    "ACCEPTED",
    "REJECTED",
    "FAILED",
    "CANCELLED",
)

_DDL = """
CREATE TABLE IF NOT EXISTS company_research_profiles (
    profile_id            TEXT PRIMARY KEY,
    legal_entity_id       TEXT NOT NULL,
    company_name          TEXT NOT NULL,
    official_domains_json TEXT NOT NULL,
    official_urls_json    TEXT NOT NULL,
    business_keywords_json TEXT NOT NULL,
    product_keywords_json TEXT NOT NULL,
    regions_json          TEXT NOT NULL,
    competitor_names_json TEXT NOT NULL,
    material_keywords_json TEXT NOT NULL,
    required_indicators_json TEXT NOT NULL,
    collection_purpose    TEXT NOT NULL,
    schedule_rule         TEXT NOT NULL DEFAULT '',
    owner_id              TEXT NOT NULL,
    retention_days        INTEGER NOT NULL,
    status                TEXT NOT NULL,
    approved_by           TEXT NOT NULL DEFAULT '',
    approved_at           TEXT NOT NULL DEFAULT '',
    fingerprint           TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_profile_entity
    ON company_research_profiles(legal_entity_id, status);

CREATE TABLE IF NOT EXISTS external_collection_jobs (
    job_id              TEXT PRIMARY KEY,
    profile_id          TEXT NOT NULL,
    bot_kind            TEXT NOT NULL,
    status              TEXT NOT NULL,
    dry_run             INTEGER NOT NULL DEFAULT 1,
    profile_fingerprint TEXT NOT NULL,
    requested_by        TEXT NOT NULL,
    requested_at        TEXT NOT NULL,
    started_at          TEXT NOT NULL DEFAULT '',
    finished_at         TEXT NOT NULL DEFAULT '',
    result_summary_json TEXT NOT NULL DEFAULT '{}',
    error               TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_external_job_profile
    ON external_collection_jobs(profile_id, requested_at DESC);

CREATE TABLE IF NOT EXISTS external_research_candidates (
    candidate_id       TEXT PRIMARY KEY,
    job_id             TEXT NOT NULL,
    profile_id         TEXT NOT NULL,
    candidate_kind     TEXT NOT NULL,
    source_url         TEXT NOT NULL,
    title              TEXT NOT NULL DEFAULT '',
    summary            TEXT NOT NULL DEFAULT '',
    evidence_json      TEXT NOT NULL DEFAULT '{}',
    content_hash       TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'CANDIDATE_READY',
    reviewed_by        TEXT NOT NULL DEFAULT '',
    reviewed_at        TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    UNIQUE(job_id, candidate_kind, source_url, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_external_candidate_job
    ON external_research_candidates(job_id, status, created_at);
"""


class ExternalResearchError(ValueError):
    """검증·상태 전이 위반 등 사용자 요청을 고쳐야 하는 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_list(values: Optional[Iterable[Any]]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values or ():
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _domain(value: str) -> str:
    raw = (value or "").strip().lower().rstrip(".")
    if "://" in raw or "/" in raw or "@" in raw or not raw or "." not in raw:
        raise ExternalResearchError(
            f"허용 도메인은 scheme·경로 없는 호스트명이어야 합니다: {value!r}")
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        pass
    else:
        raise ExternalResearchError("허용 도메인은 IP 주소가 아니라 공식 호스트명이어야 합니다.")
    return raw


def _host_allowed(host: str, domains: Iterable[str]) -> bool:
    h = (host or "").lower().rstrip(".")
    return any(h == d or h.endswith("." + d) for d in domains)


def _official_url(value: str, domains: Iterable[str]) -> str:
    raw = (value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ExternalResearchError(
            f"공식 URL은 사용자정보 없는 https 주소여야 합니다: {value!r}")
    if not _host_allowed(parsed.hostname, domains):
        raise ExternalResearchError(
            f"공식 URL이 승인 도메인 밖을 가리킵니다: {parsed.hostname}")
    if parsed.fragment:
        raise ExternalResearchError("공식 URL에는 fragment(#...)를 둘 수 없습니다.")
    return raw


def validate_public_target(url: str, domains: Iterable[str], resolver=socket.getaddrinfo) -> str:
    """승인 도메인의 공개 HTTPS 주소만 허용한다.

    프로필 승인만 믿고 바로 연결하면 DNS가 내부 주소를 가리키는 순간 SSRF가 된다. 최초 URL과
    모든 리디렉션에서 이 검사를 다시 호출한다.
    """
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ExternalResearchError("수집 대상은 사용자정보 없는 https 주소여야 합니다.")
    if parsed.port not in (None, 443):
        raise ExternalResearchError("수집 대상은 표준 HTTPS 포트(443)만 허용합니다.")
    if parsed.fragment:
        raise ExternalResearchError("수집 대상 URL에는 fragment를 둘 수 없습니다.")
    if not _host_allowed(host, domains):
        raise ExternalResearchError(f"수집 대상이 승인 도메인 밖입니다: {host}")
    try:
        infos = resolver(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ExternalResearchError(f"수집 대상 주소를 확인할 수 없습니다: {host}: {exc}") from exc
    addresses = {item[4][0] for item in infos}
    if not addresses:
        raise ExternalResearchError(f"수집 대상 주소가 없습니다: {host}")
    for raw in addresses:
        ip = ipaddress.ip_address(raw)
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            raise ExternalResearchError(f"공개망이 아닌 수집 대상은 허용하지 않습니다: {host}")
    return url


@dataclass(frozen=True)
class FetchDocument:
    url: str
    body: str
    content_type: str = "text/html"
    status: int = 200


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.links: List[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content", "").strip()
        elif tag.lower() == "a" and values.get("href"):
            self.links.append(values["href"].strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


class _SafeHttpFetcher:
    USER_AGENT = "LAXS-ExternalResearch/1.0"
    MAX_BYTES = 2 * 1024 * 1024

    def __call__(self, url: str, profile: Dict[str, Any]) -> FetchDocument:
        from urllib.error import HTTPError
        from urllib.request import HTTPRedirectHandler, Request, build_opener
        from urllib.robotparser import RobotFileParser

        domains = profile["official_domains"]

        class CheckedRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                validate_public_target(newurl, domains)
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        opener = build_opener(CheckedRedirect())

        def read(target: str, limit: int) -> FetchDocument:
            validate_public_target(target, domains)
            req = Request(target, headers={"User-Agent": self.USER_AGENT,
                                           "Accept": "text/html,application/rss+xml,application/xml"})
            with opener.open(req, timeout=10.0) as response:  # nosec - 대상·DNS·리디렉션 선검증
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise ExternalResearchError("수집 문서가 허용 크기를 초과했습니다.")
                content_type = response.headers.get_content_type()
                charset = response.headers.get_content_charset() or "utf-8"
                return FetchDocument(response.geturl(), raw.decode(charset, errors="replace"),
                                     content_type, int(response.status))

        parsed = urlparse(validate_public_target(url, domains))
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        robot = RobotFileParser()
        robot.set_url(robots_url)
        try:
            robot_doc = read(robots_url, 512 * 1024)
            robot.parse(robot_doc.body.splitlines())
        except HTTPError as exc:
            if exc.code not in (404, 410):
                raise ExternalResearchError(f"robots.txt를 확인할 수 없습니다: HTTP {exc.code}") from exc
            robot.parse([])
        except ExternalResearchError:
            raise
        except Exception as exc:
            raise ExternalResearchError(f"robots.txt를 확인할 수 없습니다: {exc}") from exc
        if not robot.can_fetch(self.USER_AGENT, url):
            raise ExternalResearchError("robots.txt 정책이 이 URL의 자동 수집을 허용하지 않습니다.")
        return read(url, self.MAX_BYTES)


def _semantic_material(values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "legal_entity_id": values["legal_entity_id"],
        "company_name": values["company_name"],
        "official_domains": sorted(values["official_domains"]),
        "official_urls": sorted(values["official_urls"]),
        "business_keywords": sorted(values["business_keywords"]),
        "product_keywords": sorted(values["product_keywords"]),
        "regions": sorted(values["regions"]),
        "competitor_names": sorted(values["competitor_names"]),
        "material_keywords": sorted(values["material_keywords"]),
        "required_indicators": sorted(values["required_indicators"]),
        "collection_purpose": values["collection_purpose"],
        "schedule_rule": values["schedule_rule"],
        "owner_id": values["owner_id"],
        "retention_days": values["retention_days"],
    }


def _fingerprint(values: Dict[str, Any]) -> str:
    body = json.dumps(_semantic_material(values), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class ExternalResearchStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = _DB_PATH if db_path is None else db_path
        self._lock = threading.RLock()
        self._ready_path = ""

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path:
            raise ExternalResearchError("외부 조사 저장소 경로가 비어 있습니다.")
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ready(self) -> None:
        target = os.path.realpath(self.db_path)
        if self._ready_path == target:
            return
        with self._lock:
            if self._ready_path == target:
                return
            with self._connect() as conn:
                conn.executescript(_DDL)
            self._ready_path = target

    @staticmethod
    def _decode(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        for key in (
            "official_domains", "official_urls", "business_keywords", "product_keywords",
            "regions", "competitor_names", "material_keywords", "required_indicators",
        ):
            packed = key + "_json"
            if packed in out:
                out[key] = json.loads(out.pop(packed))
        if "dry_run" in out:
            out["dry_run"] = bool(out["dry_run"])
        if "result_summary_json" in out:
            out["result_summary"] = json.loads(out.pop("result_summary_json"))
        return out

    @staticmethod
    def _normalise(payload: Dict[str, Any]) -> Dict[str, Any]:
        values = {
            "legal_entity_id": str(payload.get("legal_entity_id") or "").strip(),
            "company_name": str(payload.get("company_name") or "").strip(),
            "official_domains": sorted({_domain(x) for x in payload.get("official_domains") or []}),
            "business_keywords": _clean_list(payload.get("business_keywords")),
            "product_keywords": _clean_list(payload.get("product_keywords")),
            "regions": _clean_list(payload.get("regions")),
            "competitor_names": _clean_list(payload.get("competitor_names")),
            "material_keywords": _clean_list(payload.get("material_keywords")),
            "required_indicators": _clean_list(payload.get("required_indicators")),
            "collection_purpose": str(payload.get("collection_purpose") or "").strip(),
            "schedule_rule": str(payload.get("schedule_rule") or "").strip(),
            "owner_id": str(payload.get("owner_id") or "").strip(),
            "retention_days": int(payload.get("retention_days") or 0),
        }
        values["official_urls"] = sorted({
            _official_url(x, values["official_domains"])
            for x in payload.get("official_urls") or []
        })
        if not values["legal_entity_id"] or not values["company_name"]:
            raise ExternalResearchError("법인 ID와 회사명은 필수입니다.")
        if not values["owner_id"]:
            raise ExternalResearchError("조사 프로필 담당자는 필수입니다.")
        if not 1 <= values["retention_days"] <= 3650:
            raise ExternalResearchError("보존 기간은 1~3650일이어야 합니다.")
        return values

    def save_profile(self, payload: Dict[str, Any], profile_id: str = "") -> Dict[str, Any]:
        values = self._normalise(payload)
        fingerprint = _fingerprint(values)
        self._ready()
        pid = profile_id or f"erp_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            previous = conn.execute(
                "SELECT status,fingerprint,created_at,approved_by,approved_at "
                "FROM company_research_profiles WHERE profile_id=?", (pid,)).fetchone()
            if previous and previous["fingerprint"] == fingerprint:
                status = previous["status"]
                approved_by, approved_at = previous["approved_by"], previous["approved_at"]
            elif previous and previous["status"] == "APPROVED":
                status, approved_by, approved_at = "REVIEW_REQUIRED", "", ""
            else:
                status, approved_by, approved_at = "DRAFT", "", ""
            created_at = previous["created_at"] if previous else now
            packed = [json.dumps(values[k], ensure_ascii=False) for k in (
                "official_domains", "official_urls", "business_keywords", "product_keywords",
                "regions", "competitor_names", "material_keywords", "required_indicators",
            )]
            conn.execute(
                "INSERT INTO company_research_profiles(profile_id,legal_entity_id,company_name,"
                "official_domains_json,official_urls_json,business_keywords_json,"
                "product_keywords_json,regions_json,competitor_names_json,material_keywords_json,"
                "required_indicators_json,collection_purpose,schedule_rule,owner_id,retention_days,"
                "status,approved_by,approved_at,fingerprint,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(profile_id) DO UPDATE SET legal_entity_id=excluded.legal_entity_id,"
                "company_name=excluded.company_name,official_domains_json=excluded.official_domains_json,"
                "official_urls_json=excluded.official_urls_json,"
                "business_keywords_json=excluded.business_keywords_json,"
                "product_keywords_json=excluded.product_keywords_json,regions_json=excluded.regions_json,"
                "competitor_names_json=excluded.competitor_names_json,"
                "material_keywords_json=excluded.material_keywords_json,"
                "required_indicators_json=excluded.required_indicators_json,"
                "collection_purpose=excluded.collection_purpose,schedule_rule=excluded.schedule_rule,"
                "owner_id=excluded.owner_id,retention_days=excluded.retention_days,"
                "status=excluded.status,approved_by=excluded.approved_by,approved_at=excluded.approved_at,"
                "fingerprint=excluded.fingerprint,updated_at=excluded.updated_at",
                (pid, values["legal_entity_id"], values["company_name"], *packed,
                 values["collection_purpose"], values["schedule_rule"], values["owner_id"],
                 values["retention_days"], status, approved_by, approved_at, fingerprint,
                 created_at, now))
        return self.get_profile(pid)

    def get_profile(self, profile_id: str) -> Dict[str, Any]:
        self._ready()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM company_research_profiles WHERE profile_id=?", (profile_id,)
            ).fetchone()
        if not row:
            raise ExternalResearchError(f"존재하지 않는 회사 조사 프로필입니다: {profile_id}")
        return self._decode(row)

    def list_profiles(self) -> List[Dict[str, Any]]:
        self._ready()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM company_research_profiles ORDER BY updated_at DESC"
            ).fetchall()
        return [self._decode(row) for row in rows]

    def request_review(self, profile_id: str) -> Dict[str, Any]:
        profile = self.get_profile(profile_id)
        if not profile["official_domains"] or not profile["official_urls"]:
            raise ExternalResearchError("검토 요청 전 공식 도메인과 공식 URL이 필요합니다.")
        if not profile["collection_purpose"]:
            raise ExternalResearchError("검토 요청 전 수집 목적이 필요합니다.")
        if profile["status"] not in ("DRAFT", "REVIEW_REQUIRED"):
            raise ExternalResearchError(f"현재 상태에서는 검토 요청할 수 없습니다: {profile['status']}")
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE company_research_profiles SET status='REVIEW_REQUIRED',updated_at=? "
                         "WHERE profile_id=?", (_now(), profile_id))
        return self.get_profile(profile_id)

    def approve_profile(self, profile_id: str, approved_by: str,
                        expected_fingerprint: str) -> Dict[str, Any]:
        actor = (approved_by or "").strip()
        if not actor:
            raise ExternalResearchError("승인자는 필수입니다.")
        profile = self.get_profile(profile_id)
        if profile["status"] != "REVIEW_REQUIRED":
            raise ExternalResearchError("검토 요청 상태의 프로필만 승인할 수 있습니다.")
        if expected_fingerprint != profile["fingerprint"]:
            raise ExternalResearchError("검토한 프로필과 현재 프로필의 지문이 다릅니다.")
        now = _now()
        with self._lock, self._connect() as conn:
            changed = conn.execute(
                "UPDATE company_research_profiles SET status='APPROVED',approved_by=?,"
                "approved_at=?,updated_at=? WHERE profile_id=? AND status='REVIEW_REQUIRED' "
                "AND fingerprint=?", (actor, now, now, profile_id, expected_fingerprint)).rowcount
            if changed != 1:
                raise ExternalResearchError("승인 직전에 프로필 상태나 지문이 바뀌었습니다.")
        return self.get_profile(profile_id)

    def schedule_job(self, profile_id: str, bot_kind: str, requested_by: str,
                     dry_run: bool = True) -> Dict[str, Any]:
        if bot_kind not in BOT_KINDS:
            raise ExternalResearchError(f"지원하지 않는 조사 봇입니다: {bot_kind}")
        actor = (requested_by or "").strip()
        if not actor:
            raise ExternalResearchError("작업 요청자는 필수입니다.")
        if not dry_run:
            raise ExternalResearchError(
                "회사 조사 봇은 현재 dry-run 후보 생성만 허용합니다. 확정 적재는 지원하지 않습니다.")
        profile = self.get_profile(profile_id)
        if profile["status"] != "APPROVED":
            raise ExternalResearchError("승인된 회사 조사 프로필만 수집 작업을 예약할 수 있습니다.")
        jid, now = f"erj_{uuid.uuid4().hex[:12]}", _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO external_collection_jobs(job_id,profile_id,bot_kind,status,dry_run,"
                "profile_fingerprint,requested_by,requested_at) VALUES(?,?,?,'SCHEDULED',?,?,?,?)",
                (jid, profile_id, bot_kind, 1 if dry_run else 0,
                 profile["fingerprint"], actor, now))
        return self.get_job(jid)

    def get_job(self, job_id: str) -> Dict[str, Any]:
        self._ready()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM external_collection_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if not row:
            raise ExternalResearchError(f"존재하지 않는 수집 작업입니다: {job_id}")
        return self._decode(row)

    def list_jobs(self, profile_id: str = "") -> List[Dict[str, Any]]:
        self._ready()
        sql, args = "SELECT * FROM external_collection_jobs", ()
        if profile_id:
            sql, args = sql + " WHERE profile_id=?", (profile_id,)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY requested_at DESC", args).fetchall()
        return [self._decode(row) for row in rows]

    def _set_job(self, job_id: str, *, status: str, summary: Optional[Dict[str, Any]] = None,
                 error: str = "") -> Dict[str, Any]:
        if status not in JOB_STATUSES:
            raise ExternalResearchError(f"지원하지 않는 작업 상태입니다: {status}")
        now = _now()
        started = now if status == "RUNNING" else ""
        finished = now if status in ("CANDIDATE_READY", "ACCEPTED", "REJECTED",
                                     "FAILED", "CANCELLED") else ""
        self._ready()
        with self._lock, self._connect() as conn:
            current = conn.execute("SELECT status FROM external_collection_jobs WHERE job_id=?",
                                   (job_id,)).fetchone()
            if not current:
                raise ExternalResearchError(f"존재하지 않는 수집 작업입니다: {job_id}")
            if status == "RUNNING" and current["status"] != "SCHEDULED":
                raise ExternalResearchError(
                    f"예약 상태의 작업만 실행할 수 있습니다: {current['status']}")
            conn.execute(
                "UPDATE external_collection_jobs SET status=?,"
                "started_at=CASE WHEN ?<>'' THEN ? ELSE started_at END,"
                "finished_at=CASE WHEN ?<>'' THEN ? ELSE finished_at END,"
                "result_summary_json=?,error=? WHERE job_id=?",
                (status, started, started, finished, finished,
                 json.dumps(summary or {}, ensure_ascii=False), error, job_id))
        return self.get_job(job_id)

    def add_candidates(self, job_id: str, candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        job = self.get_job(job_id)
        now = _now()
        made: List[str] = []
        with self._lock, self._connect() as conn:
            for item in candidates:
                source_url = str(item.get("source_url") or "").strip()
                kind = str(item.get("candidate_kind") or "SOURCE_CANDIDATE").strip()
                material = {
                    "candidate_kind": kind,
                    "source_url": source_url,
                    "title": str(item.get("title") or "").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "evidence": item.get("evidence") or {},
                }
                content_hash = hashlib.sha256(json.dumps(
                    material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")).hexdigest()
                cid = f"erc_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT OR IGNORE INTO external_research_candidates(candidate_id,job_id,"
                    "profile_id,candidate_kind,source_url,title,summary,evidence_json,content_hash,"
                    "status,created_at) VALUES(?,?,?,?,?,?,?,?,?,'CANDIDATE_READY',?)",
                    (cid, job_id, job["profile_id"], kind, source_url, material["title"],
                     material["summary"], json.dumps(material["evidence"], ensure_ascii=False),
                     content_hash, now))
                row = conn.execute(
                    "SELECT candidate_id FROM external_research_candidates WHERE job_id=? AND "
                    "candidate_kind=? AND source_url=? AND content_hash=?",
                    (job_id, kind, source_url, content_hash)).fetchone()
                made.append(row["candidate_id"])
        return [self.get_candidate(cid) for cid in made]

    def get_candidate(self, candidate_id: str) -> Dict[str, Any]:
        self._ready()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM external_research_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if not row:
            raise ExternalResearchError(f"존재하지 않는 조사 후보입니다: {candidate_id}")
        out = dict(row)
        out["evidence"] = json.loads(out.pop("evidence_json"))
        return out

    def list_candidates(self, profile_id: str = "", status: str = "") -> List[Dict[str, Any]]:
        self._ready()
        where, args = [], []
        if profile_id:
            where.append("profile_id=?")
            args.append(profile_id)
        if status:
            where.append("status=?")
            args.append(status)
        sql = "SELECT * FROM external_research_candidates"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY created_at DESC", tuple(args)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            out.append(item)
        return out

    def review_candidate(self, candidate_id: str, decision: str, reviewed_by: str,
                         expected_content_hash: str) -> Dict[str, Any]:
        if decision not in ("ACCEPTED", "REJECTED"):
            raise ExternalResearchError("후보 결정은 ACCEPTED 또는 REJECTED여야 합니다.")
        actor = (reviewed_by or "").strip()
        if not actor:
            raise ExternalResearchError("후보 검토자는 필수입니다.")
        candidate = self.get_candidate(candidate_id)
        if candidate["status"] != "CANDIDATE_READY":
            raise ExternalResearchError("검토 대기 후보만 결정할 수 있습니다.")
        if candidate["content_hash"] != expected_content_hash:
            raise ExternalResearchError("검토한 후보와 현재 후보의 내용 지문이 다릅니다.")
        with self._lock, self._connect() as conn:
            changed = conn.execute(
                "UPDATE external_research_candidates SET status=?,reviewed_by=?,reviewed_at=? "
                "WHERE candidate_id=? AND status='CANDIDATE_READY' AND content_hash=?",
                (decision, actor, _now(), candidate_id, expected_content_hash)).rowcount
            if changed != 1:
                raise ExternalResearchError("후보 결정 직전에 상태나 내용 지문이 바뀌었습니다.")
        return self.get_candidate(candidate_id)


class ExternalResearchRunner:
    """승인 프로필을 읽어 후보만 만드는 결정론적 조사 실행기."""

    def __init__(self, store: ExternalResearchStore, fetcher=None):
        self.store = store
        self.fetcher = fetcher or _SafeHttpFetcher()

    @staticmethod
    def _as_document(value: Any, requested_url: str) -> FetchDocument:
        if isinstance(value, FetchDocument):
            return value
        if isinstance(value, str):
            return FetchDocument(requested_url, value)
        if isinstance(value, dict):
            return FetchDocument(str(value.get("url") or requested_url),
                                 str(value.get("body") or ""),
                                 str(value.get("content_type") or "text/html"),
                                 int(value.get("status") or 200))
        raise ExternalResearchError("수집기가 지원하지 않는 응답 형식을 반환했습니다.")

    @staticmethod
    def _html_candidates(doc: FetchDocument, domains: List[str]) -> List[Dict[str, Any]]:
        parser = _PageParser()
        parser.feed(doc.body)
        candidates: List[Dict[str, Any]] = [{
            "candidate_kind": "COMPANY_PAGE",
            "source_url": doc.url,
            "title": parser.title.strip(),
            "summary": parser.description[:500],
            "evidence": {"content_type": doc.content_type, "http_status": doc.status},
        }]
        seen = {doc.url}
        for href in parser.links:
            target = urljoin(doc.url, href)
            parsed = urlparse(target)
            if (parsed.scheme == "https" and parsed.hostname
                    and _host_allowed(parsed.hostname, domains) and target not in seen):
                seen.add(target)
                candidates.append({
                    "candidate_kind": "SOURCE_CANDIDATE",
                    "source_url": target,
                    "title": "공식 사이트에서 발견한 링크",
                    "summary": "자동 등록되지 않은 원천 후보입니다.",
                    "evidence": {"discovered_from": doc.url},
                })
            if len(candidates) >= 21:
                break
        return candidates

    @staticmethod
    def _rss_candidates(doc: FetchDocument, domains: List[str]) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(doc.body)
        except ET.ParseError as exc:
            raise ExternalResearchError(f"RSS/XML 문서를 해석할 수 없습니다: {exc}") from exc
        out: List[Dict[str, Any]] = []
        for item in root.findall(".//item") + root.findall(".//{*}entry"):
            title_node = item.find("title") or item.find("{*}title")
            link_node = item.find("link") or item.find("{*}link")
            link = ""
            if link_node is not None:
                link = (link_node.text or link_node.attrib.get("href") or "").strip()
            target = urljoin(doc.url, link)
            parsed = urlparse(target)
            if not parsed.hostname or not _host_allowed(parsed.hostname, domains):
                continue
            out.append({
                "candidate_kind": "EXTERNAL_EVENT",
                "source_url": target,
                "title": ((title_node.text if title_node is not None else "") or "").strip(),
                "summary": "RSS에서 발견한 사건 후보입니다. 수치 관측값으로 자동 전환하지 않습니다.",
                "evidence": {"feed_url": doc.url},
            })
            if len(out) >= 50:
                break
        return out

    def run(self, job_id: str) -> Dict[str, Any]:
        job = self.store.get_job(job_id)
        self.store._set_job(job_id, status="RUNNING")
        try:
            profile = self.store.get_profile(job["profile_id"])
            if profile["status"] != "APPROVED":
                raise ExternalResearchError("실행 시점에 회사 조사 프로필 승인이 유효하지 않습니다.")
            if profile["fingerprint"] != job["profile_fingerprint"]:
                raise ExternalResearchError("예약 시 봉인한 프로필과 현재 승인 프로필이 다릅니다.")
            if job["bot_kind"] != "COMPANY_BASE_RESEARCH":
                raise ExternalResearchError(
                    f"이 조사 봇의 수집 어댑터는 아직 구현되지 않았습니다: {job['bot_kind']}")
            candidates: List[Dict[str, Any]] = []
            for target in profile["official_urls"]:
                doc = self._as_document(self.fetcher(target, profile), target)
                if not _host_allowed(urlparse(doc.url).hostname or "", profile["official_domains"]):
                    raise ExternalResearchError("수집 응답이 승인 도메인 밖에서 왔습니다.")
                ctype = doc.content_type.lower()
                if "html" in ctype:
                    candidates.extend(self._html_candidates(doc, profile["official_domains"]))
                elif "rss" in ctype or "xml" in ctype:
                    candidates.extend(self._rss_candidates(doc, profile["official_domains"]))
                else:
                    raise ExternalResearchError(f"지원하지 않는 수집 문서 형식입니다: {doc.content_type}")
            current = self.store.get_profile(job["profile_id"])
            if current["status"] != "APPROVED" or current["fingerprint"] != job["profile_fingerprint"]:
                raise ExternalResearchError("수집 중 회사 조사 프로필의 승인 내용이 바뀌었습니다.")
            made = self.store.add_candidates(job_id, candidates)
            summary = {"candidate_count": len(made), "requested_url_count": len(profile["official_urls"]),
                       "dry_run": job["dry_run"]}
            return self.store._set_job(job_id, status="CANDIDATE_READY", summary=summary)
        except Exception as exc:
            self.store._set_job(job_id, status="FAILED", error=str(exc))
            if isinstance(exc, ExternalResearchError):
                raise
            raise ExternalResearchError(f"회사 조사 작업을 완료하지 못했습니다: {exc}") from exc


external_research = ExternalResearchStore()
external_research_runner = ExternalResearchRunner(external_research)
