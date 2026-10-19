"""YouTube Shorts 업로드 + 제휴 링크 댓글 등록 (YouTube Data API v3).

main.py가 렌더링 후 output/result_meta.json 을 남기면 이 모듈이 그 파일을 읽어
제목/설명/태그를 만들고 업로드한 뒤 제휴 링크 댓글을 등록한다.

═══ 최초 1회 설정 가이드 ═══
1. https://console.cloud.google.com 에서 프로젝트 생성
2. "API 및 서비스 > 라이브러리"에서 'YouTube Data API v3' 사용 설정
3. "OAuth 동의 화면" 구성 (외부, 테스트 모드) → '테스트 사용자'에 본인 구글 계정 추가
4. "사용자 인증 정보 > OAuth 클라이언트 ID" → 유형 '데스크톱 앱' 생성
5. JSON을 내려받아 이 폴더에 `client_secrets.json` 으로 저장 (`client_secret.json` 이름도 인식)
6. 첫 실행 시 브라우저가 열리고 로그인/허용하면 `token.json`이 저장되어 이후엔 자동 인증

═══ 알아둘 점 ═══
- 검수(audit)를 받지 않은 API 프로젝트로 올린 영상은 YouTube가 '비공개'로 강제 잠글 수 있습니다.
  이 경우 스튜디오에서 수동으로 공개 전환하거나 API 감사 신청을 하세요.
- 업로드 1건은 할당량 약 1,600단위(기본 일 10,000), 댓글 등록은 약 50단위입니다.
- YouTube Data API는 댓글 '고정(pin)' 메서드를 제공하지 않습니다. 이 모듈은 댓글을 자동 등록하고
  pin_comment() 자리에 고정 로직을 끼워 넣을 수 있게만 해 두었습니다. 지금은 스튜디오에서
  댓글 옆 ⋮ → '고정'을 한 번 눌러야 합니다.
- Shorts는 세로 영상 + 3분 이하 + 제목/설명에 #Shorts 가 있으면 Shorts로 분류됩니다.

사용 예:
    python uploader.py --video output/shorts_queue_test.mp4 --dry-run        # 인증 없이 메타데이터만 확인
    python uploader.py --video output/shorts_queue_test.mp4                   # 기본: 일부 공개(unlisted)
    python main.py --csv --upload                           # 렌더링 직후 업로드
"""
import datetime
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIENT_SECRETS = [ROOT / "client_secrets.json", ROOT / "client_secret.json",
                  ROOT / "client_secrets.json.json"]     # 윈도우 숨김 확장자 때문에 이중 확장자로 저장된 경우
TOKEN = ROOT / "token.json"
ARCHIVE_DIR = ROOT / "uploaded_videos"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # 댓글 작성
]
PLACEHOLDER = "(여기에 제휴 링크 입력)"
DEFAULT_TAGS_COMMON = ["쇼츠", "Shorts", "마멋선생", "쇼핑천재", "가성비"]
# 플랫폼별 태그/해시태그/대가성 문구는 manual_queue.py 에서 관리 (알리: 기본값)
from manual_queue import PLATFORM_TAGS
MAX_TITLE = 100
AD_TITLE_PLATFORMS = {"네이버"}          # 제목 앞에 [광고]를 붙이고 '유료 광고 포함' 표시를 거는 플랫폼
# 공개 범위 기본값. 비공개(private) 영상에는 YouTube가 댓글 작성을 막아(403) 제휴 링크 댓글이 달리지 않는다.
# 실전 배포 시 이 한 줄만 "public" 으로 바꾸면 대중에게 공개 업로드된다.
DEFAULT_PRIVACY = "unlisted"
# 댓글 등록이 확인되면 영상을 이 공개 범위로 자동 전환한다. 댓글이 실패하면 전환하지 않고 unlisted 로 둔다.
# 끄려면 None 으로 바꾸거나 실행 시 --no-publish 를 붙인다.
PUBLISH_AFTER_COMMENT = "public"


