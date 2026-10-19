"""uploaded_videos/*.json 으로 프로필용 링크 모음 페이지(docs/index.html)를 만든다.

업로드가 끝날 때마다 uploader.py 가 자동으로 호출하고, 직접 실행해도 된다:
    python linkpage.py

생성된 docs/ 폴더를 GitHub Pages 등에 올리고, 그 주소를 유튜브 프로필 링크에 한 번만 등록한다.
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIVE_DIR = ROOT / "uploaded_videos"
OUT_DIR = ROOT / "docs"
PAGE_TITLE = "마멋선생 꿀템 모음"
DISCLOSURE = "이 페이지는 제휴 마케팅 활동의 일환으로, 구매 시 일정 수수료를 지급받을 수 있습니다."


def load_items() -> list[dict]:
    items = []
    for p in sorted(ARCHIVE_DIR.glob("*.json"), reverse=True):   # 파일명이 타임스탬프로 시작 → 최신순
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if m.get("link"):
            items.append(m)
    live = public_ids([m.get("video_id", "") for m in items])
    return [m for m in items if live is None or m.get("video_id") in live]


def public_ids(ids: list[str]) -> set[str] | None:
    """유튜브에서 실제로 공개 중인 영상 ID 집합 (삭제/비공개 영상 제외). 조회 실패 시 None → 필터 생략."""
    ids = [i for i in ids if i]
    if not ids:
        return set()
    try:
        from uploader import get_service
        yt = get_service()
        live = set()
        for i in range(0, len(ids), 50):
            r = yt.videos().list(part="status", id=",".join(ids[i:i + 50])).execute()
            live |= {v["id"] for v in r.get("items", []) if v["status"]["privacyStatus"] == "public"}
        return live
    except Exception as e:
        print(f"  [경고] 공개 영상 확인 실패, 필터 없이 진행: {e}")
        return None


def render(items: list[dict]) -> str:
    cards = []
    for m in items:
        name = html.escape(m.get("headline") or m.get("product_name", "제품"))
        hook = html.escape(m.get("hook", ""))
        link = html.escape(m["link"], quote=True)
        video = html.escape(m.get("url", ""), quote=True)
        watch = f'<a class="sub" href="{video}">영상 보기</a>' if video else ""
        img = m.get("image") or (f"https://i.ytimg.com/vi/{m['video_id']}/hqdefault.jpg" if m.get("video_id") else "")
        if img.startswith("//"):
            img = "https:" + img
        pic = (f'<a href="{link}" rel="sponsored nofollow noopener" target="_blank">'
               f'<img src="{html.escape(img, quote=True)}" alt="{name}" loading="lazy"></a>') if img else ""
        cards.append(f'<div class="card">{pic}<p class="hook">{hook}</p>'
                     f'<a class="btn" href="{link}" rel="sponsored nofollow noopener" target="_blank">🛒 {name} 최저가 보기</a>{watch}</div>')
    body = "\n".join(cards) or "<p>준비 중입니다.</p>"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(PAGE_TITLE)}</title>
<style>
body{{margin:0;background:#111;color:#eee;font-family:system-ui,sans-serif}}
main{{max-width:480px;margin:0 auto;padding:24px 16px}}
h1{{font-size:1.3rem;text-align:center}}
.card{{background:#1c1c1c;border-radius:12px;padding:14px;margin:12px 0}}
.card img{{display:block;width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:8px;margin-bottom:10px}}
.hook{{margin:0 0 10px;font-size:.9rem;color:#bbb}}
.btn{{display:block;text-align:center;background:#ff4747;color:#fff;text-decoration:none;font-weight:700;padding:12px;border-radius:8px}}
.sub{{display:block;text-align:center;margin-top:8px;color:#8ab4f8;font-size:.85rem;text-decoration:none}}
.note{{font-size:.75rem;color:#888;text-align:center;margin-top:24px}}
</style></head>
<body><main>
<h1>{html.escape(PAGE_TITLE)}</h1>
{body}
<p class="note">{DISCLOSURE}</p>
</main></body></html>
"""


def build() -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    items = load_items()
    out = OUT_DIR / "index.html"
    out.write_text(render(items), encoding="utf-8")
    print(f"  링크 모음 페이지 갱신: {out.relative_to(ROOT)} ({len(items)}개)")
    return out


def publish() -> bool:
    """docs/ 변경분을 커밋하고 GitHub 로 푸시한다 (GitHub Pages 가 몇 분 안에 반영)."""
    import subprocess

    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)

    git("add", "docs")
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("  링크 모음 변경 없음")
        return False
    git("commit", "-m", "Update link page")
    r = git("push", "origin", "main")
    print("  링크 모음 푸시 완료" if r.returncode == 0 else f"  [경고] 푸시 실패: {r.stderr.strip()[:200]}")
    return r.returncode == 0


if __name__ == "__main__":
    build()
    publish()
