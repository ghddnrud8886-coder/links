"""알리익스프레스 상품 페이지에서 소개 영상(MP4)과 고화질 사진을 내려받는다 (best-effort).

알리익스프레스는 봇 차단/동적 렌더링을 쓰므로 정적 HTML 요청만으로는 실패할 수 있다.
실패하면 Playwright 폴백(`pip install playwright && playwright install chromium`)을 시도한다.
"""
import re
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
IMG_RE = re.compile(r"https?:\\?/\\?/[\w.\-]*alicdn\.com\\?/kf\\?/[\w.\-]+?\.(?:jpg|jpeg|png)", re.I)
VID_RE = re.compile(r"https?:\\?/\\?/[^\"'\s\\]+?\.mp4[^\"'\s\\]*", re.I)


def _clean(u: str) -> str:
    return u.replace("\\/", "/").replace("\\", "")


def _base_image(u: str) -> str:
    # ..._640x640.jpg_.webp 같은 썸네일 접미사 제거 → 원본(고화질)
    return re.sub(r"_\d+x\d+[a-z0-9]*\.(jpg|jpeg|png)(_\.\w+)?$", r".\1", u, flags=re.I)


def extract_media_urls(html: str) -> tuple[list[str], list[str]]:
    imgs, seen = [], set()
    for m in IMG_RE.findall(html):
        u = _base_image(_clean(m))
        if u not in seen:
            seen.add(u)
            imgs.append(u)
    vids = list(dict.fromkeys(_clean(m) for m in VID_RE.findall(html)))
    return imgs, vids


def _fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}, timeout=30)
        html = r.text
        if r.ok and IMG_RE.search(html):
            return html
    except requests.RequestException:
        pass
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(user_agent=UA, locale="ko-KR")
            page.goto(url, wait_until="networkidle", timeout=60000)
            html = page.content()
            b.close()
            return html
    except Exception as e:
        raise RuntimeError(
            "상품 페이지를 가져오지 못했습니다(봇 차단 가능). Playwright 설치 후 재시도하거나 "
            f"사진/영상을 직접 sample_images/에 넣어주세요. ({e})")


def _download(url: str, dest: Path) -> bool:
    try:
        with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=60) as r:
            if not r.ok:
                return False
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        return dest.stat().st_size > 5000
    except requests.RequestException:
        return False


def download_product_media(url: str, out_dir: Path, max_images: int = 8) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    imgs, vids = extract_media_urls(_fetch_html(url))
    count = 0
    for i, v in enumerate(vids[:1]):
        if _download(v, out_dir / f"00_video{i}.mp4"):
            count += 1
    for i, u in enumerate(imgs[:max_images], 1):
        if _download(u, out_dir / f"{i:02d}_photo.jpg"):
            count += 1
    if count == 0:
        raise RuntimeError("다운로드된 파일이 없습니다. 직접 sample_images/에 넣어주세요.")
    return count


if __name__ == "__main__":
    import sys
    print(download_product_media(sys.argv[1], Path("sample_images/ali")), "files")
