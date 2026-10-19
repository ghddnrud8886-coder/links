"""상황 컷용 b-roll 라이브러리: assets/broll/<콘셉트 key>/ 의 mp4 를 관리한다.

    python broll.py --fetch            # 모든 콘셉트 클립을 Pixabay 에서 내려받는다 (이미 있으면 건너뜀)
    python broll.py --fetch --concept hobby --per-query 6
    python broll.py --sheet            # 콘셉트별 컨택트 시트(png)를 만들어 눈으로 검수한다

마음에 안 드는 클립은 폴더에서 지우면 된다. 직접 받은 mp4(Pexels/Mixkit 등)를 폴더에 넣어도 똑같이 쓰인다.
Pixabay 라이선스: 상업적 이용 가능, 출처 표기 불필요.
"""
import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
BROLL_DIR = ROOT / "assets" / "broll"
MIN_DUR, MAX_DUR = 6, 40
MIN_WIDTH = 1280        # 정사각 카드에 cover 로 채워도 선명하도록 720p 이상


def fetch(concept: dict, per_query: int = 5) -> int:
    load_dotenv(ROOT / ".env")
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        sys.exit("[오류] .env 에 PIXABAY_API_KEY 가 없습니다.")
    dest = BROLL_DIR / concept["key"]
    dest.mkdir(parents=True, exist_ok=True)
    meta_path = dest / "_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    got = 0
    for q in concept.get("broll", []):
        r = requests.get("https://pixabay.com/api/videos/", timeout=30,
                         params={"key": key, "q": q, "per_page": 30, "safesearch": "true"})
        r.raise_for_status()
        taken = 0
        for h in r.json().get("hits", []):
            if taken >= per_query:
                break
            vid = h["videos"].get("medium") or h["videos"].get("small")
            if not vid or str(h["id"]) in meta or not (MIN_DUR <= h["duration"] <= MAX_DUR) or vid["width"] < MIN_WIDTH:
                continue
            path = dest / f"pixabay_{h['id']}.mp4"
            with requests.get(vid["url"], stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(1 << 16):
                        f.write(chunk)
            meta[str(h["id"])] = {"query": q, "tags": h["tags"], "duration": h["duration"], "page": h["pageURL"]}
            taken += 1
            got += 1
            print(f"  [{concept['key']}] {q}: {path.name} ({h['duration']}s) {h['tags'][:50]}")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return got


MIN_USE_DUR = 5.5       # 컷(문장 하나 + 크로스페이드)보다 짧은 클립은 중간에 멈추므로 쓰지 않는다
_dur_cache: dict[Path, float] = {}


def clip_duration(p: Path) -> float:
    if p not in _dur_cache:
        from main import find_tool
        r = subprocess.run([find_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                           capture_output=True, text=True)
        try:
            _dur_cache[p] = float(r.stdout.strip())
        except ValueError:
            _dur_cache[p] = 0.0
    return _dur_cache[p]


def list_clips(key: str) -> list[Path]:
    """key 폴더(하위 폴더 포함)의 사용 가능한 클립. 너무 짧은 클립은 제외."""
    d = BROLL_DIR / key
    if not d.exists():
        return []
    return [p for p in sorted(d.rglob("*.mp4")) if clip_duration(p) >= MIN_USE_DUR]


def pick(key: str, n: int, sub: str = "") -> list[Path]:
    """n개를 무작위로 고른다. 상품 유형(sub) 폴더의 클립을 먼저 쓰고, 모자라면 같은 콘셉트의 나머지 클립으로 채운다.
    클립이 없으면 빈 목록."""
    allc = list_clips(key)
    if not allc:
        return []
    mine = [c for c in allc if sub and c.parent.name == sub]
    rest = [c for c in allc if c not in mine]
    random.shuffle(mine)
    random.shuffle(rest)
    chosen = (mine + rest)[:n]
    while len(chosen) < n:
        chosen.append(chosen[len(chosen) % len(allc)])
    return chosen


def contact_sheet(key: str, ffmpeg: str):
    clips = list_clips(key)
    if not clips:
        return
    out_dir = ROOT / "output" / "broll_sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(clips), 30):
        chunk = clips[i:i + 30]
        inputs, filt = [], []
        for j, c in enumerate(chunk):
            inputs += ["-ss", f"{min(2.0, clip_duration(c) / 2):.2f}", "-i", str(c)]
            filt.append(f"[{j}:v]scale=256:144:force_original_aspect_ratio=decrease,pad=256:144:(ow-iw)/2:(oh-ih)/2[v{j}]")
        grid = "".join(f"[v{j}]" for j in range(len(chunk))) + f"xstack=inputs={len(chunk)}:layout=" + \
            "|".join(f"{(j % 5) * 256}_{(j // 5) * 144}" for j in range(len(chunk)))
        out = out_dir / f"{key}_{i // 30}.png"
        r = subprocess.run([ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filt) + ";" + grid + "[o]", "-map", "[o]",
                            "-frames:v", "1", str(out)], capture_output=True, text=True, errors="replace")
        if r.returncode:
            print("  [시트 실패]", r.stderr[-300:])
        print("  시트:", out, "→", ", ".join(f"{j}={c.name}" for j, c in enumerate(chunk)))


if __name__ == "__main__":
    from concepts import CONCEPTS
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--concept")
    ap.add_argument("--per-query", type=int, default=5)
    a = ap.parse_args()
    for c in CONCEPTS:
        if a.concept and c["key"] != a.concept:
            continue
        if a.fetch:
            print(f"[{c['key']}] {fetch(c, a.per_query)}개 신규")
        if a.sheet:
            from main import find_tool
            contact_sheet(c["key"], find_tool("ffmpeg"))
