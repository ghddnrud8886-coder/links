"""알리 어필리에이트 포털 'Hot Products' 내보내기 파일(xlsx/xls/csv) 파서.

data/ 안에서 hot_products.xlsx -> hot_products.xls(.xls 포함) -> hot_products.csv 순으로 찾고,
행 순서를 순위로 보아 상위 N위 상품을 dict로 돌려준다.

필요 패키지: openpyxl(.xlsx), xlrd(.xls). CSV는 표준 라이브러리만 사용.
단독 실행: python ali_csv_loader.py [순위]
"""
import csv
import json
import re
import sys
from pathlib import Path

import requests

from ali_trend_collector import UA, hires

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
FILE_PATTERNS = ["hot_products*.xls*", "hot_products*.csv"]

# 컬럼 별칭(소문자 비교)
COLS = {
    "id": ["productid", "product id"],
    "image": ["image url", "main image"],
    "name": ["product desc", "product title", "상품명"],
    "origin": ["origin price", "original price"],
    "price": ["discount price", "sale price"],
    "discount": ["discount"],
    "sales": ["sales180day", "sales volume"],
    "feedback": ["positive feedback"],
    "link": ["promotion url", "promotion link"],
    "video": ["video url"],
}


# 대중성 낮은 산업/공장/전문 부품류 제외, 생활 꿀템 키워드 우선
EXCLUDE = ["분쇄기", "그라인더", "기계", "공구", "수리", "부품", "모듈", "DIY", "산업", "실험", "의류", "신발"]
# 리필/교체 부품/소모품 단독 상품 (본체 완제품만 선정). 공백을 뺀 상품명으로 비교한다.
EXCLUDE += ["블레이드", "교체", "리필", "교환용", "소모품", "전용백", "면도날", "부속품", "바늘", "패치"]
# '헤드'(헤드폰/헤드셋)·'호환'(아이폰 호환 충전기)은 완제품에도 흔해서 단독으로는 쓰지 않고 부품성 표현으로 좁힌다
# 비닐/봉투/가방/케이블/필터류 소모품·부속품 (완제품만 선정)
EXCLUDE += ["가방", "포장가방", "진공백", "비닐", "롤", "봉투", "파우치", "케이블", "스트랩", "어댑터", "젠더", "보호대", "필터", "패치"]
# 컴퓨터/네트워크/보안 부품류 (비가전). 영문 약어는 단어 경계로만 매칭한다(예: RAM 이 program 에 걸리지 않게).
EXCLUDE += ["SSD", "NVMe", "RAM", "메모리", "CPU", "메인보드", "그래픽카드", "라우터", "CPE", "CCTV"]
EXCLUDE += ["액세서리", "휠모터"]       # 본체가 아닌 호환 액세서리/구동 부품
EXCLUDE += ["교체헤드", "면도기헤드", "칫솔헤드", "교체용헤드", "단독호환부품", "호환팁", "호환젠더"]


def is_excluded(name: str) -> bool:
    low = name.lower()
    nospace = low.replace(" ", "")
    for k in EXCLUDE:
        kk = k.lower().replace(" ", "")
        if kk.isascii() and kk.isalnum():        # 영문 약어: 원문에서 앞뒤가 영문자가 아닐 때만 (RAM 이 program 에 걸리지 않게)
            if re.search(rf"(?<![a-z]){re.escape(kk)}(?![a-z])", low):
                return True
        elif kk in nospace:
            return True
    return False


# 계절 필터: 지금 시즌에 수요가 없는 상품을 건너뛴다 (공백 뺀 상품명 비교). 월 단위라 날씨와 어긋날 수 있으니 필요하면 수정.
SUMMER_ITEMS = ["선풍기", "쿨링", "냉각", "에어컨", "얼음", "모기", "냉감", "아이스", "목팬", "미니팬", "데스크팬", "휴대용팬",
                "cooling", "neckfan", "coolingfan"]
WINTER_ITEMS = ["히터", "난방", "온열", "핫팩", "전기장판", "전기담요", "보온", "손난로", "열풍기", "난로", "heater", "warmer"]
SUMMER_MONTHS = {5, 6, 7, 8, 9}      # 이 달에만 여름 상품 허용
WINTER_MONTHS = {10, 11, 12, 1, 2, 3}  # 이 달에만 겨울 상품 허용


def is_off_season(name: str, month: int | None = None) -> bool:
    import datetime
    month = month or datetime.date.today().month
    nospace = name.lower().replace(" ", "")
    if month not in SUMMER_MONTHS and any(k in nospace for k in SUMMER_ITEMS):
        return True
    return month not in WINTER_MONTHS and any(k in nospace for k in WINTER_ITEMS)