# ───────────────────────── 인증 ─────────────────────────
def get_service():
    """OAuth 2.0 (데스크톱 앱) 인증 후 YouTube API 클라이언트를 돌려준다. token.json 을 재사용/갱신한다."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secret = next((p for p in CLIENT_SECRETS if p.exists()), None)
            if not secret:
                raise FileNotFoundError(
                    f"{CLIENT_SECRETS[0].name} 이 없습니다. 이 파일 상단의 '최초 1회 설정 가이드'를 따라 "
                    "발급받아 프로젝트 폴더에 저장하세요.")
            creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


# ───────────────────────── 메타데이터 ─────────────────────────
def load_meta(meta_path: Path, text_path: Path | None = None) -> dict:
    """output/result_meta.json 을 읽는다. 없으면 result_text.txt 의 [섹션]에서 최소 정보를 복원한다."""
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    if text_path and text_path.exists():
        text = text_path.read_text(encoding="utf-8")
        sec = {m.group(1).strip(): m.group(2).strip()
               for m in re.finditer(r"\[([^\]\n]+)\]\n(.*?)(?=\n\[[^\]\n]+\]\n|\Z)", text, re.S)}
        script = [l for l in sec.get("대본", "").splitlines() if l.strip()]
        return {"hook": script[0] if script else sec.get("후킹 제목", ""), "title": sec.get("후킹 제목", ""),
                "headline": "", "keywords": [], "hashtags": re.findall(r"#\S+", sec.get("해시태그", "")),
                "pinned_comment": sec.get("고정 댓글", ""), "link": "", "product_name": ""}
    raise FileNotFoundError(f"{meta_path} 가 없습니다. 먼저 main.py 로 영상을 만드세요.")


def build_title(meta: dict) -> str:
    """제목 = 훅 1문장 (해시태그/키워드 조각 없이, 100자 이내). 해시태그는 설명란에만 둔다."""
    hook = (meta.get("title") or meta.get("hook", "")).strip()
    headline = (meta.get("headline") or "").strip()
    head = f"{headline} | {hook}" if headline and hook else (headline or hook)     # 검색에 걸리도록 상품 키워드를 앞에
    if meta.get("platform") in AD_TITLE_PLATFORMS:         # 네이버 쇼핑 커넥트: 제목 내 '광고' 표시 (유튜브 정책 + 브랜드 커넥트 가이드)
        head = f"[광고] {head}"
    return head if len(head) <= MAX_TITLE else f"{head[:MAX_TITLE - 1]}…"


def build_tags(meta: dict) -> list[str]:
    """업로드 태그: 상품 해시태그 + 키워드 + 기본 태그 (중복 제거, 전체 450자 이내)."""
    plat_tags = PLATFORM_TAGS.get(meta.get("platform", "알리"), PLATFORM_TAGS["알리"])[0]
    raw = [t.lstrip("#") for t in meta.get("hashtags", [])] + list(meta.get("keywords", [])) + [meta.get("concept_name", "")] + plat_tags + DEFAULT_TAGS_COMMON
    tags, total = [], 0
    for t in dict.fromkeys(x.strip() for x in raw if x.strip()):
        if total + len(t) + 1 > 450:
            break
        tags.append(t)
        total += len(t) + 1
    return tags


def build_description(meta: dict, link: str) -> str:
    plat = meta.get("platform", "알리")
    hashtags = [t for t in meta.get("hashtags", []) if t.lower() != "#shorts"][:3] + ["#Shorts"] + PLATFORM_TAGS.get(plat, PLATFORM_TAGS["알리"])[1]
    lines = [meta.get("hook", ""), meta.get("headline", "")]
    lines += ["", "👉 제품 링크는 채널 프로필의 링크에서 확인하세요.",
              "※ " + (meta.get("disclosure") or "이 게시물은 제휴 마케팅 활동의 일환으로, 구매 시 일정 수수료를 지급받을 수 있습니다."),
              *(["※ " + meta["notice"]] if meta.get("notice") else []),
              *["※ " + t for t in meta.get("extra_notes", [])],
              "", " ".join(dict.fromkeys(hashtags))]
    return "\n".join(l for i, l in enumerate(lines) if l or i >= 2).strip()


def build_comment(meta: dict, link: str) -> str:
    comment = meta.get("pinned_comment", "")
    return comment.replace(PLACEHOLDER, link) if link else comment


# ───────────────────────── 업로드 / 댓글 ─────────────────────────
def upload_video(youtube, video: Path, title: str, description: str, tags: list[str], privacy: str, paid_promo: bool = False) -> str:
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs
            "defaultLanguage": "ko",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    part = "snippet,status"
    if paid_promo:       # '유료 광고 포함' 뱃지 (영상 시작 시 표시). 지원하지 않는 경우 제목의 [광고] 표시만으로 진행한다
        body["paidProductPlacementDetails"] = {"hasPaidProductPlacement": True}
        part += ",paidProductPlacementDetails"
    for attempt in (1, 2):
        req = youtube.videos().insert(part=part, body=body, media_body=media)
        resp = None
        try:
            while resp is None:
                status, resp = req.next_chunk()
                if status:
                    print(f"  업로드 {int(status.progress() * 100)}%")
            if paid_promo and attempt == 1:
                print("  '유료 광고 포함' 뱃지 적용 요청 완료")
            return resp["id"]
        except Exception as e:
            if not (paid_promo and attempt == 1):
                raise
            print(f"  [경고] '유료 광고 포함' 뱃지 설정 실패({type(e).__name__}) → 제목의 [광고] 표시로만 진행합니다")
            body.pop("paidProductPlacementDetails", None)
            part = "snippet,status"
            media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)


def post_comment(youtube, video_id: str, text: str) -> str:
    """영상에 최상위 댓글을 등록하고 댓글 ID를 돌려준다."""
    resp = youtube.commentThreads().insert(
        part="snippet",
        body={"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}},
    ).execute()
    return resp["id"]


def pin_comment(youtube, video_id: str, comment_id: str) -> bool:
    """고정 댓글 처리 자리. YouTube Data API v3 에는 댓글 고정 메서드가 없어 현재는 항상 False 를 돌려준다.
    (브라우저 자동화 등으로 고정을 구현하게 되면 여기에 넣는다.)"""
    return False


def set_privacy(youtube, video_id: str, privacy: str) -> str:
    """videos.update 로 공개 범위를 바꾼다 (snippet 의 title/categoryId 는 필수라 그대로 다시 보낸다)."""
    cur = youtube.videos().list(part="snippet,status", id=video_id).execute()["items"][0]
    body = {"id": video_id,
            "snippet": {k: cur["snippet"][k] for k in ("title", "description", "categoryId")},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    return youtube.videos().update(part="snippet,status", body=body).execute()["status"]["privacyStatus"]


def register_affiliate_comment(youtube, video_id: str, text: str) -> str | None:
    """제휴 링크 댓글 등록 + 고정 시도. 실패해도 업로드는 유지한다."""
    try:
        cid = post_comment(youtube, video_id, text)
    except Exception as e:  # 업로드 직후 처리 중이면 댓글이 거부될 수 있음
        print(f"  [경고] 댓글 등록 실패: {e}")
        return None
    if pin_comment(youtube, video_id, cid):
        print("  제휴 링크 댓글 등록 + 고정 완료")
    else:
        print("  제휴 링크 댓글 등록 완료 (고정은 YouTube 스튜디오에서 ⋮ → '고정'으로 직접 눌러주세요)")
    return cid


def _safe_name(name: str, limit: int = 40) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")[:limit] or "video"


def archive_upload(video: Path, meta_path: Path, meta: dict, video_id: str, url: str, privacy: str) -> Path:
    """업로드가 끝난 mp4 와 메타 JSON 을 uploaded_videos/[타임스탬프]_[상품명].(mp4|json) 으로 이동한다."""
    ARCHIVE_DIR.mkdir(exist_ok=True)
    stamp = datetime.datetime.now()
    stem = f"{stamp:%Y%m%d_%H%M%S}_{_safe_name(meta.get('product_name') or meta.get('hook', 'video'))}"
    meta = {**meta, "video_id": video_id, "url": url, "privacy": privacy, "uploaded_at": stamp.isoformat(timespec="seconds")}
    (ARCHIVE_DIR / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    meta_path.unlink(missing_ok=True)
    dest = ARCHIVE_DIR / f"{stem}.mp4"
    shutil.move(str(video), str(dest))
    return dest


def upload_from_result(video: Path, result_txt: Path | None = None, privacy: str | None = None,
                       link: str | None = None, dry_run: bool = False, meta_path: Path | None = None,
                       publish: bool = True) -> str:
    """main.py 호환 진입점. meta_path 가 없으면 result_txt 와 같은 폴더의 result_meta.json 을 쓴다."""
    privacy = privacy or DEFAULT_PRIVACY
    video_meta = Path(video).with_name(Path(video).stem + ".meta.json")      # 영상별 정보가 있으면 그것을 우선 (다른 영상 정보로 올라가는 사고 방지)
    if meta_path is None and video_meta.exists():
        meta_path = video_meta
    meta_path = meta_path or (Path(result_txt).with_name("result_meta.json") if result_txt
                              else ROOT / "output" / "result_meta.json")
    if meta_path.name == "result_meta.json":
        print("  [주의] 영상별 정보 파일이 없어 '마지막으로 렌더링한 영상'의 정보(result_meta.json)를 사용합니다. 제목/링크가 맞는지 확인하세요.")
    meta = load_meta(meta_path, Path(result_txt) if result_txt else None)
    link = link or meta.get("link", "")
    title, description = build_title(meta), build_description(meta, link)
    tags, comment = build_tags(meta), build_comment(meta, link)

    if dry_run:
        print(f"[제목 {len(title)}자] {title}\n\n[설명]\n{description}\n\n[태그] {', '.join(tags)}\n\n[댓글]\n{comment}")
        return "(dry-run)"
    if not link or PLACEHOLDER in comment:
        raise SystemExit("[중단] 제휴 링크가 없습니다. --link \"https://...\" 로 지정하거나 result_meta.json 의 link 를 채우세요.")

    youtube = get_service()
    video_id = upload_video(youtube, video, title, description, tags, privacy, paid_promo=meta.get("platform") in AD_TITLE_PLATFORMS)
    print(f"  Video ID: {video_id}")
    url = f"https://youtu.be/{video_id}"

    # 업로드가 성공한 즉시 히스토리에 영구 기록 (댓글 단계에서 실패해도 같은 상품이 다시 뽑히지 않게)
    if meta.get("product_id"):
        from ali_trend_collector import record_upload
        record_upload(meta["product_id"], meta.get("product_name", ""), video_id, url, privacy)
        print("  히스토리 기록 완료 (data/trend_history.json)")

    cid = register_affiliate_comment(youtube, video_id, comment)
    if cid and publish and PUBLISH_AFTER_COMMENT and privacy != PUBLISH_AFTER_COMMENT:
        try:                                    # 댓글 등록이 확인된 경우에만 공개 전환
            privacy = set_privacy(youtube, video_id, PUBLISH_AFTER_COMMENT)
            print(f"  공개 범위 전환: {privacy}")
            if meta.get("product_id"):
                from ali_trend_collector import update_upload_privacy
                update_upload_privacy(video_id, privacy)
        except Exception as e:
            print(f"  [경고] 공개 전환 실패(일부 공개 유지): {e}")
    elif not cid:
        print(f"  [안내] 댓글 등록이 확인되지 않아 {privacy} 상태를 유지합니다.")
    log_md = Path(meta["log_md"]) if meta.get("log_md") else None
    if log_md and log_md.exists():           # 작업 기록 MD 의 업로드 결과를 채운다
        txt = log_md.read_text(encoding="utf-8").replace(
            "- (아직 업로드 전)",
            "\n".join([f"- 업로드: {datetime.datetime.now():%Y-%m-%d %H:%M}", f"- URL: {url}", f"- 공개 범위: {privacy}",
                       f"- 제목: {title}", f"- 댓글 등록: {'성공' if cid else '실패(미등록)'}"]))
        log_md.write_text(txt, encoding="utf-8")
    if cid:
        dest = archive_upload(video, meta_path, meta, video_id, url, privacy)
        print(f"  보관: {dest.relative_to(ROOT)}")
        try:
            import linkpage
            linkpage.build()
            linkpage.publish()
        except Exception as e:                  # 링크 페이지 실패가 업로드를 막지 않게
            print(f"  [경고] 링크 모음 페이지 갱신 실패: {e}")
    else:
        print(f"  [안내] 댓글이 등록되지 않아 영상은 {video} 에 그대로 둡니다.")
    return url


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="이미 만든 영상을 YouTube Shorts로 업로드")
    ap.add_argument("--video", default=str(ROOT / "output" / "shorts_remotion.mp4"))
    ap.add_argument("--meta", default=None, help="메타데이터 JSON (생략하면 <영상 이름>.meta.json, 없으면 output/result_meta.json)")
    ap.add_argument("--text", default=str(ROOT / "output" / "result_text.txt"))
    ap.add_argument("--privacy", default=None, choices=["private", "unlisted", "public"],
                    help=f"공개 범위 (기본 {DEFAULT_PRIVACY}, 코드 상단 DEFAULT_PRIVACY 로 변경)")
    ap.add_argument("--link", help="제휴 링크 (생략하면 result_meta.json 의 link)")
    ap.add_argument("--no-publish", action="store_true", help="댓글 등록 후에도 공개 전환하지 않고 업로드 때의 공개 범위 유지")
    ap.add_argument("--dry-run", action="store_true", help="인증/업로드 없이 제목·설명·태그·댓글만 출력")
    a = ap.parse_args()
    print(upload_from_result(Path(a.video), Path(a.text), a.privacy, a.link, a.dry_run, Path(a.meta) if a.meta else None, not a.no_publish))
