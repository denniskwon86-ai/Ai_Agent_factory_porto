import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import datetime

class GitManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._init_if_needed()

    def _run_cmd(self, cmd: list) -> subprocess.CompletedProcess:
        """
        [Hotfix] Windows cp949 인코딩 충돌 방지를 위해 encoding="utf-8" 강제 적용
        """
        try:
            return subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                encoding="utf-8", # 🚨 Windows 환경 한글 깨짐 방지 핵심 조치
                check=False
            )
        except FileNotFoundError:
            print("🚨 [GitManager] 시스템에 'git'이 설치되어 있지 않거나 PATH에 없습니다.")
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Git not found")

    def _init_if_needed(self):
        """Git 저장소가 없으면 초기화"""
        git_dir = self.workspace_root / ".git"
        if not git_dir.exists():
            self._run_cmd(["git", "init"])
            self._run_cmd(["git", "config", "user.name", "AI Factory Agent"])
            self._run_cmd(["git", "config", "user.email", "agent@aifactory.local"])
            
            readme = self.workspace_root / "README.md"
            if not readme.exists():
                readme.write_text("# AI Factory Unified Workspace\n자동 생성된 워크스페이스입니다.", encoding="utf-8")
                
            self._run_cmd(["git", "add", "."])
            self._run_cmd(["git", "commit", "-m", "chore: Initialize unified workspace"])
            print("🌱 [GitManager] 통합 워크스페이스 Git 저장소 초기화 완료")

    def commit_sprint_changes(self, task_id: str, state: Dict[str, Any]) -> Optional[str]:
        """변경된 파일을 스테이징하고 ProjectState 정보를 바탕으로 커밋"""
        status = self._run_cmd(["git", "status", "--porcelain"])
        if not status.stdout.strip():
            print("ℹ️ [GitManager] 변경된 파일이 없어 커밋을 건너뜁니다.")
            return None

        self._run_cmd(["git", "add", "."])

        file_index = state.get("file_index", {})
        change_summaries = []
        for path, meta in file_index.items():
            if meta.get("last_modified_task") == task_id and meta.get("change_summary"):
                change_summaries.append(f"- {path}: {meta['change_summary']}")

        if change_summaries:
            body = "\n".join(change_summaries)
            summary_title = "워크스페이스 코드 병합 및 업데이트"
        else:
            body = "- 자동 병합된 코드 업데이트"
            summary_title = "코드 자동 병합 완료"

        commit_msg = f"feat({task_id}): {summary_title}\n\n[AI Factory Auto Commit]\n{body}"

        res = self._run_cmd(["git", "commit", "-m", commit_msg])
        if res.returncode == 0:
            log_res = self._run_cmd(["git", "rev-parse", "HEAD"])
            commit_hash = log_res.stdout.strip()
            print(f"📦 [GitManager] Git 커밋 완료 (Hash: {commit_hash[:7]})")
            return commit_hash
        else:
            print(f"⚠️ [GitManager] 커밋 실패: {res.stderr}")
            return None