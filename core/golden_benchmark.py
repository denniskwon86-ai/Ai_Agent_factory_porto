"""골든 벤치마크 — 품질 회귀 방지 프레임워크.

방향 선언(AI_HANDOFF §2): "완주가 쌓이면 대표 시나리오 산출물을 사람+LLM 이중 채점해,
이후 모든 기능 투자를 '벤치마크 점수 상승'으로 판정한다."

본 모듈은 **채점·스코어카드·회귀비교 프레임워크**다. 시나리오 실행(완주)은 별도(쿼터 환경, A-1
관문). 완주 산출물(`projects/<id>/latest_state.json`)이 있으면 3개 축으로 채점한다:
  1. deterministic (LLM 0콜): 파이프라인 단계 산출물 존재 + criteria.DETERMINISTIC_CHECKS.
  2. llm_judge (쿼터, 선택): criteria.STAGE_RUBRICS 를 score_stage 로 채점(정성 품질).
  3. human: 사람이 입력한 점수(외부 판단 반영).

스코어카드를 저장하고, '골든'으로 승격한 기준 스코어카드와 비교해 점수 하락(회귀)을 리포트한다.
골든 데이터 자체는 A-1 최초 완주 후 승격으로 채운다(그 전엔 프레임워크만 동작).
"""
import os
import json
import subprocess
from datetime import datetime, timezone

from state_models import ProjectState
from criteria import DETERMINISTIC_CHECKS

# 대표 골든 시나리오 세트. project_id 는 카탈로그(docs/test_plan/01_scenario_catalog.md) 규칙.
# ⚠️ C-1/D-1 의 실제 project_id 는 최초 완주 시 생성된 폴더명으로 조정(카탈로그에 suffix 미명시).
GOLDEN_SCENARIOS = [
    {"id": "A-1", "project_id": "test_a1_unitconv", "title": "단위 변환기", "domain": "sw"},
    {"id": "C-1", "project_id": "test_c1_sales", "title": "판매 데이터 분석 리포트", "domain": "data"},
    {"id": "D-1", "project_id": "test_d1_cost", "title": "원가 분석", "domain": "manufacturing"},
]

# 완주 판정에 쓰는 파이프라인 단계 산출물(상태 필드). 존재 여부로 '구간 완주율'을 낸다.
_STAGE_ARTIFACT_FIELDS = {
    "rfp": "rfp_summary",
    "prd": "prd_summary",
    "ui": "ui_mockup_summary",
    "architecture": "architecture_summary",
    "tech_spec": "tech_spec_summary",
}
# LLM judge 축에서 채점할 단계(criteria.STAGE_RUBRICS 키). 산출물 없으면 자동 skip.
_JUDGE_STAGES = ["RFP", "PLANNING", "ARCHITECTURE", "TECH_SPEC", "CODE_REVIEW"]

# 축 가중치(축이 없으면 있는 축만으로 재정규화).
_AXIS_WEIGHTS = {"deterministic": 0.4, "llm_judge": 0.4, "human": 0.2}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


