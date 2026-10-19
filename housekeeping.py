"""output/ 정리 + 미업로드 영상 리마인드.

- tidy(): output/ 의 mp4 중 만든 지 1일(24시간) 이상 지났고 업로드 기록(작업기록 MD 의 '- URL:')이 없는 영상을
          작업기록 MD 와 함께 '미업로드/' 폴더로 옮긴다. main.py 가 실행될 때마다 자동으로 호출된다.
- reminder(): '미업로드/' 에 쌓인 영상을 나이순으로 알려준다 (실행이 끝날 때마다 출력).

    python housekeeping.py          # 지금 정리하고 목록 보기
"""
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "작업기록"
PENDING_DIR = ROOT / "미업로드"
STALE_DAYS = 1.0          # 이 기간이 지나면 미업로드 폴더로 이동
WARN_DAYS = 7.0           # 이 기간이 지난 영상은 결정(업로드/삭제)을 재촉


def _uploaded(md: Path) -> bool:
    try:
        return md.exists() and "- URL:" in md.read_text(encoding="utf-8")
    except OSError:
        return False


def _dest(path: Path) -> Path:
    dest = PENDING_DIR / path.name
    n = 2
    while dest.exists():
        dest = PENDING_DIR / f"{path.stem}-{n}{path.suffix}"
        n += 1
    return dest


def tidy(days: float = STALE_DAYS, quiet: bool = False) -> list[str]:
    """오래된 미업로드 영상을 옮기고 옮긴 파일 이름을 돌려준다."""
    moved: list[str] = []
    if not OUT_DIR.exists():
        return moved
    now = time.time()
    for mp4 in sorted(OUT_DIR.glob("*.mp4")):
        if (now - mp4.stat().st_mtime) / 86400 < days:
            continue
        md = LOG_DIR / f"{mp4.stem}.md"
        if _uploaded(md):
            continue
        PENDING_DIR.mkdir(exist_ok=True)
        try:
            shutil.move(str(mp4), str(_dest(mp4)))
            if md.exists():
                shutil.move(str(md), str(_dest(md)))
            meta = mp4.with_name(mp4.stem + ".meta.json")
            if meta.exists():
                shutil.move(str(meta), str(_dest(meta)))
            moved.append(mp4.name)
        except OSError as e:           # 파일이 열려 있는 등: 다음 실행 때 다시 시도
            print(f"  [정리] {mp4.name} 이동 실패(사용 중?): {e}")
    if moved and not quiet:
        print(f"[정리] 1일 이상 업로드하지 않은 영상 {len(moved)}개를 '미업로드' 폴더로 옮겼습니다:")
        for name in moved:
            print(f"  - {name}")
    return moved


def reminder() -> None:
    """미업로드 폴더에 영상이 있으면 목록과 나이를 출력한다."""
    if not PENDING_DIR.exists():
        return
    items = sorted(PENDING_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not items:
        return
    now = time.time()
    print("")
    print(f"[리마인드] 미업로드 영상이 {len(items)}개 있습니다 ({PENDING_DIR.name}/):")
    for p in items:
        age = (now - p.stat().st_mtime) / 86400
        flag = "  ← 업로드할지 삭제할지 정해주세요" if age >= WARN_DAYS else ""
        print(f"  - {p.name} ({age:.0f}일 전){flag}")


if __name__ == "__main__":
    tidy()
    reminder()