def priority_hits(name: str) -> list[str]:
    """키워드로 콘셉트(camp/sport/hobby/desk/lazy)에 분류되면 [콘셉트 키], 아니면 []"""
    from concepts import classify
    c, matched = classify(name)
    return [c["key"]] if matched else []


def _price_num(price: str) -> int:
    return int(re.sub(r"[^0-9]", "", price) or 0)


def rank_candidates(products: list[dict], need_video: bool = True,
                    exclude_ids: set[str] | None = None, max_price: int = 0,
                    min_price: int = 0) -> list[tuple[int, dict]]:
    """(엑셀 순위, 상품) 목록. 제외 키워드 상품과(need_video면) 비디오 없는 상품을 빼고
    우선 키워드 포함 상품 -> 판매량(180일) 순으로 정렬한다."""
    out = [(i + 1, p) for i, p in enumerate(products)
           if not is_excluded(p["name"]) and not is_off_season(p["name"]) and (p["video"] or not need_video)
           and p["product_id"] not in (exclude_ids or set())
           and (not max_price or _price_num(p["price"]) <= max_price)
           and _price_num(p["price"]) >= min_price]
    out.sort(key=lambda t: (not priority_hits(t[1]["name"]), -int(float(t[1]["sales"] or 0)), t[0]))
    return out


def find_files() -> list[Path]:
    """data/ 안의 hot_products*.xls* / hot_products*.csv 를 모두 찾는다 (엑셀 임시파일 ~$ 제외)."""
    found = {p for pat in FILE_PATTERNS for p in DATA_DIR.glob(pat) if not p.name.startswith("~$")}
    return sorted(found, key=lambda p: p.name.lower())


def _rows(path: Path) -> list[dict]:
    suf = path.suffix.lower()
    if suf == ".xlsx":
        import openpyxl
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        it = ws.iter_rows(values_only=True)
        head = [str(h or "").strip() for h in next(it)]
        return [dict(zip(head, ["" if v is None else str(v) for v in r])) for r in it]
    if suf == ".xls":
        import xlrd
        sh = xlrd.open_workbook(path).sheet_by_index(0)
        head = [str(h).strip() for h in sh.row_values(0)]
        return [dict(zip(head, [str(v) for v in sh.row_values(r)])) for r in range(1, sh.nrows)]
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(path, newline="", encoding=enc) as f:
                return list(csv.DictReader(f))
        except UnicodeError:
            continue
    raise RuntimeError(f"CSV 인코딩을 읽지 못했습니다: {path}")


def _pick(row: dict, key: str) -> str:
    low = {k.strip().lower(): v for k, v in row.items()}
    for a in COLS[key]:
        if low.get(a, "").strip():
            return low[a].strip()
    return ""


def _won(s: str) -> str:
    """'KRW 44418' -> '44,418원'"""
    m = re.search(r"[\d.]+", s.replace(",", ""))
    return f"{int(float(m.group())):,}원" if m else s


def _parse(path: Path) -> list[dict]:
    out = []
    for r in _rows(path):
        name = _pick(r, "name")
        if not name:
            continue
        out.append({
            "product_id": _pick(r, "id").split(".")[0],
            "name": name,
            "price": _won(_pick(r, "price")),
            "original_price": _won(_pick(r, "origin")) if _pick(r, "origin") else "",
            "discount": _pick(r, "discount"),
            "sales": _pick(r, "sales").split(".")[0],
            "feedback": _pick(r, "feedback"),
            "image": hires(_pick(r, "image")),
            "affiliate_link": _pick(r, "link"),
            "video": _pick(r, "video"),
            "source": path.name,
        })
    return out


def load_products(path: Path | None = None, verbose: bool = False) -> list[dict]:
    """모든 hot_products 파일을 병합하고 ProductId 기준으로 중복을 제거한다 (먼저 나온 행 우선,
    먼저 나온 행에 비디오가 없고 뒤 파일에 있으면 비디오/링크를 보강)."""
    files = [path] if path else find_files()
    if not files:
        raise FileNotFoundError("data/ 에 hot_products*.xlsx / .xls / .csv 파일이 없습니다.")
    merged: dict[str, dict] = {}
    total = 0
    for f in files:
        rows = _parse(f)
        total += len(rows)
        if verbose:
            print(f"  [데이터] {f.name}: {len(rows)}개")
        for p in rows:
            key = p["product_id"] or p["name"]
            if key not in merged:
                merged[key] = p
            elif not merged[key]["video"] and p["video"]:
                merged[key]["video"] = p["video"]
    if verbose:
        print(f"  [데이터] 병합 {total}개 -> 중복 제거 후 {len(merged)}개")
    return list(merged.values())