class GoldenBenchmark:
    def __init__(self, root: str = None, projects_dir: str = "projects"):
        root = root or os.path.join("data", "benchmark")
        self.root = root
        self.projects_dir = projects_dir
        self.scorecards_dir = os.path.join(root, "scorecards")
        self.golden_dir = os.path.join(root, "golden")
        self.human_dir = os.path.join(root, "human")
        for d in (self.scorecards_dir, self.golden_dir, self.human_dir):
            os.makedirs(d, exist_ok=True)

    # ── 시나리오/상태 ─────────────────────────────────────────────────
    def list_scenarios(self) -> list:
        return [dict(s) for s in GOLDEN_SCENARIOS]

    def _scenario(self, scenario_id: str) -> dict | None:
        return next((dict(s) for s in GOLDEN_SCENARIOS if s["id"] == scenario_id), None)

    def _load_state(self, project_id: str) -> ProjectState | None:
        path = os.path.join(self.projects_dir, project_id, "latest_state.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ProjectState.model_validate(data)
        except Exception as e:
            print(f"⚠️ [GoldenBenchmark] 상태 로드 실패({project_id}): {e}")
            return None

    # ── 축 1: deterministic (LLM 0콜) ─────────────────────────────────
    def score_deterministic(self, state: ProjectState) -> dict:
        checks: dict[str, bool] = {}
        # (a) 파이프라인 단계 산출물 존재 = 구간 완주
        for label, field in _STAGE_ARTIFACT_FIELDS.items():
            checks[f"stage_{label}"] = bool((getattr(state, field, "") or "").strip())
        # (b) 빌드 성공
        checks["build_success"] = getattr(state, "build_status", "") == "success"
        # (c) criteria 의 결정론 검사 전수 재사용
        for cid, fn in DETERMINISTIC_CHECKS.items():
            try:
                checks[f"crit_{cid}"] = bool(fn(state))
            except Exception:
                checks[f"crit_{cid}"] = False
        passed = sum(1 for v in checks.values() if v)
        score = passed / len(checks) if checks else 0.0
        return {"score": round(score, 3), "passed": passed, "total": len(checks), "checks": checks}

    # ── 축 2: llm_judge (쿼터 소비) ───────────────────────────────────
    async def score_llm_judge(self, state: ProjectState) -> dict:
        from nodes.utils.scoring import score_stage
        per_stage: dict[str, float | None] = {}
        for stage in _JUDGE_STAGES:
            try:
                r = await score_stage(state, stage)
                per_stage[stage] = r.get("score")
            except Exception as e:
                print(f"⚠️ [GoldenBenchmark] judge 실패({stage}): {e}")
                per_stage[stage] = None
        vals = [v for v in per_stage.values() if isinstance(v, (int, float))]
        score = round(sum(vals) / len(vals), 3) if vals else None
        return {"score": score, "per_stage": per_stage}

    # ── 축 3: human ───────────────────────────────────────────────────
    def _human_path(self, scenario_id: str) -> str:
        return os.path.join(self.human_dir, f"{scenario_id}.json")

    def get_human_score(self, scenario_id: str) -> dict | None:
        p = self._human_path(scenario_id)
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def set_human_score(self, scenario_id: str, score: float, notes: str = "") -> dict:
        if not self._scenario(scenario_id):
            raise ValueError(f"알 수 없는 시나리오: {scenario_id}")
        if not (isinstance(score, (int, float)) and 0.0 <= score <= 1.0):
            raise ValueError("human score 는 0.0~1.0 범위의 숫자여야 합니다.")
        rec = {"score": round(float(score), 3), "notes": notes or "", "updated_at": _now()}
        with open(self._human_path(scenario_id), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        return rec

    # ── 복합 점수 ─────────────────────────────────────────────────────
    @staticmethod
    def _composite(axes: dict) -> float | None:
        parts = []
        for name, w in _AXIS_WEIGHTS.items():
            ax = axes.get(name)
            s = ax.get("score") if isinstance(ax, dict) else None
            if isinstance(s, (int, float)):
                parts.append((w, s))
        if not parts:
            return None
        tw = sum(w for w, _ in parts)
        return round(sum(w * s for w, s in parts) / tw, 3) if tw else None

    # ── 평가 실행 → 스코어카드 ────────────────────────────────────────
    async def evaluate(self, scenario_id: str, use_llm_judge: bool = False) -> dict:
        sc = self._scenario(scenario_id)
        if not sc:
            raise ValueError(f"알 수 없는 시나리오: {scenario_id}")
        state = self._load_state(sc["project_id"])
        axes: dict = {}
        if state is None:
            axes["deterministic"] = {"score": None, "note": "산출물 없음(미완주) — A-1 완주 후 채점 가능"}
        else:
            axes["deterministic"] = self.score_deterministic(state)
            if use_llm_judge:
                axes["llm_judge"] = await self.score_llm_judge(state)
        human = self.get_human_score(scenario_id)
        if human:
            axes["human"] = human

        scorecard = {
            "scenario_id": scenario_id,
            "project_id": sc["project_id"],
            "title": sc["title"],
            "created_at": _now(),
            "git_commit": _git_commit(),
            "has_artifact": state is not None,
            "used_llm_judge": bool(use_llm_judge and state is not None),
            "axes": axes,
            "composite": self._composite(axes),
        }
        self._save_scorecard(scorecard)
        return scorecard

    def _save_scorecard(self, scorecard: dict):
        ts = scorecard["created_at"].replace(":", "").replace("-", "").replace(".", "")[:15]
        fn = f"{scorecard['scenario_id']}_{ts}.json"
        with open(os.path.join(self.scorecards_dir, fn), "w", encoding="utf-8") as f:
            json.dump(scorecard, f, ensure_ascii=False, indent=2)

    def latest_scorecard(self, scenario_id: str) -> dict | None:
        cards = sorted(f for f in os.listdir(self.scorecards_dir)
                       if f.startswith(f"{scenario_id}_") and f.endswith(".json"))
        if not cards:
            return None
        with open(os.path.join(self.scorecards_dir, cards[-1]), "r", encoding="utf-8") as f:
            return json.load(f)

    # ── 골든 승격 + 회귀 비교 ─────────────────────────────────────────
    def _golden_path(self, scenario_id: str) -> str:
        return os.path.join(self.golden_dir, f"{scenario_id}.json")

    def get_golden(self, scenario_id: str) -> dict | None:
        p = self._golden_path(scenario_id)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def promote_golden(self, scenario_id: str, scorecard: dict = None) -> dict:
        """스코어카드를 이 시나리오의 골든(기준)으로 고정한다. 미지정 시 최신 스코어카드 사용."""
        card = scorecard or self.latest_scorecard(scenario_id)
        if not card:
            raise ValueError("승격할 스코어카드가 없습니다. 먼저 evaluate 하세요.")
        card = dict(card, promoted_at=_now(), is_golden=True)
        with open(self._golden_path(scenario_id), "w", encoding="utf-8") as f:
            json.dump(card, f, ensure_ascii=False, indent=2)
        return card

    def compare(self, scenario_id: str, current: dict = None) -> dict:
        """골든 대비 현재(또는 최신) 스코어카드의 축별/복합 delta 와 회귀 여부를 리포트."""
        golden = self.get_golden(scenario_id)
        cur = current or self.latest_scorecard(scenario_id)
        if not golden:
            return {"scenario_id": scenario_id, "status": "no_golden",
                    "message": "골든 기준이 아직 없습니다(A-1 완주 후 promote_golden)."}
        if not cur:
            return {"scenario_id": scenario_id, "status": "no_current", "message": "현재 스코어카드가 없습니다."}

        def _s(card, axis):
            ax = card.get("axes", {}).get(axis)
            return ax.get("score") if isinstance(ax, dict) else None

        axis_deltas = {}
        for axis in ("deterministic", "llm_judge", "human"):
            g, c = _s(golden, axis), _s(cur, axis)
            if isinstance(g, (int, float)) and isinstance(c, (int, float)):
                axis_deltas[axis] = round(c - g, 3)
        gc, cc = golden.get("composite"), cur.get("composite")
        composite_delta = round(cc - gc, 3) if isinstance(gc, (int, float)) and isinstance(cc, (int, float)) else None
        regressions = [a for a, d in axis_deltas.items() if d < 0]
        if isinstance(composite_delta, (int, float)) and composite_delta < 0:
            regressions.append("composite")
        return {
            "scenario_id": scenario_id,
            "status": "regression" if regressions else "ok",
            "golden_commit": golden.get("git_commit"),
            "current_commit": cur.get("git_commit"),
            "axis_deltas": axis_deltas,
            "composite_delta": composite_delta,
            "regressions": regressions,
        }


golden_benchmark = GoldenBenchmark()
