"""알리익스프레스 Hot Products 수집기: 쇼츠 파이프라인에 '오늘 뜨는 상품 1개'를 공급한다.

우선순위
  1) Affiliate API  aliexpress.affiliate.hotproduct.query  (.env의 ALI_APP_KEY / ALI_APP_SECRET / ALI_TRACKING_ID)
  2) 오프라인 CSV   data/hot_products.csv  (portals.aliexpress.com → Hot Products 내보내기 파일)

반환 형식(dict): product_id, name, features, images[list[url]], price, original_price,
                 affiliate_link, volume, category, source

이미 영상으로 만든 상품은 data/trend_history.json에 기록되어 다음 실행에서 건너뛴다.
단독 실행: python ali_trend_collector.py 전자제품 --top 3
"""
import argparse
import csv
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from typing import Iterator

import requests

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CSV_PATH = DATA_DIR / "hot_products.csv"
HISTORY_PATH = DATA_DIR / "trend_history.json"

GATEWAY = "https://api-sg.aliexpress.com/sync"
METHOD = "aliexpress.affiliate.hotproduct.query"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# 1단계 카테고리 ID. 어필리에이트 포털/aliexpress.affiliate.category.get 으로 최신 값을 확인해 수정하세요.
CATEGORIES = {
    "전자제품": "44",      # Consumer Electronics
    "차량용품": "34",      # Automobiles & Motorcycles
    "생활꿀템": "15",      # Home & Garden
    "휴대폰": "509",       # Phones & Telecommunications
    "컴퓨터": "7",         # Computer & Office
    "뷰티": "66",          # Beauty & Health
    "공구": "1420",        # Tools
    "전체": "",
    "all": "",
}

# CSV 헤더 별칭(포털 내보내기 형식/언어별 차이를 흡수)
CSV_ALIASES = {
    "product_id": ["product id", "productid", "product_id", "상품 id", "상품id"],
    "name": ["product desc", "product title", "product name", "title", "상품명", "상품 설명"],
    "image": ["image url", "main image", "image", "product main image url", "이미지 url"],
    "images": ["image urls", "small image urls", "extra images"],
    "link": ["promotion url", "promotion link", "promo link", "affiliate link", "product url", "product detail url",
             "프로모션 링크", "제휴 링크", "상품 url"],
    "price": ["discount price", "sale price", "target sale price", "price", "할인가", "판매가"],
    "original_price": ["origin price", "original price", "target original price", "정가"],
    "volume": ["sales volume", "30days sales", "orders", "lastest volume", "last volume", "판매량", "주문수"],
    "discount": ["discount", "할인율"],
    "rate": ["evaluate rate", "positive feedback", "rating", "평점", "만족도"],
    "category": ["first level category name", "category", "카테고리"],
}


# ───────────────────────── 공통 유틸 ─────────────────────────
def hires(url: str) -> str:
    """..._640x640.jpg_.webp 같은 썸네일 접미사를 떼어 원본(고화질) URL로."""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    return re.sub(r"_\d+x\d+[a-z0-9]*\.(jpg|jpeg|png)(_\.\w+)?$", r".\1", url, flags=re.I)


def _read_history() -> dict:
    try:
        d = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"used": list(d.get("used", [])), "uploaded": list(d.get("uploaded", []))}


def _write_history(d: dict):
    DATA_DIR.mkdir(exist_ok=True)
    tmp = HISTORY_PATH.with_suffix(".tmp")        # 임시 파일에 쓰고 교체: 도중에 끊겨도 기록이 깨지지 않는다
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(HISTORY_PATH)


def _load_history() -> set[str]:
    """큐에서 제외할 ProductId: 제작/예약된 상품(used) + 업로드된 상품(uploaded)."""
    d = _read_history()
    return {str(x) for x in d["used"]} | {str(u.get("product_id", "")) for u in d["uploaded"]}


def mark_used(product_id: str):
    d = _read_history()
    d["used"] = sorted(set(map(str, d["used"])) | {str(product_id)})
    _write_history(d)


def release_used(product_id: str):
    """제작이 끝나기 전에 실패한 상품의 예약을 풀어준다 (이미 업로드된 상품은 풀지 않는다)."""
    d = _read_history()
    if str(product_id) in {str(u.get("product_id", "")) for u in d["uploaded"]}:
        return
    d["used"] = [x for x in d["used"] if str(x) != str(product_id)]
    _write_history(d)


