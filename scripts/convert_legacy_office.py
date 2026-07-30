"""레거시 Office 문서(OLE2)를 최신 형식으로 변환한다 — 참고문서 등록부의 색인 병목 해소.

## 왜 필요한가 (2026-07-30 실측)

`docs/reference` 68건 중 **51건이 OLE2 레거시 바이너리**다. 확장자는 `.pptx`/`.docx` 인데 실제
내용은 PowerPoint 97-2003 형식이어서(`.ppt` 를 이름만 바꾼 파일) 추출이 전부 실패했다:

    추출 가능 16건 / 변환 필요 51건 (확장자 기준으로는 67건이 '가능'으로 보였다)

즉 **지식팩에 들어갈 수 있는 지식이 실제로는 1/4**이다. 그 병목이 이 스크립트가 푸는 문제다.

## 무엇을 하고 무엇을 하지 않는가

**한다**
  · 실제 시그니처로 레거시 파일을 식별한다(확장자를 믿지 않는다 — 그게 문제의 원인이었다)
  · 사용 가능한 변환기를 **자동 탐색**한다: LibreOffice(`soffice`) → Windows Office COM
  · 변환본을 **원본 옆에 새 파일로** 만든다
  · 변환 후 등록부를 재스캔해 `extraction_status` 가 실제로 바뀌었는지 보고한다

**하지 않는다**
  · **원본을 지우거나 덮어쓰지 않는다.** 원본은 증적이고, 변환은 손실이 있을 수 있다.
  · 변환기가 없을 때 "성공"이라고 말하지 않는다 — 파일 목록과 할 일을 정확히 출력한다.
  · 기본 실행은 **예행(dry-run)** 이다. `--apply` 를 줘야 실제로 변환한다.

## ⚠️ 백엔드 실측 결과 (2026-07-30) — **LibreOffice 를 쓰라**

이 저장소의 실제 파일 2건으로 Office COM 백엔드를 시험했고 **두 건 모두 멈췄다**(파일당
타임아웃으로 끊김). 다음을 순서대로 시도했는데 전부 같은 결과였다:

  ① `Unblock-File` (보호된 보기 해제)
  ② `AutomationSecurity=1` · `DisplayAlerts` 억제
  ③ 실제 형식에 맞는 확장자로 임시 사본을 만들어 열기(확장자 불일치 보안 프롬프트 회피)

즉 **비대화형 세션의 Office 자동화는 신뢰할 수 없다.** 게다가 멈춘 WINWORD/POWERPNT 프로세스가
남아 다음 실행의 COM 탐지까지 실패시킨다(그래서 `run()` 시작 시 잔여 임시 사본을 정리한다).

→ **권장 경로**: LibreOffice 설치 후 이 스크립트를 다시 돌린다(`soffice` 헤드리스는 대화상자가
  없다). 설치가 불가하면 현업이 각 파일을 열어 최신 형식으로 다시 저장해 올리는 것이 확실하다.
  COM 백엔드는 **최선 노력(best-effort)** 으로 남겨 두되 짧은 타임아웃으로 빨리 실패시킨다.

사용:
    python scripts/convert_legacy_office.py                  # 예행(무엇을 바꿀지만 출력)
    python scripts/convert_legacy_office.py --apply --limit 5
    python scripts/convert_legacy_office.py --apply --rescan  # 변환 후 등록부 재스캔
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: OLE2 복합 문서(레거시 Office) 시그니처.
OLE2_MAGIC = b"\xd0\xcf\x11\xe0"
#: 레거시 → 최신 확장자. 내용 기준으로 판정하되, 어느 앱으로 열지는 확장자 힌트를 참고한다.
_MODERN = {".ppt": ".pptx", ".pptx": ".pptx", ".doc": ".docx", ".docx": ".docx",
           ".xls": ".xlsx", ".xlsx": ".xlsx"}
_APP = {".pptx": "powerpoint", ".docx": "word", ".xlsx": "excel"}

#: LibreOffice 실행 파일 탐색 경로(Windows·macOS·Linux 표준 설치 위치).
_SOFFICE_CANDIDATES = (
    "soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice", "/usr/local/bin/soffice",
)


def is_ole2(path: Path) -> bool:
    """실제 내용이 레거시 OLE2 인가. **확장자를 믿지 않는다** — 그게 문제의 원인이었다."""
    try:
        with path.open("rb") as f:
            return f.read(4) == OLE2_MAGIC
    except OSError:
        return False


#: OLE2 안의 이 스트림 = **암호화된 OOXML**(MS 표준 암호화 · IRM/DRM). 변환 대상이 아니다.
_ENCRYPTED_MARKER = "EncryptedPackage".encode("utf-16-le")


def is_encrypted_ooxml(path: Path) -> bool:
    """암호/DRM 보호 문서인가 — **변환으로 풀리지 않는다.**

    ★★ [2026-07-30 실측] `docs/reference` 의 51건을 "레거시 Office"로 오진했다. 실제로는
      **50건이 암호화된 OOXML**(`EncryptedPackage`+`DataSpaces`)이고 1건은 보호가 걸린 `.ppt`
      였다. 그래서 모든 변환 시도가 실패했다:
        · LibreOffice → `Error: source file could not be loaded`
        · Office COM → 암호/DRM 프롬프트에서 무한 대기
      변환 목록에 넣는 것 자체가 잘못이다 — 실패가 확정된 작업으로 사람을 보낸다."""
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    return raw[:4] == OLE2_MAGIC and _ENCRYPTED_MARKER in raw


def encrypted_report(root: Path) -> Dict[str, Any]:
    """암호/DRM 보호 문서 목록 — **변환이 아니라 원본 재저장이 필요한 일감**이다."""
    items = [p for p in sorted(Path(root).rglob("*"))
             if p.is_file() and is_encrypted_ooxml(p)]
    return {
        "total": len(items),
        "files": [str(p.relative_to(root)) for p in items],
        "note": ("이 문서들은 **암호/DRM 으로 보호**되어 있어 자동 변환·추출이 불가능합니다"
                 "(변환기가 파일을 열지 못합니다). 문서 소유자 또는 DRM 권한자가 보호를 해제해 "
                 "다시 저장·업로드해야 합니다. 도구를 더 붙여서 해결되는 문제가 아닙니다."
                 if items else "암호/DRM 보호 문서가 없습니다."),
    }


def detect_backend() -> Tuple[Optional[str], str]:
    """쓸 수 있는 변환기를 찾는다. 없으면 `(None, "")` — **없는데 있다고 하지 않는다.**

    우선순위: LibreOffice(헤드리스·크로스플랫폼) → Windows Office COM(화면을 띄운다)."""
    for cand in _SOFFICE_CANDIDATES:
        found = shutil.which(cand) if os.sep not in cand else (cand if Path(cand).exists() else None)
        if found:
            return "soffice", found
    if sys.platform == "win32" and _office_com_available():
        return "office_com", ""
    return None, ""


def _office_com_available() -> bool:
    """PowerPoint COM 을 띄울 수 있는가(설치 여부 확인 — 곧바로 닫는다)."""
    ps = ("try { $a = New-Object -ComObject PowerPoint.Application -ErrorAction Stop; "
          "$a.Quit(); Write-Output 'OK' } catch { Write-Output 'NO' }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=90)
        return "OK" in (out.stdout or "")
    except Exception:
        return False


def plan(root: Path, registry_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """변환 대상 목록. 등록부가 있으면 그 판정을 쓰고, 없으면 디렉토리를 훑는다.

    ★ 등록부를 우선하는 이유: 같은 판정을 두 곳에서 하면 어긋난다(이 저장소의 관통 원칙)."""
    targets: List[Dict[str, Any]] = []
    files: List[Path] = []
    if registry_path and Path(registry_path).exists():
        try:
            from core.reference_registry import load_registry
            for a in load_registry(Path(registry_path)).get("assets", []):
                if a.get("extraction_status") == "CONVERSION_REQUIRED":
                    files.append(Path(root) / a["relative_path"])
        except Exception as e:
            print(f"⚠️ 등록부를 읽지 못해 디렉토리 스캔으로 대체합니다: {e}")
    if not files:
        files = [p for p in sorted(Path(root).rglob("*")) if p.is_file()]
    for p in files:
        if not p.exists() or not is_ole2(p):
            continue
        if is_encrypted_ooxml(p):
            # ★★ [2026-07-30 실측] 변환 대상이 **아니다.** 암호/DRM 보호 문서는 어떤 변환기로도
            #   열리지 않는다(LibreOffice: "source file could not be loaded" · Office COM: 프롬프트
            #   에서 무한 대기). 여기에 넣으면 사람을 실패가 확정된 작업으로 보낸다.
            continue
        modern = _MODERN.get(p.suffix.lower())
        if not modern:
            continue
        out = p.with_suffix("")
        out = out.parent / f"{out.name}_converted{modern}"
        targets.append({"source": p, "target": out, "app": _APP[modern],
                        "already": out.exists()})
    return targets


def convert_with_soffice(item: Dict[str, Any], soffice: str, timeout: float = 180) -> Path:
    """LibreOffice 헤드리스 변환.

    ⚠️⚠️ **[2026-07-30 실측으로 잡은 데이터 사고]** 처음에는 `--outdir` 를 원본 폴더로 주고
      `produced = src.parent / (src.stem + dst.suffix)` 를 결과로 삼았다. 그런데 원본이 이미
      최신 확장자(`.pptx` 인데 내용은 레거시)면 **그 경로가 원본과 같다.** soffice 는 원본을
      덮어쓰지 않으므로 `produced == src` 가 되고, 뒤이은 `produced.replace(dst)` 가
      **원본을 `_converted` 이름으로 옮겨 버렸다.** 실제 파일 50건이 그렇게 개명됐다
      (git 추적 파일이어서 전량 복원했다).

    그래서 두 가지를 바꿨다:
      ① 출력은 **격리된 임시 폴더**에 만든다 — 입력과 출력 경로가 겹칠 수 없게 구조로 막는다
      ② 결과가 **실제로 최신 형식인지 검증**한다(OOXML=zip). 이 검증이 있었다면 "변환 성공
         50건"이라는 거짓 보고가 즉시 잡혔다 — 결과를 확인하지 않는 변환은 변환이 아니다
      ③ soffice 에게도 **실제 형식에 맞는 이름**으로 준다(확장자가 내용과 다르면 오해한다)"""
    import tempfile

    src, dst = item["source"], item["target"]
    if dst.resolve() == src.resolve():
        raise RuntimeError("변환 대상 경로가 원본과 같습니다 — 원본을 덮어쓰지 않습니다.")
    fmt = dst.suffix.lstrip(".")
    with tempfile.TemporaryDirectory(prefix="soffice_") as work:
        # 입력 사본을 **임시 폴더 안에** 실제 형식 이름으로 둔다. 원본 폴더에 숨김 파일
        #   (`.name`)을 만들었더니 soffice 가 처리하지 못했다(rc=0 · 산출물 없음) — 실측.
        legacy = _LEGACY_EXT.get(src.suffix.lower(), src.suffix)
        feed = Path(work) / f"in{legacy}"
        shutil.copyfile(src, feed)
        outdir = str(Path(work) / "out")
        os.makedirs(outdir, exist_ok=True)
        # ★ 전용 프로필을 준다. LibreOffice 는 단일 인스턴스로 동작해서, 다른 soffice 가 떠 있으면
        #   두 번째 `--convert-to` 가 **조용히 아무 것도 하지 않는다**(rc=0 · 산출물 없음).
        #   배치 변환이 중간부터 실패하는 원인이 이것이다.
        profile = (Path(work) / "profile").as_uri()
        res = subprocess.run([soffice, f"-env:UserInstallation={profile}",
                              "--headless", "--norestore", "--convert-to", fmt,
                              "--outdir", outdir, str(feed)],
                             capture_output=True, text=True, timeout=timeout)
        produced = Path(outdir) / (feed.stem + dst.suffix)
        if not produced.exists():
            cand = [p for p in Path(outdir).iterdir() if p.suffix == dst.suffix]
            if not cand:
                raise RuntimeError(
                    f"변환 결과가 없습니다(soffice rc={res.returncode}): "
                    f"{(res.stderr or res.stdout or '').strip()[:200]}")
            produced = cand[0]
        _assert_modern(produced, dst.suffix)
        shutil.move(str(produced), str(dst))
    return dst


def _assert_modern(path: Path, suffix: str) -> None:
    """변환 결과가 정말 최신 형식인가. **결과를 확인하지 않는 변환은 변환이 아니다.**

    실측에서 soffice 가 `rc=0` 으로 성공을 보고했는데 산출물이 여전히 OLE2 였다(사실은 원본이
    그 자리에 있었다). 성공 코드만 믿으면 "변환 50건 완료"라는 거짓 보고가 그대로 나간다."""
    head = path.read_bytes()[:4]
    if head == OLE2_MAGIC:
        raise RuntimeError(
            "변환 결과가 여전히 레거시(OLE2)입니다 — 변환되지 않았습니다"
            "(soffice 가 원본을 그대로 돌려준 경우입니다).")
    want = _MAGIC_EXPECT.get(suffix.lower())
    if want and not head.startswith(want):
        raise RuntimeError(
            f"변환 결과의 형식이 기대와 다릅니다(머리 {head!r}, 기대 {want!r}).")


#: 최신 형식의 기대 시그니처(OOXML 은 zip).
_MAGIC_EXPECT = {".pptx": b"PK", ".docx": b"PK", ".xlsx": b"PK"}


#: COM 변환 파일당 제한(초). 짧게 두는 이유는 **빨리 실패하기 위해서**다 — 실측에서 300초
#: 제한으로 두 파일이 각각 끝까지 매달렸고, 51건이면 4시간을 기다린 뒤에야 원인을 알게 된다.
COM_TIMEOUT_SEC = 120

#: Office 자동화의 두 가지 정지 원인을 미리 없앤다.
#:  ① **보호된 보기** — 임시 폴더·다운로드 등 신뢰되지 않은 위치의 파일은 대화상자를 띄우고
#:     자동화는 그 앞에서 **무한정 멈춘다**(실측: 이 경로로 타임아웃했다).
#:  ② 변환 확인·복구 대화상자 — 레거시 형식을 열 때 뜬다.
_PS_PREAMBLE = """$ErrorActionPreference='Stop'
try { Unblock-File -LiteralPath "{src}" -ErrorAction SilentlyContinue } catch {}
"""


#: 최신 확장자 → 실제 내용(레거시)에 맞는 확장자.
_LEGACY_EXT = {".pptx": ".ppt", ".docx": ".doc", ".xlsx": ".xls"}


def _legacy_named_copy(src: Path) -> Optional[Path]:
    """실제 형식에 맞는 확장자로 임시 사본을 만든다.

    ★ [2026-07-30 실측] 이것이 Office 자동화가 멈춘 **진짜 원인**이었다. `.doc` 를 `.docx` 로
      이름만 바꾼 파일을 열면 Word 가 "파일 형식과 확장자가 일치하지 않습니다 — 계속 여시겠습니까?"
      **보안 프롬프트**를 띄운다. 이 대화상자는 `DisplayAlerts=0` 으로 꺼지지 않고
      (보안 경고는 알림이 아니다), 자동화는 그 앞에서 무한정 멈춘다.
      → 내용이 레거시임을 이미 시그니처로 알고 있으므로, 그 형식의 이름으로 사본을 만들어 연다.

    ⚠️ 사본이므로 원본은 이름도 내용도 그대로다."""
    legacy = _LEGACY_EXT.get(src.suffix.lower())
    if not legacy:
        return None
    tmp = src.parent / f".{src.stem}__legacy_tmp{legacy}"
    try:
        shutil.copyfile(src, tmp)
        return tmp
    except OSError:
        return None


def convert_with_office_com(item: Dict[str, Any], timeout: float = COM_TIMEOUT_SEC) -> Path:
    """Windows Office COM 변환(PowerPoint 32 = pptx, Word 16 = docx, Excel 51 = xlsx).

    ⚠️ 실제 앱을 띄운다. 파일마다 열고 저장하고 닫으므로 느리고 화면이 깜빡인다.
    ⚠️ 원본은 열기만 하고 저장하지 않는다 — 원본 손상 경로를 만들지 않는다.
    ⚠️ **보호된 보기가 걸린 위치의 파일은 자동화가 멈춘다.** 그래서 `Unblock-File` +
      `AutomationSecurity=1`(msoAutomationSecurityLow)로 미리 푼다. 그래도 멈추면
      타임아웃으로 끊고 실패로 보고한다 — 조용히 기다리지 않는다."""
    src, dst = item["source"], item["target"]
    app = item["app"]
    # 실제 형식에 맞는 이름의 사본으로 연다 — 확장자 불일치 보안 프롬프트가 자동화를 멈춘다.
    tmp = _legacy_named_copy(src)
    open_path = tmp or src
    try:
        return _com_open_and_save(app, open_path, dst, timeout)
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


def _com_open_and_save(app: str, src: Path, dst: Path, timeout: float) -> Path:
    pre = _PS_PREAMBLE.replace("{src}", str(src.resolve()))
    if app == "powerpoint":
        ps = pre + f'''$app = New-Object -ComObject PowerPoint.Application
try {{
  try {{ $app.AutomationSecurity = 1 }} catch {{}}
  try {{ $app.DisplayAlerts = 1 }} catch {{}}
  $pres = $app.Presentations.Open("{src.resolve()}", $true, $false, $false)
  $pres.SaveAs("{dst.resolve()}", 24)
  $pres.Close()
}} finally {{ $app.Quit() }}'''
    elif app == "word":
        ps = pre + f'''$app = New-Object -ComObject Word.Application
$app.Visible = $false
try {{
  try {{ $app.AutomationSecurity = 1 }} catch {{}}
  $app.DisplayAlerts = 0
  $doc = $app.Documents.Open("{src.resolve()}", $false, $true, $false)
  $doc.SaveAs2("{dst.resolve()}", 16)
  $doc.Close(0)
}} finally {{ $app.Quit(0) }}'''
    else:
        ps = pre + f'''$app = New-Object -ComObject Excel.Application
$app.Visible = $false; $app.DisplayAlerts = $false
try {{
  try {{ $app.AutomationSecurity = 1 }} catch {{}}
  $wb = $app.Workbooks.Open("{src.resolve()}", 0, $true)
  $wb.SaveAs("{dst.resolve()}", 51)
  $wb.Close($false)
}} finally {{ $app.Quit() }}'''
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True, timeout=timeout)
    if not dst.exists():
        raise RuntimeError(f"변환 결과가 없습니다(rc={res.returncode}): "
                           f"{(res.stderr or res.stdout or '').strip()[:300]}")
    return dst


def run(root: Path, registry_path: Optional[Path], apply: bool = False,
        limit: int = 0, rescan: bool = False,
        converter: Optional[Callable[[Dict[str, Any]], Path]] = None) -> Dict[str, Any]:
    """변환을 수행(또는 예행)하고 결과를 돌려준다. `converter` 는 테스트 주입용이다."""
    # 멈춘 Office 프로세스가 임시 사본을 붙잡고 있으면 unlink 가 실패해 잔여물이 남는다.
    #   다음 실행에서 정리한다 — 잔여물이 쌓이면 다음 스캔이 그것들까지 자산으로 센다.
    for stale in Path(root).rglob(".*__legacy_tmp.*"):
        try:
            stale.unlink()
        except OSError:
            pass
    targets = plan(Path(root), registry_path)
    pending = [t for t in targets if not t["already"]]
    if limit:
        pending = pending[:limit]

    backend, exe = (None, "")
    if converter is None:
        backend, exe = detect_backend()
        if apply and backend is None:
            # 변환기가 없으면 **성공이라고 말하지 않는다.** 할 일을 정확히 알려준다.
            return {
                "backend": None, "planned": len(targets), "converted": 0,
                "failed": 0, "skipped": len(targets), "items": [], "failed_items": [],
                "note": (f"변환기를 찾지 못했습니다(LibreOffice·Office 모두 없음). 대상 "
                         f"{len(targets)}건은 변환되지 않았습니다.\n"
                         f"  · LibreOffice 설치 후 다시 실행하거나,\n"
                         f"  · 현업이 각 파일을 열어 '다른 이름으로 저장 → 최신 형식'으로 "
                         f"저장해 올리십시오.\n"
                         f"  · 변환 대상 목록은 `--list` 로 파일에 저장할 수 있습니다."),
            }

    done, failed = [], []
    for t in pending:
        if not apply:
            done.append({"source": str(t["source"]), "target": str(t["target"])})
            continue
        try:
            if converter is not None:
                out = converter(t)
            elif backend == "soffice":
                out = convert_with_soffice(t, exe)
            else:
                out = convert_with_office_com(t)
            done.append({"source": str(t["source"]), "target": str(out),
                         "size": out.stat().st_size if Path(out).exists() else 0})
        except Exception as e:
            failed.append({"source": str(t["source"]), "reason": str(e)[:300]})

    out: Dict[str, Any] = {
        "backend": backend or ("injected" if converter else None),
        "planned": len(targets), "pending": len(pending),
        "converted": len(done), "failed": len(failed),
        "items": done, "failed_items": failed, "applied": bool(apply),
    }
    if apply and rescan and registry_path:
        try:
            from core.reference_registry import build_registry
            reg = build_registry(Path(root), Path(registry_path))
            out["registry_after"] = reg["summary"]
        except Exception as e:
            out["rescan_error"] = str(e)
    out["note"] = (("[예행] 실제로 변환하지 않았습니다. " if not apply else "")
                   + f"대상 {len(targets)}건 중 {len(done)}건 처리 · 실패 {len(failed)}건. "
                   + "원본은 지우거나 덮어쓰지 않았습니다(변환본은 `_converted` 접미사).")
    return out


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description="레거시 Office(OLE2) → 최신 형식 변환")
    ap.add_argument("--root", default="docs/reference")
    ap.add_argument("--registry", default="data/reference_registry.json")
    ap.add_argument("--apply", action="store_true", help="실제로 변환한다(기본은 예행)")
    ap.add_argument("--limit", type=int, default=0, help="이번 실행에서 처리할 건수")
    ap.add_argument("--rescan", action="store_true", help="변환 후 등록부 재스캔")
    ap.add_argument("--list", default="", help="변환 대상 목록을 이 파일에 저장")
    a = ap.parse_args(argv)

    backend, exe = detect_backend()
    print(f"변환기: {backend or '없음'}{f' ({exe})' if exe else ''}")
    res = run(Path(a.root), Path(a.registry), apply=a.apply, limit=a.limit, rescan=a.rescan)
    if a.list:
        Path(a.list).write_text(
            "\n".join(i["source"] for i in (res["items"] or [])) or "", encoding="utf-8")
        print(f"목록 저장: {a.list}")
    print(f"대상 {res['planned']}건 · 처리 {res['converted']}건 · 실패 {res['failed']}건")
    for f in res["failed_items"][:5]:
        print(f"  실패: {Path(f['source']).name} — {f['reason'][:90]}")
    if res.get("registry_after"):
        print(f"재스캔 후: {res['registry_after']}")
    print(res["note"])
    return 0 if not res["failed"] else 1


if __name__ == "__main__":     # pragma: no cover
    raise SystemExit(main())
