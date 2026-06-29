"""core/context_engine.py — 증분 codegen 전체파일 주입 검증.
소유 파일(full_file_exts)은 절단 없이 전체 주입되어 멀티태스크 기능 누락(회귀)을 막아야 한다.
full_file_exts 미지정 시에는 종전과 동일하게 per_file 절단되어야 한다(비개발자 단계 회귀 방지)."""
from state_models import ProjectState
from core.context_engine import ContextEngine

SENTINEL = "ZZZ_END_OF_FILE_SENTINEL_ZZZ"


def _make_state(tmp_path):
    # 4000자를 크게 초과하는 .tsx + 작은 .py 를 디스크에 쓰고 file_index 에 등록
    big_tsx = "// App\n" + ("const filler = 1;\n" * 400) + f"\n// {SENTINEL}\n"
    assert len(big_tsx) > 4000
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "App.tsx").write_text(big_tsx, encoding="utf-8")
    (tmp_path / "backend").mkdir(parents=True, exist_ok=True)
    (tmp_path / "backend" / "main.py").write_text("print('be')\n", encoding="utf-8")

    return ProjectState.model_validate({
        "project_name": "T",
        "workspace_root": str(tmp_path),
        "file_index": {
            "src/App.tsx": {"path": "src/App.tsx", "purpose": "메인 화면"},
            "backend/main.py": {"path": "backend/main.py", "purpose": "API 서버"},
        },
    })


def test_owned_file_injected_in_full(tmp_path):
    state = _make_state(tmp_path)
    ctx = ContextEngine.build_core_context(state, full_file_exts=(".tsx", ".ts"))
    # 소유 .tsx 는 전체 주입 → 끝부분 sentinel 이 살아 있고 절단 마커가 없어야 한다
    assert SENTINEL in ctx
    assert "전체 코드 보존 필수" in ctx
    # 비소유 .py 는 본문 없이 1줄 색인(참조)으로만
    assert "본 작업 비대상" in ctx
    assert "print('be')" not in ctx


def test_default_mode_truncates_large_file(tmp_path):
    # full_file_exts 미지정 → 종전대로 per_file(4000) 절단 (sentinel 소실, 절단 마커 존재)
    state = _make_state(tmp_path)
    ctx = ContextEngine.build_core_context(state)
    assert SENTINEL not in ctx
    assert "자 생략" in ctx  # _clip 절단 마커


def test_light_mode_skips_files(tmp_path):
    state = _make_state(tmp_path)
    ctx = ContextEngine.build_core_context(state, light=True, full_file_exts=(".tsx",))
    # light=True 면 파일 주입 자체를 생략
    assert SENTINEL not in ctx
    assert "워크스페이스 실제 파일" not in ctx


def test_disk_walk_recovers_owned_file_missing_from_index(tmp_path):
    # file_index 가 비어 있어도(유실/stale) 소유 확장자 파일은 디스크에서 직접 발견·주입돼야 한다
    big_tsx = "// App\n" + ("const filler = 1;\n" * 400) + f"\n// {SENTINEL}\n"
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "App.tsx").write_text(big_tsx, encoding="utf-8")
    state = ProjectState.model_validate({
        "project_name": "T",
        "workspace_root": str(tmp_path),
        "file_index": {},  # 인덱스 유실 상황
    })
    ctx = ContextEngine.build_core_context(state, full_file_exts=(".tsx", ".ts"))
    assert SENTINEL in ctx  # 인덱스에 없어도 디스크 walk 로 복구 주입
    assert "전체 코드 보존 필수" in ctx


def test_disk_walk_excludes_noise_dirs(tmp_path):
    # node_modules 등 제외 디렉터리의 owned 확장자는 주입하지 않는다
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "node_modules" / "pkg" / "index.tsx").write_text(f"// {SENTINEL}_NOISE\n", encoding="utf-8")
    state = ProjectState.model_validate({
        "project_name": "T", "workspace_root": str(tmp_path), "file_index": {},
    })
    ctx = ContextEngine.build_core_context(state, full_file_exts=(".tsx",))
    assert f"{SENTINEL}_NOISE" not in ctx