def update_upload_privacy(video_id: str, privacy: str):
    d = _read_history()
    for u in d["uploaded"]:
        if u.get("video_id") == video_id:
            u["privacy"] = privacy
    _write_history(d)


def record_upload(product_id: str, name: str, video_id: str, url: str, privacy: str):
    """업로드 성공 직후 상품ID/상품명/영상ID/일시를 영구 기록한다 (used 에도 함께 넣는다)."""
    import datetime as _dt
    d = _read_history()
    d["used"] = sorted(set(map(str, d["used"])) | {str(product_id)})
    d["uploaded"].append({
        "product_id": str(product_id), "name": name, "video_id": video_id, "url": url, "privacy": privacy,
        "uploaded_at": _dt.datetime.now().isoformat(timespec="seconds"),
    })
    _write_history(d)


def _build_features(title: str, volume, price, discount, rate) -> str:
    """API/CSV에는 '소구점' 필드가 없으므로 수치 정보와 원문 상품명을 합쳐 대본 모델에 전달한다."""
    bits = [f"원문 상품명: {title}"]
    if volume:
        bits.append(f"최근 주문 {volume}건")
    if discount:
        bits.append(f"할인율 {discount}")
    if rate:
        bits.append(f"평점/만족도 {rate}")
    if price:
        bits.append(f"가격 {price}")
    return ", ".join(bits)


# ───────────────────────── 1순위: Affiliate API ─────────────────────────
def sign_params(params: dict, secret: str) -> str:
    """AliExpress Open Platform sha256 서명: 파라미터를 키 순 정렬해 key+value 이어붙인 뒤 HMAC-SHA256(secret)."""
    base = "".join(f"{k}{params[k]}" for k in sorted(params))
    return hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest().upper()


def api_configured() -> bool:
    return all(os.getenv(k, "").strip() for k in ("ALI_APP_KEY", "ALI_APP_SECRET", "ALI_TRACKING_ID"))


def parse_api_response(j: dict) -> list[dict]:
    if "error_response" in j:
        e = j["error_response"]
        raise RuntimeError(f"AliExpress API 오류: {e.get('code')} {e.get('msg')}")
    body = j.get("aliexpress_affiliate_hotproduct_query_response", {}).get("resp_result", {})
    if str(body.get("resp_code")) != "200":
        raise RuntimeError(f"AliExpress API 응답 코드 {body.get('resp_code')}: {body.get('resp_msg')}")
    items = body.get("result", {}).get("products", {}).get("product", [])
    out = []
    for p in items:
        imgs = [p.get("product_main_image_url", "")]
        imgs += (p.get("product_small_image_urls") or {}).get("string", [])
        imgs = list(dict.fromkeys(hires(u) for u in imgs if u))
        title = p.get("product_title", "").strip()
        price = p.get("target_sale_price") or p.get("app_sale_price") or ""
        out.append({
            "product_id": str(p.get("product_id", "")),
            "name": title,
            "features": _build_features(title, p.get("lastest_volume"), price, p.get("discount"),
                                        p.get("evaluate_rate")),
            "images": imgs,
            "price": f"{price} {p.get('target_sale_price_currency', '')}".strip(),
            "original_price": p.get("target_original_price", ""),
            "affiliate_link": p.get("promotion_link") or p.get("product_detail_url", ""),
            "volume": p.get("lastest_volume", ""),
            "category": p.get("first_level_category_name", ""),
            "source": "api",
        })
    return out


def query_api(category: str, page_no: int = 1, page_size: int = 20) -> list[dict]:
    cat_id = CATEGORIES.get(category, category if category.isdigit() else "")
    params = {
        "app_key": os.environ["ALI_APP_KEY"].strip(),
        "timestamp": str(int(time.time() * 1000)),
        "sign_method": "sha256",
        "method": METHOD,
        "tracking_id": os.environ["ALI_TRACKING_ID"].strip(),
        "page_no": str(page_no),
        "page_size": str(page_size),
        "sort": "LAST_VOLUME_DESC",                      # 주문량 상위순
        "target_currency": os.getenv("ALI_CURRENCY", "KRW"),
        "target_language": os.getenv("ALI_LANGUAGE", "KO"),
        "ship_to_country": os.getenv("ALI_SHIP_TO", "KR"),
        "fields": "commission_rate,sale_price,discount,lastest_volume,evaluate_rate",
    }
    if cat_id:
        params["category_ids"] = cat_id
    params["sign"] = sign_params(params, os.environ["ALI_APP_SECRET"].strip())
    r = requests.post(GATEWAY, data=params, headers={"User-Agent": UA}, timeout=(10, 30))
    r.raise_for_status()
    return parse_api_response(r.json())