def top_product(rank: int = 1, path: Path | None = None) -> dict:
    prods = load_products(path)
    if not 1 <= rank <= len(prods):
        raise IndexError(f"순위 {rank}위 상품이 없습니다 (총 {len(prods)}개)")
    return prods[rank - 1]


def product_features(p: dict) -> str:
    """DeepSeek 프롬프트에 넣을 상품 소구점. 가격/할인율은 CTR을 위해 대본에 쓰지 않으므로 넘기지 않는다."""
    bits = [f"원문 상품명: {p['name']}"]
    if p["sales"]:
        bits.append(f"최근 180일 판매 {p['sales']}건")
    if p["feedback"]:
        bits.append(f"긍정 평가 {p['feedback']}")
    return ", ".join(bits)


def _is_blocked(r) -> bool:
    """알리의 봇 차단(punish/captcha) 페이지인지"""
    return "_____tmd_____" in r.text or "punish" in r.url


def fetch_gallery(product_id: str, limit: int = 5, retries: int = 2) -> list[str]:
    """상품 상세 페이지의 imagePathList(슬라이드 이미지)를 읽어 고화질 URL 목록을 돌려준다.
    봇 차단 페이지가 오면 잠시 쉬었다가 다시 시도한다(짧은 시간에 많이 요청하면 차단된다)."""
    import time
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"https://ko.aliexpress.com/item/{product_id}.html",
                             headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}, timeout=30)
        except requests.RequestException as e:
            print(f"  [경고] 상세 페이지 요청 실패: {e}")
            return []
        if not _is_blocked(r):
            break
        print(f"  [경고] 알리 봇 차단 페이지 응답({attempt + 1}/{retries + 1}) - 잠시 대기 후 재시도")
        time.sleep(6 * (attempt + 1))
    else:
        return []
    m = re.search(r'"imagePathList":(\[[^\]]*\])', r.text)
    urls = json.loads(m.group(1)) if m else []
    return list(dict.fromkeys(hires(u) for u in urls))[:limit]


def photo_like(path: Path) -> bool:
    """실사 사진인지 추정: 사진은 명암이 부드럽게 이어지는 픽셀(인접 밝기차 2~20)이 많고,
    글자/도표 인포그래픽과 흰 배경 단독컷은 평평한 면 + 날카로운 윤곽이 대부분이다."""
    from PIL import Image, ImageFilter
    px = list(Image.open(path).convert("L").resize((256, 256)).getdata())
    soft = strong = n = 0
    for y in range(255):
        row = y * 256
        for x in range(255):
            n += 1
            g = abs(px[row + x] - px[row + x + 1])
            if 2 <= g <= 20:
                soft += 1
            elif g > 60:
                strong += 1
    # 흰 배경 위의 깨끗한 제품 단독 사진은 평평하고 윤곽선이 거의 없다 -> 슬라이드쇼에 쓸 수 있다(글자/도표는 윤곽선이 더 많다)
    clean_product = strong / n <= 0.012 and soft / n >= 0.03
    if soft / n < 0.40 and not clean_product:
        return False
    # 여러 사진을 격자로 붙인 콜라주는 화면 전체가 고르게 복잡하다 (단일 피사체 사진보다 윤곽 밀도가 높다)
    edge = Image.open(path).convert("L").resize((256, 256)).filter(ImageFilter.FIND_EDGES)
    return sum(1 for v in edge.getdata() if v > 25) / (256 * 256) <= 0.33


def _min_side(path: Path) -> int:
    from PIL import Image
    return min(Image.open(path).size)


def download_gallery(product: dict, dest_dir: Path, limit: int = 5, min_side: int = 500) -> list[Path]:
    """엑셀 대표 이미지를 첫 장으로, 상세 페이지 슬라이드 이미지를 뒤에 붙여 limit장까지 내려받는다."""
    urls = list(dict.fromkeys([product["image"]] + fetch_gallery(product["product_id"], limit + 2)))
    saved: list[Path] = []
    for u in urls:
        if len(saved) >= limit:
            break
        p = download_image(u, dest_dir / f"product_{len(saved)}")
        if not p:
            continue
        if min_side and _min_side(p) < min_side:
            print(f"  [이미지] 해상도 낮아 제외: {Path(u).name}")
            p.unlink()
            continue
        if not photo_like(p):  # 대표 이미지 포함, 도표/글자 위주 컷은 버린다 (홍보 문구가 박힌 대표 이미지가 많다)
            print(f"  [이미지] 도표/글자 위주라 제외: {Path(u).name}")
            p.unlink()
            continue
        saved.append(p)
    return saved




