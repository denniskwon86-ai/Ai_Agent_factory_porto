"""PDF 슬라이드 + 문장별 나레이션 + 자막 + BGM → mp4.

사용:
  python scripts/video/build_video2.py <narration.json> <out.mp4> [--work-dir DIR] [--audio-dir DIR] [--bgm auto|bgm.wav] [--no-sub]

- 슬라이드 사이는 검정 페이드가 아니라 크로스페이드(xfade)로 잇는다 → 뚝 끊기는 느낌 제거.
- 레이아웃: 16:10 슬라이드를 1574×984 로 위쪽에 두고, 하단 96px 는 자막 전용 영역(네이비).
  줌은 슬라이드 안에서만 걸리므로 자막 영역을 침범하지 않고, 자막이 문서 내용을 가리지 않는다.
- 나레이션은 세그먼트에 붙이지 않고 하나의 오디오 타임라인에 배치한다.
- 자막: 문장 타임코드(cues.json)에 맞춰 표시용 대본을 얹는다(PIL 렌더 → overlay).
- BGM: 나레이션을 사이드체인으로 삼아 자동으로 볼륨을 낮춘다(덕킹). `--bgm auto` 면 총 길이에 맞춰 합성.
- 중간 산출물(slides/subs/segments)은 --work-dir 아래에 만든다. 기본값은 대본 파일이 있는 폴더.
  대본을 docs/ 에 두었다면 --work-dir 로 output/ 쪽을 지정할 것.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import imageio_ffmpeg
import pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))   # 저장소 루트
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

W, H = 1920, 1080
SLIDE_W, SLIDE_H = 1574, 984               # 16:10, 하단 96px 를 자막 영역으로 남긴다
SLIDE_X = (W - SLIDE_W) // 2               # 173
BAND = "0A1E5A"                            # --brand-primary
FPS = 30
LEAD, TAIL, XF = 0.5, 0.7, 0.6             # 나레이션 앞 여유 · 뒤 여유 · 크로스페이드
SUB_FONT_SIZE = 34
SUB_LINE_H = 42
BGM_GAIN = 0.22                            # ≈ -13 dB (덕킹 전)
FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\NotoSansKR-VF.ttf", "Bold"),
    (r"C:\Windows\Fonts\malgunbd.ttf", None),
    (r"C:\Windows\Fonts\malgun.ttf", None),
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path, variation in FONT_CANDIDATES:
        if os.path.exists(path):
            f = ImageFont.truetype(path, size)
            if variation:
                try:
                    f.set_variation_by_name(variation)
                except Exception:
                    pass
            return f
    raise RuntimeError("한글 폰트를 찾지 못했다")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def media_seconds(path: str) -> float:
    r = subprocess.run([FFMPEG, "-i", path, "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def render_slide(pdf: str, page_no: int, out_png: str) -> None:
    """슬라이드만 1574×984 로 렌더한다(캔버스 합성은 ffmpeg pad 가 한다)."""
    doc = pymupdf.open(os.path.join(ROOT, pdf))
    page = doc[page_no - 1]
    zoom = SLIDE_W / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    slide = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if slide.size != (SLIDE_W, SLIDE_H):
        slide = slide.resize((SLIDE_W, SLIDE_H), Image.LANCZOS)
    slide.save(out_png, optimize=True)
    doc.close()


def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if font.getlength(cand) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines if len(lines) <= 2 else [lines[0], " ".join(lines[1:])]


def render_subtitle(text: str, out_png: str, font: ImageFont.FreeTypeFont) -> None:
    """자막 텍스트 + 좌측 LS Red 포인트 바만 그린다. 배경은 캔버스(네이비)가 담당."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    area_top = SLIDE_H
    d.rectangle([SLIDE_X, area_top + 14, SLIDE_X + 5, H - 14], fill=(250, 0, 45, 255))
    lines = wrap(text, font, SLIDE_W - 140)
    y = area_top + (H - area_top - SUB_LINE_H * len(lines)) // 2 + 2
    for ln in lines:
        tw = font.getlength(ln)
        d.text(((W - tw) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += SUB_LINE_H
    img.save(out_png)


def build_segment(png: str, dur: float, subs: list[tuple[str, float, float]], out_mp4: str) -> None:
    frames = int(round(dur * FPS))
    zoom_step = 0.04 / max(frames, 1)
    inputs = ["-i", png]
    chain = (f"[0:v]zoompan=z='min(zoom+{zoom_step:.6f},1.04)':d={frames}"
             f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={SLIDE_W}x{SLIDE_H}:fps={FPS},"
             f"pad={W}:{H}:{SLIDE_X}:0:color=0x{BAND}[v0]")
    prev = "v0"
    for i, (sub_png, s, e) in enumerate(subs, 1):
        inputs += ["-i", sub_png]
        chain += f";[{prev}][{i}:v]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'[v{i}]"
        prev = f"v{i}"
    chain += f";[{prev}]format=yuv420p[vout]"
    run([FFMPEG, "-y", "-loglevel", "error", *inputs, "-filter_complex", chain,
         "-map", "[vout]", "-t", f"{dur:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", out_mp4])


def arg(argv: list[str], name: str, default: str | None) -> str | None:
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv: list[str]) -> None:
    spec_path, out_path = argv[0], argv[1]
    work = os.path.abspath(arg(argv, "--work-dir", os.path.dirname(os.path.abspath(spec_path))))
    audio_dir = arg(argv, "--audio-dir", os.path.join(work, "audio"))
    bgm = arg(argv, "--bgm", None)
    use_sub = "--no-sub" not in argv
    items = json.load(open(spec_path, encoding="utf-8"))
    slides_dir, seg_dir, sub_dir = (os.path.join(work, d) for d in ("slides", "segments", "subs"))
    for d in (slides_dir, seg_dir, sub_dir, os.path.dirname(os.path.abspath(out_path))):
        os.makedirs(d, exist_ok=True)
    font = load_font(SUB_FONT_SIZE)

    # 1) 세그먼트(비디오만) — 각 슬라이드 길이 = LEAD + 나레이션 + TAIL
    durs, wavs = [], []
    for it in items:
        png = os.path.join(slides_dir, it["id"] + ".png")
        wav = os.path.join(audio_dir, it["id"] + ".wav")
        cues = json.load(open(os.path.join(audio_dir, it["id"] + ".cues.json"), encoding="utf-8"))
        render_slide(it["pdf"], it["page"], png)
        dur = LEAD + media_seconds(wav) + TAIL
        subs = []
        if use_sub:
            for i, c in enumerate(cues):
                sp = os.path.join(sub_dir, f"{it['id']}_{i:02d}.png")
                render_subtitle(c["text"], sp, font)
                end = cues[i + 1]["start"] if i + 1 < len(cues) else c["end"] + 0.35
                subs.append((sp, LEAD + c["start"], LEAD + end))
        build_segment(png, dur, subs, os.path.join(seg_dir, it["id"] + ".mp4"))
        durs.append(dur)
        wavs.append(wav)
        print(f"{it['id']:16s} p{it['page']:<3d} {dur:5.1f}s  sub={len(subs)}", flush=True)

    # 2) 크로스페이드로 연결 — 슬라이드 i 시작 시각 S_i = Σ dur_j(j<i) − i·XF
    n = len(items)
    starts = [sum(durs[:i]) - i * XF for i in range(n)]
    total = sum(durs) - (n - 1) * XF
    seg_inputs = []
    for it in items:
        seg_inputs += ["-i", os.path.join(seg_dir, it["id"] + ".mp4")]
    chain, prev, acc = "", "0:v", 0.0
    for i in range(1, n):
        acc += durs[i - 1] - XF
        chain += f"[{prev}][{i}:v]xfade=transition=fade:duration={XF}:offset={acc:.3f}[x{i}];"
        prev = f"x{i}"
    video_only = os.path.join(seg_dir, "_video_only.mp4")
    run([FFMPEG, "-y", "-loglevel", "error", *seg_inputs, "-filter_complex", chain.rstrip(";"),
         "-map", f"[{prev}]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", video_only])

    # 3) 오디오 타임라인 — 나레이션 배치 + BGM 덕킹
    if bgm == "auto":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from make_bgm import main as make_bgm  # noqa: E402
        bgm = os.path.join(seg_dir, "_bgm.wav")
        make_bgm(total + 0.05, bgm)          # 끝의 4초 페이드아웃이 정확히 마지막에 걸린다
    a_inputs, parts = [], ""
    for i, wav in enumerate(wavs):
        a_inputs += ["-i", wav]
        ms = int(round((starts[i] + LEAD) * 1000))
        parts += f"[{i}:a]adelay={ms}|{ms}[n{i}];"
    labels = "".join(f"[n{i}]" for i in range(n))
    # 사이드체인 입력이 먼저 끝나면 컴프레서 출력(BGM)도 함께 끊긴다 — 총 길이보다 넉넉히 패딩하고 -t 로 자른다.
    parts += f"{labels}amix=inputs={n}:normalize=0:dropout_transition=0,apad=pad_dur=3[narr];"
    if bgm:
        a_inputs += ["-i", bgm]
        parts += (f"[narr]asplit[narr_a][narr_sc];"
                  f"[{n}:a]volume={BGM_GAIN},atrim=0:{total:.3f},asetpts=PTS-STARTPTS[bg];"
                  f"[bg][narr_sc]sidechaincompress=threshold=0.02:ratio=6:attack=120:release=900:makeup=1[bgd];"
                  f"[narr_a][bgd]amix=inputs=2:normalize=0:duration=longest:dropout_transition=0[aout]")
    else:
        parts += "[narr]anull[aout]"
    mix = os.path.join(seg_dir, "_mix.wav")
    run([FFMPEG, "-y", "-loglevel", "error", *a_inputs, "-filter_complex", parts,
         "-map", "[aout]", "-t", f"{total:.3f}", "-ar", "48000", "-ac", "2", mix])

    # 4) 합치기
    run([FFMPEG, "-y", "-loglevel", "error", "-i", video_only, "-i", mix,
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", out_path])
    m, s = divmod(total, 60)
    print(f"DONE {out_path}  {int(m)}m {s:04.1f}s  {os.path.getsize(out_path)/1e6:.1f}MB  slides={n}")


if __name__ == "__main__":
    main(sys.argv[1:])