# ───────────────────────── 2순위: 오프라인 CSV ─────────────────────────
def _read_csv_rows(path: Path) -> list[dict]:
    for enc in ("utf-8-sig", "cp949", "utf-16"):
        try:
            with open(path, newline="", encoding=enc) as f:
                return list(csv.DictReader(f))
        except (UnicodeError, csv.Error):
            continue
    raise RuntimeError(f"CSV 인코딩을 읽지 못했습니다: {path}")


def _pick(row_l: dict, key: str) -> str:
    for a in CSV_ALIASES[key]:
        v = row_l.get(a)
        if v and v.strip():
            return v.strip()
    return ""


def parse_csv(path: Path = CSV_PATH, category: str = "") -> list[dict]:
    out = []
    for row in _read_csv_rows(path):
        r = {(k or "").strip().lower(): v for k, v in row.items()}
        title = _pick(r, "name")
        if not title:
            continue
        cat = _pick(r, "category")
        if category and category not in ("전체", "all") and category.lower() not in cat.lower() \
                and not (CATEGORIES.get(category) and CATEGORIES[category] == cat):
            if cat:      # 카테고리 열이 있을 때만 필터링
                continue
        imgs = [_pick(r, "image")] + re.split(r"[;,|\s]+", _pick(r, "images"))
        imgs = list(dict.fromkeys(hires(u) for u in imgs if u.startswith(("http", "//"))))
        pid = _pick(r, "product_id") or hashlib.md5(title.encode()).hexdigest()[:12]
        price = _pick(r, "price")
        out.append({
            "product_id": pid,
            "name": title,
            "features": _build_features(title, _pick(r, "volume"), price, _pick(r, "discount"), _pick(r, "rate")),
            "images": imgs,
            "price": price,
            "original_price": _pick(r, "original_price"),
            "affiliate_link": _pick(r, "link"),
            "volume": _pick(r, "volume"),
            "category": cat,
            "source": "csv",
        })
    return out


# ───────────────────────── 진입점 ─────────────────────────
def iter_candidates(category: str = "전자제품", source: str = "auto") -> Iterator[dict]:
    """아직 쓰지 않은 상품을 순위 순으로 하나씩 내준다. API 실패 시 CSV로 내려간다."""
    used = _load_history()
    tried_api = False
    if source in ("auto", "api") and api_configured():
        tried_api = True
        try:
            for page in (1, 2):
                for p in query_api(category, page):
                    if p["product_id"] not in used and p["images"]:
                        yield p
        except (requests.RequestException, RuntimeError, ValueError) as e:
            print(f"  [경고] Affiliate API 조회 실패: {e}")
            if source == "api":
                return
    elif source == "api":
        print("  [안내] ALI_APP_KEY/ALI_APP_SECRET/ALI_TRACKING_ID가 .env에 없습니다.")
        return
    if source in ("auto", "csv"):
        if CSV_PATH.exists():
            if not tried_api:
                print(f"  [안내] API 키가 없어 {CSV_PATH.relative_to(ROOT)}를 사용합니다.")
            for p in parse_csv(CSV_PATH, category):
                if p["product_id"] not in used and p["images"]:
                    yield p
        elif not tried_api:
            print(f"  [안내] API 키도, {CSV_PATH.relative_to(ROOT)}도 없습니다. "
                  "portals.aliexpress.com → Hot Products에서 CSV를 내려받아 data/hot_products.csv로 저장하세요.")


def download_images(urls: list[str], dest: Path, limit: int = 6) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*"):
        old.unlink()
    saved = []
    for u in urls:
        if len(saved) >= limit:
            break
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=30)
            if r.ok and len(r.content) > 8000 and r.headers.get("content-type", "").startswith("image"):
                ext = ".png" if u.lower().endswith(".png") else ".jpg"
                p = dest / f"img_{len(saved) + 1:02d}{ext}"
                p.write_bytes(r.content)
                saved.append(p)
        except requests.RequestException:
            continue
    return saved


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("category", nargs="?", default="전자제품")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--source", default="auto", choices=["auto", "api", "csv"])
    a = ap.parse_args()
    for i, p in enumerate(iter_candidates(a.category, a.source)):
        if i >= a.top:
            break
        print(json.dumps({**p, "images": p["images"][:2]}, ensure_ascii=False, indent=1))