def fetch_video_url(product: dict) -> str:
    """시연 비디오 URL: 엑셀의 Video Url 열만 사용한다 (상세 페이지를 긁지 않는다)."""
    return product.get("video", "")


def download_video(product: dict, dest: Path, min_bytes: int = 200_000) -> Path | None:
    url = fetch_video_url(product)
    if not url:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=60) as r:
            if not r.ok:
                return None
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
    except requests.RequestException:
        return None
    if dest.stat().st_size < min_bytes:
        dest.unlink(missing_ok=True)
        return None
    return dest


BAD_LANDING = re.compile(r"login|passport|signin|punish|captcha|/error|x5secdata|not.?found|expired", re.I)


def check_affiliate_link(url: str, product_id: str = "", timeout: float = 5) -> tuple[bool, str]:
    """제휴 링크가 실제 알리 상품 페이지로 정상 연결되는지 검사한다 (HEAD 는 막히는 경우가 많아 GET 사용).
    통과 조건: 리다이렉트를 따라간 최종 응답이 2xx + 최종 URL 이 aliexpress 상품 페이지(/item/숫자)이고
    로그인/차단/오류 페이지가 아님 + 엑셀의 ProductId 와 일치. 반환: (통과 여부, 사유)."""
    if not url:
        return False, "링크 없음"
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"},
                         allow_redirects=True, timeout=timeout, stream=True)
        final, code = r.url, r.status_code
        r.close()
    except requests.Timeout:
        return False, f"타임아웃({timeout:g}초)"
    except requests.RequestException as e:
        return False, f"요청 실패({type(e).__name__})"
    if not 200 <= code < 300:
        return False, f"HTTP {code}"
    if "aliexpress" not in final.lower():
        return False, f"알리 도메인 아님: {final[:60]}"
    if BAD_LANDING.search(final):
        return False, f"로그인/오류 페이지: {final[:60]}"
    m = re.search(r"/item/(\d+)", final)
    if not m:
        return False, f"상품 페이지 아님: {final[:60]}"
    if product_id and m.group(1) != str(product_id):
        return False, f"다른 상품으로 연결({m.group(1)})"
    return True, f"OK {m.group(1)}"


def download_image(url: str, dest: Path) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    except requests.RequestException:
        return None
    if not (r.ok and r.headers.get("content-type", "").startswith("image")):
        return None
    out = dest.with_suffix(".png" if "png" in r.headers["content-type"] else ".jpg")
    out.write_bytes(r.content)
    return out


if __name__ == "__main__":
    load_products(verbose=True)
    rank = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(json.dumps(top_product(rank), ensure_ascii=False, indent=1))


# 관심 가는 품목 검색어(콘셉트별 인기 꿀템). API 조회용
API_KEYWORDS = ["캠핑 랜턴", "휴대용 선풍기", "미니 마사지건", "무선 청소기", "게이밍 마우스", "블루투스 키보드",
                "차량용 거치대", "스마트워치", "LED 무드등", "휴대용 믹서기", "목 마사지기", "미니 프로젝터"]


def load_products_api(keywords: list[str] | None = None, per_kw: int = 20, verbose: bool = False) -> list[dict]:
    """Affiliate API(product.query)로 키워드별 인기 상품을 모아 엑셀 로더와 같은 형태로 돌려준다."""
    from ali_trend_collector import query_api_keyword
    merged: dict[str, dict] = {}
    for kw in keywords or API_KEYWORDS:
        try:
            items = query_api_keyword(kw, per_kw)
        except Exception as e:           # 한 검색어가 실패해도 나머지는 계속
            print(f"  [경고] '{kw}' 조회 실패: {e}")
            continue
        if verbose:
            print(f"  [API] {kw}: {len(items)}개")
        for p in items:
            if p["product_id"] in merged:
                continue
            merged[p["product_id"]] = {
                "product_id": p["product_id"], "name": p["name"], "price": _won(str(p["price"])),
                "original_price": _won(str(p["original_price"])) if p["original_price"] else "",
                "discount": "", "sales": str(p["volume"] or 0), "feedback": "",
                "image": p["images"][0] if p["images"] else "", "affiliate_link": p["affiliate_link"],
                "video": p.get("video", ""), "source": "api", "images": p["images"],
            }
    return list(merged.values())
