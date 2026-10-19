"""쇼츠 자동 생성기: DeepSeek 대본 + edge-tts 음성 + Remotion(React) 모션 그래픽 렌더링.

사용 예:
    python main.py --name "접이식 노트북 거치대" --features "알루미늄, 6단 높이조절, 800g 초경량"
    python main.py --offline            # API 키 없이 내장 샘플 대본으로 테스트
    python main.py --ali-url "https://ko.aliexpress.com/item/....html"   # 소재 자동 다운로드 후 렌더링
"""
import argparse
import atexit
import asyncio
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

import broll
from concepts import classify, classify_sub

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"
WORK_DIR = OUT_DIR / "work"
SAMPLE_DIR = ROOT / "sample_images"

W, H, FPS = 1080, 1920, 30
# 귀차니스트 마멋 보이스: 덤덤한 기본 피치, 늘어지지 않는 속도
VOICE = "ko-KR-InJoonNeural"
PITCH = "+0Hz"
RATE = "+15%"          # 안정적인 빠른 딕션
GAP = 0.18            # 문장 사이 무음 간격(초)
API_RETRIES = 3
MAX_TITLE = 20       # 상단 훅 제목 최대 글자 수(공백 포함)
# 4번(호기심) / 5번(CTA) 문장 풀: 실행마다 무작위로 하나씩 고른다
SALE_POOL = [
    "알리 행사 때만 잠깐 풀리는 가격인데 얼마인지는 링크로 직접 확인해봐.",
    "치킨 반 마리 값도 안 하는데 품절각이니까 링크 눌러서 확인해봐.",
    "내가 얼마에 샀는지는 프로필 링크에 남겨둘 테니까 가서 봐라.",
    "솔직히 가격 보면 안 사는 게 손해인 수준인데 직접 확인해봐.",
    "지금 알리 세일 들어가서 역대급 가격에 풀렸는데 얼마인지는 링크로 직접 확인해봐.",
]
CTA_POOL = [
    "품절되고 후회하지 말고 프로필 링크 눌러라.",
    "귀찮게 고민할 시간에 프로필 링크 누르고 편해져라.",
    "프로필 링크 남겨둘 테니까 인생 편하게 살 사람만 가봐.",
    "품절되기 전에 프로필 링크 누르고 귀찮음 끝내라.",
]
# 훅 컷에 쓸 마멋 영상 분위기(assets/broll/_mascot/<calm|intense>/): 일상 공감형은 차분한 컷, 활동·취미형은 강렬한 컷
MASCOT_TONE = {"lazy": "calm", "desk": "calm", "camp": "intense", "sport": "intense", "hobby": "intense"}
CTA_NEUTRAL = [
    "마음에 들면 프로필 링크에서 직접 확인해봐.",
    "써보고 싶으면 프로필 링크 남겨둘 테니까 한번 봐봐.",
    "궁금하면 프로필 링크에서 어떤지 직접 보고 가.",
    "품절되기 전에 프로필 링크에서 한번 둘러봐.",
]
SALE_LINE, LAST_LINE = SALE_POOL[0], CTA_POOL[0]     # main()에서 pick_lines()로 무작위 교체
CLICHE_RE = re.compile(r"버튼만 누르면|손 하나 안|하면 끝남")      # 천편일률 문장 패턴: 나오면 재생성
SPEC_RE = re.compile(r"\d+\s*(ml|mah|pa|w|cm|mm|kg|g|v|hz)\b|USB|LED|파스칼|밀리리터|밀리암페어|\d{3,}", re.I)   # 스펙 나열 금지
TRANSL_RE = re.compile(r"털이 (알아서|들어)|셋업|장치|기어 ?모드|순환기|솔루션|듀얼|스마트 ?제어")   # 중국어 직역/기계 번역투: 나오면 재생성
COLOR_RE = re.compile(r"(빨간|파란|노란|초록|검은|검정|하얀|흰|분홍|핑크|보라색|회색|주황|파랑|빨강)\s?(색|빛)?")   # 상품 이미지/영상마다 색이 달라 오인 위험: 색 언급 금지
HEALTH_RE = re.compile(r"치과|치료|예방|살균|염증|통증|질환|건강|의사|완치|효과가 (좋|입증)")   # 의학적 효능 주장 금지
PRICE_RE = re.compile(r"원대|\d\s*원|[만천]\s*원|\d\s*%|퍼센트|할인율|\d{5,}")   # 구체적 가격/할인율 언급 금지
OLD_MAN = re.compile(r"자네|라네|보게나|하게나|말이지|말이야|이 말이")   # 이전 노신사 말투: 나오면 재생성
DISCLOSURE = "이 게시물은 제휴 마케팅 활동의 일환으로, 구매 시 일정 수수료를 지급받을 수 있습니다."
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}
VIDEO_EXT = {".mp4", ".mov"}

ENV_TEMPLATE = "# DeepSeek API 키를 아래에 입력하세요 (https://platform.deepseek.com)\nDEEPSEEK_API_KEY=\n"


# ───────────────────────── 환경 ─────────────────────────
def ensure_env() -> str:
    env = ROOT / ".env"
    if not env.exists():
        env.write_text(ENV_TEMPLATE, encoding="utf-8")
        print(f"[안내] {env} 템플릿을 생성했습니다. DEEPSEEK_API_KEY를 입력하세요.")
    load_dotenv(env)
    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def find_tool(name: str) -> str:
    p = shutil.which(name)
    if p:
        return p
    local = os.environ.get("LOCALAPPDATA", "")
    pats = [
        f"{local}/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/{name}.exe",
        f"C:/ffmpeg/bin/{name}.exe",
        f"C:/Program Files/ffmpeg/bin/{name}.exe",
    ]
    for pat in pats:
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    sys.exit(f"[오류] {name}를 찾을 수 없습니다. `winget install Gyan.FFmpeg` 후 터미널을 다시 여세요.")


FFMPEG = FFPROBE = ""


def run(cmd: list, cwd: Path | None = None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"[FFmpeg 오류]\n{' '.join(map(str, cmd))}\n{r.stderr[-1500:]}")
    return r


def duration(path: Path) -> float:
    r = run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(r.stdout.strip())


def detect_font() -> tuple[Path, str]:
    """OS 기본 한글 굵은 폰트 (파일, ASS용 패밀리명)를 찾는다."""
    cands = [
        ("C:/Windows/Fonts/malgunbd.ttf", "Malgun Gothic"),
        ("C:/Windows/Fonts/malgun.ttf", "Malgun Gothic"),
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "Apple SD Gothic Neo"),
        ("/Library/Fonts/AppleGothic.ttf", "AppleGothic"),
        ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "NanumGothic"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "Noto Sans CJK KR"),
    ]
    for p, fam in cands:
        if Path(p).exists():
            return Path(p), fam
    sys.exit("[오류] 한글 폰트를 찾지 못했습니다. 나눔고딕 등을 설치하세요.")


# ───────────────────────── 1. 대본 ─────────────────────────
OFFLINE_SCRIPT = {
    "sentences": [
        "솔직히 보조배터리 챙기기 귀찮아서 맨날 방전된 채로 다니지?",
        "가방에 던져 넣기만 하면 충전선까지 붙어 있어서 바로 꽂아 쓰면 됨.",
        "손바닥보다 작아서 주머니에 넣어도 있는지도 모르게 가벼움.",
        "출퇴근길 지하철이나 카페에서 꺼내 쓰기에 딱 좋은 크기임.",
        "이 크기에 이 기능이 들어갔다는 건 직접 확인해봐야 믿길 거야.",
        LAST_LINE,
    ],
    "title": "충전기 챙기기 귀찮지?",
    "headline": "케이블 일체형 보조배터리",
    "keywords": ["가방에 던져", "바로 꽂아", "주머니"],
    "hashtags": ["#귀차니스트", "#꿀템", "#자취템", "#가성비", "#마멋선생"],
    "pinned_comment": "🔥 초특가 링크는 프로필(채널 링크)에서 확인하세요!",
}


def pick_lines():
    """CTA 문장을 풀에서 무작위로 고른다 (호기심 문장은 상품별로 생성)."""
    global LAST_LINE
    LAST_LINE = random.choice(CTA_POOL)


def is_fixed(x: str) -> bool:
    return any(x.replace(" ", "") == f.replace(" ", "") for f in CTA_POOL + CTA_NEUTRAL)


def generate_script(api_key: str, name: str, features: str, concept: dict | None = None) -> dict:
    from concepts import DEFAULT
    concept = concept or DEFAULT
    global LAST_LINE
    LAST_LINE = random.choice(CTA_POOL if concept["key"] == "lazy" else CTA_NEUTRAL)
    hook_examples = " / ".join(f'"{h}"' for h in concept["hooks"])
    prompt = f"""너는 쇼츠 채널 '마멋선생'의 대본 작가다. 마멋은 만사 귀찮아하는 프로 귀차니스트 마멋이고, 좋은 물건을 덤덤하고 찰지게 추천하는 찐친 같은 캐릭터다. 귀차니스트 설정은 말투의 결(덤덤하고 힘 뺀 어조)로만 깔고, 내용에서 억지로 "귀찮다"를 반복하지는 않는다.

[이번 영상 콘셉트: {concept["name"]}]
- 시청자 상황: {concept["situation"]}
- 훅 규칙: {concept["hook_rule"]}
- 훅은 이 상품을 모르는 사람이 읽어도 무슨 이야기인지 바로 이해되는 완결된 문장이어야 한다. 상품과 무관하거나 의미가 모호한 문장은 쓰지 않는다.
- 훅 예시는 말투 참고용일 뿐이다. 이 상품과 상황이 다르면 완전히 무시하고 이 상품의 실제 사용 장면에서 훅을 만든다(예시 문장이나 소재를 가져오지 말 것): {hook_examples}

[말투 규칙] 귀찮아서 대충 사는 찐친 말투
- 친구한테 카톡으로 툭 던지는 날것의 반말: ~잖아 ~지? ~인데 ~함 ~더라 ~갖다 버리려 했는데 (설명서/광고 말투 금지)
- 일상에서 킹받는 순간을 구체적으로 찌른다. 말투 참고(그대로 베끼지 말 것): "더워 죽겠는데 일어나기도 싫지" "선 치우는 것도 일인데" "바람 약하면 갖다 버리려 했는데 의외로 세더라"
- 같은 패턴 반복 금지: "버튼만 누르면" "손 하나 안 움직여도 됨" "~하면 끝남" 같은 천편일률 문장은 쓰지 않는다. 문장마다 어미와 흐름을 다르게 쓴다.
- 노인 말투 절대 금지: ~라네 ~보게나 ~하게나 ~말이지 ~말이야 자네
- 인사말 절대 금지.
- 쉼표(,)를 대본 전체에서 절대 쓰지 않는다. TTS가 중간에 멈칫하지 않도록 문장 하나를 한 호흡으로 쭉 이어서 쓴다.
- 스펙 나열 절대 금지. 용량(ml) 전원 방식(USB) 흡입력(Pa) 와트 같은 수치와 부품 이름을 읊지 않는다. 직관적인 체감과 상황 묘사만 쓴다.

[상식성 규칙 - 훅(1번 문장)과 전체 내용]
- 상식적으로 실제로 일어나는 일상적인 불편함만 다룬다. 사람들이 진짜 겪는 상황이어야 한다.
- 아침마다 부품을 매일 교체한다거나 소모품을 하루에도 몇 번씩 갈아 끼운다는 식의 상식 밖 억지 상황을 지어내서 귀차니즘을 유도하지 않는다.
- 상품의 핵심 기능(본연의 가치)에서 오는 진짜 편리함을 중심으로 찐친 톤 대본을 구성한다. 상품명이 부품/소모품처럼 보여도 그 상품이 쓰이는 본체의 일상적 효용만 말하고 어색한 상황을 만들지 않는다.
- 상품명과 특징에 없는 기능이나 효과를 지어내지 않는다.
- 매일 부품을 바꾼다거나 일상에서 일어나지 않는 가상의 비상식적 불편함을 지어내지 않는다.
- 상품 본연의 핵심 기능 하나만 짚어서 찐친 말투로 짧고 담백하게 쓴다. 기능을 여러 개 늘어놓지 않는다.
- 하나의 간편한 사용법으로만 통일한다. 문장끼리 모순되면 안 된다. (예: 한 문장에서 "물 묻히고 쓱 밀면"이라 해놓고 다른 문장에서 "물 없이 그냥 밀면"이라 쓰는 식 금지)
- 훅(1번)은 사람들이 실제로 매일 겪는 진짜 불편함이어야 한다. 억지 행동 묘사 금지.
  나쁜 예: "면도기 들고 서서 턱 만지작거리는 거 귀찮지?" (아무도 그렇게 안 한다)
  좋은 예: "피곤한 아침에 조심조심 수염 깎기 귀찮지?" / "아침마다 면도날에 베이는 사람?"
- title(상단 문구)과 headline(3초 뒤 문구)도 번역투/한자어투 없이 친구가 말하듯 자연스럽게 쓴다.
  조사(이/가/은/는/을/를/에서/하기)를 빼먹은 전보체나 단어 나열은 절대 금지. 소리 내어 읽었을 때 완전한 한국어 문장이어야 한다.
  나쁜 예: "아침 면도 거울 앞이 귀찮냐?" "면도 셋업 귀찮은 사람?" / 좋은 예: "아침마다 면도하기 귀찮은 사람?" "출근 전에 수염 깎는 거 귀찮지?"
  나쁜 예: "아침 면도 셋업 귀찮은 사람?" "효율적인 휴대용 수염 정리 솔루션"
  좋은 예: "아침마다 면도날 베이는 사람?" "물세척 되는 미니 면도기"

[번역투 금지 - 알리 상세페이지 스펙은 중국어를 기계 번역한 문장이라 그대로 따라 쓰면 어색해진다]
- 중국식 직역/기계 번역 표현 전면 금지: "털이 알아서 들어가" "털이 들어간다" "기어 모드" "순환기" "셋업" "장치" "솔루션" "듀얼" "스마트 제어" 같은 말.
- 상품명/특징의 용어를 그대로 옮기지 말고, 친구한테 말할 때 쓰는 평소 단어로 풀어 쓴다. (예: 기어 모드 -> 세기 조절, 순환기 -> 선풍기, 장치 -> 빼기)
- 한국어로 소리 내어 읽었을 때 자연스러운지 스스로 점검한다. 어색하면 더 쉬운 말로 바꾼다.

[글자 수 규칙 - 가장 자주 틀리는 부분]
- 아래 [구조]에 적힌 문장별 글자 수 범위(공백 포함)를 엄격히 지켜라. 문장을 쓴 뒤 글자 수를 직접 세어보고 범위를 넘으면 줄여서 다시 써라.
- 범위 초과가 가장 흔한 실패다. 특히 2~4번 문장이 길어지기 쉬우니 군더더기 수식어를 빼고 한 가지 장면만 쓴다.

[사실 규칙 - 가장 중요]
- 상품 정보는 상품명이 거의 전부다. 상품명에 드러나지 않은 속성(충전식인지 유선인지, 방수인지, 소음, 소재, 조명 기능 등)은 절대 단정하지 않는다. 추측이 필요한 부분은 쓰지 말고 사용 장면과 기분 위주로 쓴다.
- 색상(파란색, 검은색, 흰색 등)을 말하지 않는다. 상품 사진과 영상의 색이 다를 수 있다.
- 건강/의료/치료/예방 효과를 말하지 않는다. (나쁜 예: "치과 갈 일이 줄어들지" "잇몸까지 시원하게")
- 존재하지 않는 장면을 만들지 않는다. (나쁜 예: 드라이어로 "차에서 머리 식히기", 선풍기를 "방송할 때 조용히")

[문장 품질 규칙]
- 같은 어미 반복 금지: "~더라"는 대본 전체에서 최대 1번, "~함"은 최대 2번. 나머지는 "~야" "~지" "~됨" "~거든" "~인데" 등으로 바꿔 쓴다.
- 명령형은 마지막 CTA 외에는 쓰지 않는다. ("꺼내서 바로 연결해" 같은 어색한 명령 금지)
- 한 문장에 한 가지 말만 한다. 접속이 어색한 두 문장을 억지로 이어 붙이지 않는다.
- 좋은 문장 예: "무선인데도 옛날 패드 손맛 그대로 살아 있더라." "책상 위 원하는 곳에 딱 맞춰 바람을 보낼 수 있음." "라이딩 나가기 전에 타이어 바람 빠진 거 보고 한숨 나온 적 있지?"
- 나쁜 문장 예: "가볍고 충전돼서 여행 갈 때 챙기기도 편함." (근거 없는 충전) "이거 하나 들고 다니면 충전기 찾을 일 없이 알아서 금방 채워줌." (뜻이 겹치고 어색) "친구 집이나 캠핑장에서도 꺼내서 바로 연결해." (명령형) "바람이 진짜 세게 나오는데 궁금하면 링크에서 봐." (공식 같은 마무리)

[구조] 정확히 6문장 (23~25초 분량)
1. 훅: 누구나 매일 겪는 진짜 불편함에 공감하는 구어체 질문. 공백 포함 22~34자.
2. 핵심 기능: 써보니 이게 해결되더라는 체감과 동작 묘사. 어려운 기술 용어 없이 한국인이 일상에서 쓰는 직관적인 표현만. 한 호흡으로 공백 포함 30~38자.
   예: "마른 얼굴에 대고 쓱 문지르면 10초 만에 깔끔하게 다 잘림."
3. 추가 장점: 배터리 휴대성 보관 같은 실사용 디테일. 공백 포함 30~38자.
4. 활용 팁: 실내 야외 차량 등 구체적으로 어디서 어떻게 쓰는지 상황 묘사. 공백 포함 26~34자.
5. 호기심 유발: 이 상품만의 포인트 하나를 짚어서 "어떤 느낌일지 궁금해지게" 끝낸다. "링크"라는 단어는 쓰지 않는다(마지막 CTA 문장이 링크를 안내한다). 가격 할인 언급 금지. 공백 포함 20~40자. 4번과 같은 말을 반복하지 않는다.
6. CTA 고정 문장: 정확히 "{LAST_LINE}"

상품명: {name}
특징: {features}

위 상품의 귀차니스트 마멋 스타일 쇼츠 대본을 JSON으로만 출력해.
규칙:
- 이모지 괄호 따옴표 금지. 과장 허위 효능 금지. 가격 할인율 금액 언급 금지. 상품명과 특징에 있는 사실에서 벗어난 기능을 지어내지 않는다.
- title: 화면 상단에 크게 나올 훅 제목 1개. 훅 규칙을 따르되 문장이 끝까지 완결돼야 한다(말줄임이나 끊긴 문장 금지: "바람 빠져 있으면?" 같은 불완전한 문장 X, "바람 빠진 타이어 만난 적 있지?" O). 공백 포함 20자 이내.
- headline: 3초 뒤 상단에 교체되어 나올 상품 핵심 솔루션 요약. 상품명과 특징에 있는 사실만 써서 공백 포함 18자 이내의 자연스러운 한국어 명사구. 가격 언급 금지.
- keywords: 자막에서 노란색으로 강조할 핵심 단어 2~4개 (sentences 안에 글자 그대로 등장하는 단어)
- hashtags: 해시태그 정확히 5개 ('#' 포함 마지막은 #마멋선생)
- pinned_comment: 댓글 문구. 쇼츠 댓글의 링크는 클릭이 안 되므로 URL을 넣지 말고 "프로필 링크에서 제품 확인" 취지로 안내하고, 제휴 마케팅 수수료 지급 안내 문구를 반드시 포함.
출력 형식: {{"sentences":["훅","핵심 기능","추가 장점","활용 팁","호기심 유발","{LAST_LINE}"],"title":"...","headline":"...","keywords":[...],"hashtags":[...],"pinned_comment":"..."}}"""
    last_err = None
    soft = None          # (편차, 대본): 글자 수만 어긋난 시도 중 가장 근접한 것
    for attempt in range(1, API_RETRIES + 1):
        try:
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.8,
                },
                timeout=(10, 60),
            )
            if resp.status_code in (401, 403):
                sys.exit("[오류] DeepSeek API 키가 거부되었습니다(401/403). .env의 DEEPSEEK_API_KEY를 확인하세요.")
            if resp.status_code == 402:
                sys.exit("[오류] DeepSeek 잔액이 부족합니다(402). 플랫폼에서 충전 후 다시 시도하세요.")
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            (WORK_DIR / "deepseek_response.json").write_text(raw, encoding="utf-8")   # 원본 응답 보관
            parsed = parse_json_loose(raw)
            try:
                return review_script(api_key, name, features, validate_script(parsed))
            except LengthError as e:
                if soft is None or e.deviation < soft[0]:
                    soft = (e.deviation, parsed)
                raise
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            last_err = e
            print(f"  [경고] DeepSeek 호출/파싱 실패 {attempt}/{API_RETRIES}: {type(e).__name__}: {e}")
            time.sleep(1.5 * attempt)
    if soft and soft[0] <= SOFT_PASS_DEV:
        print(f"  [소프트 패스] 글자 수 편차 {soft[0]}자(허용 {SOFT_PASS_DEV}자 이내)라 그대로 사용합니다.")
        return soft[1]
    raise RuntimeError(f"DeepSeek 대본 생성 실패: {last_err}")


def review_script(api_key: str, name: str, features: str, d: dict) -> dict:
    """생성된 대본을 한 번 더 읽혀서 어색하거나 사실과 다른 문장/제목만 고친다.
    규칙 검증을 못 넘기면 거부 사유를 알려주고 한 번 더 시도하며, 끝내 실패하면 원본을 쓴다."""
    base = f"""아래는 쇼츠 대본 JSON이다. 상품: {name} / 특징: {features}

{json.dumps(d, ensure_ascii=False)}

한국인이 소리 내어 읽었을 때 어색하거나 뜻이 불분명한 문장(조사 누락, 번역투, 앞뒤 모순, 상품과 무관한 내용, 말이 안 되는 상황)이 있는지 문장 하나씩 점검하라.
[사실 검증] 각 문장의 주장을 하나씩 뽑아, 상품명과 특징에서 확인되는 사실인지 따져라. 확인되지 않는 기능·장면(예: 상품명에 없는 벽걸이, 충전식 여부, 소음, 방송용 등)이나 상품의 용도와 맞지 않는 훅(다른 상품 얘기)은 상품명에서 확실한 사실과 일반적인 사용 장면만으로 다시 써라.
문제 있는 문장과 title/headline만 자연스럽게 고치고 문제 없는 문장은 글자 그대로 둔다. 문장 수와 순서, 글자 수 범위(공백 포함), 마지막 고정 CTA 문장, 쉼표 금지, 가격 언급 금지는 유지한다.
다음은 반드시 지킨다: 숫자(2자리 이상)와 용량/전원/풍속 등 스펙 수치·단위(ml mAh W Pa cm 등)를 쓰지 않는다. "링크"는 5번째 문장에 쓰지 않는다. "~더라"는 한 번만, "~함"은 두 번까지.
상품명과 특징에 없는 기능을 지어내지 않는다. 같은 JSON 형식으로만 출력."""
    feedback = ""
    for attempt in (1, 2):
        try:
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": base + feedback}],
                      "response_format": {"type": "json_object"}, "temperature": 0.3},
                timeout=(10, 60),
            )
            resp.raise_for_status()
            fixed = parse_json_loose(resp.json()["choices"][0]["message"]["content"])
            try:
                fixed = validate_script(fixed)
            except LengthError as e:
                if e.deviation > SOFT_PASS_DEV:
                    raise
            (WORK_DIR / "deepseek_review.json").write_text(json.dumps(fixed, ensure_ascii=False, indent=1), encoding="utf-8")
            changed = sum(a != b for a, b in zip(d["sentences"], fixed["sentences"])) + (d.get("title") != fixed.get("title"))
            print(f"  [검수] {changed}곳 수정" if changed else "  [검수] 수정할 곳 없음")
            return fixed
        except Exception as e:      # 검수는 보너스: 실패하면 사유를 알려 한 번 더, 그래도 안 되면 원본 유지
            print(f"  [검수 재시도 {attempt}/2] {type(e).__name__}: {e}")
            feedback = "\n\n[직전 출력이 다음 규칙 위반으로 거부됨: " + str(e) + "] 이 문제를 고쳐서 다시 출력."
    print("  [검수 생략] 원본 대본을 사용합니다.")
    return d


def parse_json_loose(raw: str) -> dict:
    """```json 펜스나 앞뒤 잡설이 붙어도 첫 JSON 객체를 꺼낸다."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError("응답에서 JSON 객체를 찾지 못했습니다")
        return json.loads(m.group(0))


def _same(a: str, b: str) -> bool:
    return a.replace(" ", "") == b.replace(" ", "")


class LengthError(ValueError):
    """문장 글자 수만 범위를 벗어난 경우. deviation = 범위를 벗어난 최대 글자 수."""

    def __init__(self, msg: str, deviation: int):
        super().__init__(msg)
        self.deviation = deviation


# 문장별 허용 글자 수(공백 포함). 프롬프트 지시 범위보다 위아래로 5자 정도 여유를 둔다.
LEN_LIMITS = ((17, 38), (21, 43), (21, 43), (19, 39), (17, 45))     # 자막이 화면 2줄에 읽기 좋게 들어가는 길이
SOFT_PASS_DEV = 3        # 3회 모두 길이만 어긋났다면 범위를 3자 이내로 벗어난 대본은 그대로 통과시킨다


def validate_script(d: dict) -> dict:
    """필수 필드/문장 수/금지 요소를 검사한다. 어긋나면 ValueError → 재시도.
    글자 수는 마지막에 검사하며 LengthError(편차 포함)로 알려 소프트 패스 판단에 쓴다."""
    sents = d.get("sentences")
    if not isinstance(sents, list) or not all(isinstance(x, str) for x in sents):
        raise ValueError("sentences가 문자열 배열이 아닙니다")
    body = [x.strip() for x in sents if x.strip() and not is_fixed(x)]
    if len(body) != 5:
        raise ValueError(f"훅+핵심 기능+추가 장점+활용 팁+호기심 5문장이어야 합니다({len(body)}개)")
    joined = " ".join(sents)
    if TRANSL_RE.search(joined):
        raise ValueError("직역투/기계 번역투 표현이 들어 있습니다")
    if CLICHE_RE.search(" ".join(body)):
        raise ValueError("천편일률 문장 패턴이 들어 있습니다")
    if SPEC_RE.search(" ".join(body)):
        raise ValueError("스펙/수치 나열이 들어 있습니다")
    if COLOR_RE.search(joined):
        raise ValueError("색상 언급이 들어 있습니다(상품 색을 단정하지 않는다)")
    if HEALTH_RE.search(joined):
        raise ValueError("의학적/건강 효능 주장이 들어 있습니다")
    if sum(x.rstrip(".").endswith("더라") for x in body) > 1:
        raise ValueError("~더라 어미가 두 번 이상 반복됩니다")
    if sum(x.rstrip(".").endswith("함") for x in body) > 2:
        raise ValueError("~함 어미가 세 번 이상 반복됩니다")
    if "링크" in body[-1]:
        raise ValueError("호기심 문장(5번)에 링크 언급이 들어 있습니다")
    if PRICE_RE.search(joined):
        raise ValueError("대본에 구체적 가격/할인율이 들어 있습니다")
    if OLD_MAN.search(joined):
        raise ValueError("노인 말투가 섞여 있습니다")
    if re.search(r"물 ?(묻|적시|넣|채우)", joined) and re.search(r"물 ?없이|마른 ?(상태|채)", joined):
        raise ValueError("사용법이 서로 모순됩니다(물 사용 여부)")
    if not str(d.get("title", "")).strip():
        raise ValueError("title이 비어 있습니다")
    worst, msg = 0, ""
    for x, (lo, hi) in zip(body, LEN_LIMITS):
        n = len(x.replace(",", ""))
        dev = max(lo - n, n - hi, 0)
        if dev > worst:
            worst, msg = dev, f"문장 길이가 범위({lo}~{hi}자)를 벗어났습니다({n}자): {x}"
    if worst:
        raise LengthError(msg, worst)
    return d


def normalize_script(d: dict) -> dict:
    clean = lambda t: re.sub(r"\s+", " ", re.sub(r"[,，、]", " ", t)).strip()      # 쉼표 완전 제거
    sents = [clean(s) for s in d["sentences"] if s.strip()]
    sents = [s for s in sents if s and not is_fixed(s)]
    sents = sents[:5] + [LAST_LINE]   # 훅 + 핵심 기능 + 추가 장점 + 활용 팁 + 호기심 + CTA
    tags = [t if t.startswith("#") else "#" + t for t in d.get("hashtags", [])][:5]
    comment = f"🔥 초특가 링크: {PLACEHOLDER}\n{DISCLOSURE}"      # 모델 문구 대신 고정 형식 (링크는 main에서 치환)
    text = " ".join(sents)
    kws = [k.strip() for k in d.get("keywords", []) if isinstance(k, str) and k.strip() and k.strip() in text][:4]
    if not kws:   # 모델이 키워드를 못 줬으면 숫자가 든 단어를 노란색 강조 대상으로 사용
        kws = [w for w in re.findall(r"\S*\d\S*", text)][:3]
    title = clean(str(d.get("title", "")))
    if len(title) > MAX_TITLE:   # 물음표 앞에서, 없으면 단어 경계에서 자른다
        head = re.split(r"[?!]", title)[0].strip()
        title = head if 6 <= len(head) <= MAX_TITLE else title[:MAX_TITLE].rsplit(" ", 1)[0].rstrip(" ,")
    headline = clean(str(d.get("headline", "")))[:20]
    if PRICE_RE.search(headline):
        headline = ""
    return {"sentences": sents, "title": title, "headline": headline, "keywords": kws, "hashtags": tags,
            "pinned_comment": comment}


def load_reuse_script(replaces: list[str]) -> dict:
    """직전 실행의 result_meta.json / result_text.txt 로 대본 dict 를 복원하고 '원문=>수정문' 치환을 적용한다."""
    meta = json.loads((OUT_DIR / "result_meta.json").read_text(encoding="utf-8"))
    text = (OUT_DIR / "result_text.txt").read_text(encoding="utf-8")
    body = text.split("[대본]")[1].strip().splitlines()
    d = {"sentences": [s.strip() for s in body if s.strip()], "title": meta["title"], "headline": meta.get("headline", ""),
         "keywords": meta["keywords"], "hashtags": meta["hashtags"], "pinned_comment": meta["pinned_comment"]}
    for r in replaces:
        old, new = r.split("=>", 1)
        hit = False
        for k in ("title", "headline"):
            if old in d[k]:
                d[k], hit = d[k].replace(old, new), True
        for i, s in enumerate(d["sentences"]):
            if old in s:
                d["sentences"][i], hit = s.replace(old, new), True
        if not hit:
            sys.exit(f"[오류] --replace 대상 문구를 대본에서 찾지 못했습니다: {old}")
    return d


def save_result_text(d: dict):
    OUT_DIR.mkdir(exist_ok=True)
    text = (
        f"[후킹 제목]\n{d['title']}\n\n"
        f"[해시태그]\n{' '.join(d['hashtags'])}\n\n"
        f"[고정 댓글]\n{d['pinned_comment']}\n\n"
        f"[대본]\n" + "\n".join(d["sentences"]) + "\n"
    )
    (OUT_DIR / "result_text.txt").write_text(text, encoding="utf-8")


# ───────────────────────── 2. 음성 + 자막 ─────────────────────────
_PA = re.compile(r"(\d+)\s*pa\b", re.I)
_TTS_WORDS = [
    (re.compile(r"(\d+)\s*ml\b", re.I), r"\1밀리"),
    (re.compile(r"(\d+)\s*mah\b", re.I), r"\1밀리암페어"),
    (re.compile(r"(\d+)\s*cm\b", re.I), r"\1센티"),
    (re.compile(r"\bUSB\b", re.I), "유에스비"),
    (re.compile(r"\bLED\b", re.I), "엘이디"),
]


def _man_cheon(m: re.Match) -> str:
    """13000Pa -> '만 3천 파스칼', 5000Pa -> '5천 파스칼'. 10만 이상이거나 천 단위가 아니면 숫자를 그대로 둔다."""
    n = int(m.group(1))
    if n >= 100000 or n % 1000:
        return f"{n} 파스칼"
    man, chun = divmod(n, 10000)
    parts = ([("만" if man == 1 else f"{man}만")] if man else []) + ([f"{chun // 1000}천"] if chun else [])
    return " ".join(parts) + " 파스칼"


def tts_text(text: str) -> str:
    """영문 단위/약어를 한국어 구어체 발음으로 바꾼다 (자막 원문은 그대로 두고 음성에만 적용)."""
    text = _PA.sub(_man_cheon, text)
    for rx, rep in _TTS_WORDS:
        text = rx.sub(rep, text)
    return text


async def _tts(text: str, path: Path) -> list[dict]:
    """mp3 를 저장하고 단어별 발화 시각(초)을 돌려준다 (edge-tts WordBoundary)."""
    import edge_tts
    words = []
    comm = edge_tts.Communicate(tts_text(text), VOICE, rate=RATE, pitch=PITCH, boundary="WordBoundary")
    with open(path, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"w": ch["text"], "t0": ch["offset"] / 1e7, "t1": (ch["offset"] + ch["duration"]) / 1e7})
    return words


def synth_audio(sentences: list[str]) -> tuple[Path, list[float], list[list[dict]]]:
    """문장별 TTS 를 첫 발화 직전부터 자르고 끝 무음은 제거한 뒤 GAP 만큼만 띄워 이어붙인다(무손실 wav).
    durs 는 GAP 을 포함한 '실제 오디오 길이'이며 영상 컷 전환 기준이 된다.
    words 는 각 문장 시작(=잘린 지점) 기준으로 보정한 단어별 발화 시각이다."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    parts, durs, all_words = [], [], []
    for i, s in enumerate(sentences):
        raw = WORK_DIR / f"tts_{i}.mp3"
        words = asyncio.run(_tts(s, raw))
        lead = max(0.0, words[0]["t0"] - 0.03) if words else 0.0
        head = f"atrim=start={lead:.3f},asetpts=PTS-STARTPTS" if words else "silenceremove=start_periods=1:start_threshold=-50dB"
        af = (f"{head},areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
              f"apad=pad_dur={GAP}")
        p = WORK_DIR / f"tts_{i}.wav"
        run([FFMPEG, "-y", "-i", str(raw), "-af", af, "-ar", "44100", "-ac", "1", str(p)])
        parts.append(p)
        durs.append(duration(p))
        all_words.append([{"w": w["w"], "t0": max(0.0, w["t0"] - lead), "t1": max(0.0, w["t1"] - lead)} for w in words])
    lst = WORK_DIR / "tts_list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    out = OUT_DIR / "voice.wav"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])   # 재인코딩 없음: 길이/위치 오차 0
    return out, durs, all_words


_CAP_PUNCT = re.compile(r"[,.\"\u201c\u201d'\u2018\u2019()]")


def build_words(sentence: str, words: list[dict]) -> list[dict] | None:
    """자막 어절별 발화 시각(문장 시작 기준 초). TTS 단어 수와 자막 어절 수가 맞을 때만 돌려준다 (아니면 None)."""
    tokens = _CAP_PUNCT.sub(" ", sentence).split()
    if not tokens or len(words) != len(tokens):
        return None
    return [{"text": t, "start": round(w["t0"], 3), "end": round(w["t1"], 3)} for t, w in zip(tokens, words)]


def collect_media() -> list[Path]:
    SAMPLE_DIR.mkdir(exist_ok=True)
    files = sorted(
        (p for p in SAMPLE_DIR.rglob("*") if p.suffix.lower() in MEDIA_EXT),
        key=lambda p: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", str(p))],
    )
    if not files:
        print("[안내] sample_images가 비어 있어 테스트 이미지 4장을 생성합니다.")
        files = make_samples()
    return files


def make_samples() -> list[Path]:
    from PIL import Image, ImageDraw, ImageFont
    font_path, _ = detect_font()
    font = ImageFont.truetype(str(font_path), 160)
    colors = [(231, 76, 60), (52, 152, 219), (46, 204, 113), (155, 89, 182)]
    out = []
    for i, c in enumerate(colors, 1):
        img = Image.new("RGB", (1200, 1200), c)
        ImageDraw.Draw(img).text((600, 600), f"샘플 {i}", font=font, fill="white", anchor="mm")
        p = SAMPLE_DIR / f"sample_{i}.jpg"
        img.save(p, quality=92)
        out.append(p)
    return out



def frame_source(src: Path, idx: int) -> Path:
    """영상 소재는 대표 프레임 한 장을 뽑아 이미지로 쓴다."""
    if src.suffix.lower() not in VIDEO_EXT:
        return src
    out = WORK_DIR / f"still_{idx}.jpg"
    run([FFMPEG, "-y", "-ss", "0.5", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(out)])
    return out


ASSETS = ROOT / "assets"


def pick_bgm() -> Path | None:
    """assets/ 안의 mp3 중 무작위 1곡 (파일명 무관)."""
    tracks = sorted(ASSETS.glob("*.mp3"))
    return random.choice(tracks) if tracks else None

REMOTION_DIR = ROOT / "remotion_shorts"
REMOTION_PUBLIC = REMOTION_DIR / "public"
REMOTION_DATA = REMOTION_DIR / "src" / "data.json"
FINAL_OUT = OUT_DIR / "shorts_remotion.mp4"
MARMOT_DIR = ROOT / "마멋선생"
PLACEHOLDER = "(여기에 제휴 링크 입력)"
TAIL = 1.5          # 마지막 문장 이후 여운(초): BGM이 커졌다가 페이드아웃되는 구간


def prepare_marmot(dest: Path) -> str | None:
    """마멋선생/이미지의 투명 PNG를 여백 없이 잘라 public/ 에 배치한다."""
    hits = sorted((MARMOT_DIR / "이미지").glob("*beaver*.png"))
    if not hits:
        print("  [안내] 마멋선생/이미지에 캐릭터 PNG가 없어 캐릭터 없이 렌더링합니다.")
        return None
    from PIL import Image
    im = Image.open(hits[0]).convert("RGBA")
    im = im.crop(im.getchannel("A").getbbox())
    im.thumbnail((900, 900))
    im.save(dest)
    return dest.name


# 문장 순서별 마멋 표정(마멋선생/표정/marmot_<이름>.png, prepare_expressions.py 로 생성):
# 훅(곤란) -> 핵심 기능(놀람) -> 추가 장점(웃음) -> 활용 팁(생각) -> 호기심(윙크) -> CTA(닦달)
EXPRESSION_PLAN = ["worried", "shocked", "laugh", "think", "wink", "angry"]


def prepare_expressions(count: int) -> list[str] | None:
    """표정 PNG를 public/ 에 배치하고 문장별 파일명 목록을 돌려준다. 하나라도 없으면 None(단일 마멋 이미지 사용)."""
    src_dir = MARMOT_DIR / "표정"
    names = [EXPRESSION_PLAN[i % len(EXPRESSION_PLAN)] for i in range(count)]
    if not all((src_dir / f"marmot_{n}.png").exists() for n in set(names)):
        return None
    from PIL import Image
    for n in set(names):
        im = Image.open(src_dir / f"marmot_{n}.png").convert("RGBA")
        im.thumbnail((700, 700))
        im.save(REMOTION_PUBLIC / f"marmot_{n}.png")
    return [f"marmot_{n}.png" for n in names]


def probe_video_size(url: str) -> tuple[int, int]:
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", url], capture_output=True, text=True, timeout=60)
    try:
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except ValueError:
        return 0, 0


def build_remotion_data(data: dict, sentences: list[str], durs: list[float], audio: Path,
                        media: list[Path], bgm: Path | None, image_urls: list[str],
                        video: Path | None = None, words: list[list[dict]] | None = None,
                        badge: str = "", broll_clips: list[Path] | None = None, hero: bool = False,
                        concept_key: str = "") -> dict:
    """문장별 TTS 길이(초)와 에셋을 remotion_shorts/public 으로 복사하고 src/data.json 을 기록한다."""
    REMOTION_PUBLIC.mkdir(parents=True, exist_ok=True)
    for old in REMOTION_PUBLIC.glob("*"):          # 이전 실행의 에셋 정리
        if old.is_file():
            old.unlink()
    shutil.copy2(audio, REMOTION_PUBLIC / audio.name)
    images = list(image_urls)
    for i, m in enumerate(media):
        still = frame_source(m, i)
        name = f"product_{i}{still.suffix.lower()}"
        shutil.copy2(still, REMOTION_PUBLIC / name)
        images.append(name)
    video_name, video_info = None, None
    if video:
        video_name = "product_video.mp4"
        shutil.copy2(video, REMOTION_PUBLIC / video_name)
        r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height:format=duration", "-of", "json", str(video)])
        j = json.loads(r.stdout)
        video_info = {"width": j["streams"][0]["width"], "height": j["streams"][0]["height"],
                      "duration": float(j["format"]["duration"])}
    broll_names = []
    hero_trim = 0.0
    if hero and broll_clips:                 # 마멋선생 AI 영상을 훅 컷(첫 컷)에 쓴다
        broll_clips = [broll.pick("_mascot", 1, MASCOT_TONE.get(concept_key, "calm"))[0]] + list(broll_clips)[:-1]
        off = broll.BROLL_DIR / "_mascot" / "offsets.json"      # 클립별 훅 시작 지점(초): 가만히 서 있는 앞부분을 건너뛴다
        if off.exists():
            hero_trim = float(json.loads(off.read_text(encoding="utf-8")).get(broll_clips[0].name, 0))
    for i, c in enumerate(broll_clips or []):
        name = f"broll_{i}.mp4"
        shutil.copy2(c, REMOTION_PUBLIC / name)
        broll_names.append(name)
    marmot_name = prepare_marmot(REMOTION_PUBLIC / "marmot.png")
    expressions = prepare_expressions(len(sentences))
    bgm_name = None
    if bgm:
        bgm_name = f"bgm{bgm.suffix.lower()}"
        shutil.copy2(bgm, REMOTION_PUBLIC / bgm_name)
    payload = {
        "title": data["title"],
        "headline": data.get("headline", ""),
        "badge": badge,
        "keywords": data["keywords"],
        "images": images,
        "sentences": [{"text": s, "duration": round(d, 4),
                       "words": build_words(s, (words or [[]] * len(sentences))[i])}
                      for i, (s, d) in enumerate(zip(sentences, durs))],
        "voice": audio.name,
        "bgm": bgm_name,
        "marmot": marmot_name,
        "marmotExpressions": expressions,
        "video": video_name,
        "broll": broll_names,
        "brollSources": [str(c.relative_to(ROOT)) for c in (broll_clips or [])],
        "heroFirst": bool(hero and broll_clips),
        "heroTrim": hero_trim,
        "videoInfo": video_info,
        "tail": TAIL,
    }
    REMOTION_DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def render_remotion(out_path: Path = FINAL_OUT) -> Path:
    """npx remotion render 를 서브프로세스로 실행해 output/shorts_remotion.mp4 를 만든다."""
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        sys.exit("[오류] Node.js(npx)를 찾을 수 없습니다. https://nodejs.org 에서 설치하세요.")
    if not (REMOTION_DIR / "node_modules").exists():
        print("  remotion_shorts 의존성 설치 중 (npm install)...")
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        r = subprocess.run([npm, "install"], cwd=REMOTION_DIR)
        if r.returncode != 0:
            sys.exit("[오류] npm install 실패")
    out_path.parent.mkdir(exist_ok=True)
    cmd = [npx, "remotion", "render", "src/index.ts", "Shorts", str(out_path), "--overwrite"]
    r = subprocess.run(cmd, cwd=REMOTION_DIR)       # 진행률을 터미널에 그대로 출력
    if r.returncode != 0 or not out_path.exists():
        sys.exit(f"[Remotion 오류] 렌더링 실패 (exit {r.returncode})")
    return out_path




# ───────────────────────── 작업 기록 ─────────────────────────
LOG_DIR = ROOT / "작업기록"


def work_stem(data: dict, full_name: str) -> str:
    """영상 파일과 작업 기록이 같이 쓰는 이름: YY.MM.DD-상품 요약 (같은 이름이 있으면 -2, -3 ...)"""
    short = re.sub(r'[<>:"/\\|?*]', "", (data.get("headline") or full_name)[:30]).strip() or "상품"
    stem = f"{time.strftime('%y.%m.%d')}-{short}"
    cand, n = stem, 2
    while (LOG_DIR / f"{cand}.md").exists() or (OUT_DIR / f"{cand}.mp4").exists():
        cand = f"{stem}-{n}"
        n += 1
    return cand


def write_work_log(data: dict, product: dict | None, args, concept: dict, full_name: str, payload: dict, out: Path) -> Path:
    """영상 하나당 작업 기록 MD 를 남긴다. 파일명: YY.MM.DD-상품명.md (예: 26.10.19-메가드라이브 스타일 게임패드.md)"""
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{out.stem}.md"        # 영상 파일명과 같은 이름
    sub = classify_sub(full_name, concept["key"]) or "-"
    used_video = bool(payload.get("video"))
    lines = [
        f"# {path.stem}", "",
        "## 상품",
        f"- 상품명: {full_name}",
        f"- 알리 상품 ID: {product['product_id'] if product else '-'}",
        f"- 제휴 링크: {args.link or '-'}",
        f"- 콘셉트: {concept['name']} / b-roll 유형: {sub}", "",
        "## 영상",
        f"- 파일: {out.relative_to(ROOT)}",
        f"- 상품 시연 영상: {'사용' if used_video else '없음 (b-roll + 상품 이미지로 구성)'}",
        f"- 상품 이미지: {sum(1 for i in payload['images'] if not i.startswith('http'))}장",
        f"- 마멋 훅 영상 사용: {'예' if payload.get('heroFirst') else '아니오'}",
        "- 사용한 b-roll:", *[f"  - {s}" for s in payload.get("brollSources", [])], "",
        "## 대본",
        f"- 상단 제목: {data['title']}",
        f"- 3초 뒤 문구: {data.get('headline', '')}", "",
        *[f"{i}. {s}" for i, s in enumerate(data["sentences"], 1)], "",
        "## 업로드용",
        f"- 해시태그: {' '.join(data['hashtags'])}",
        f"- 고정 댓글: {data['pinned_comment'].splitlines()[0] if data['pinned_comment'] else ''}", "",
        "## 업로드 결과",
        "- (아직 업로드 전)", "",
        "## 메모", "-", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ───────────────────────── main ─────────────────────────
def main():
    global FFMPEG, FFPROBE
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="케이블 일체형 10000mAh 소형 보조배터리")
    ap.add_argument("--features", default="10000mAh 대용량, 케이블 내장, 초소형 경량, 아이폰/갤럭시 호환")
    ap.add_argument("--offline", action="store_true", help="DeepSeek 호출 없이 내장 샘플 대본 사용")
    ap.add_argument("--csv", action="store_true", help="data/hot_products.xlsx(없으면 .csv)의 상위 상품으로 자동 제작")
    ap.add_argument("--min-price", type=int, default=5000, help="자동 선별 시 할인가 하한(원): 1~4천 원대 비닐/소모품/부속 파츠 차단")
    ap.add_argument("--max-price", type=int, default=50000, help="자동 선별 시 할인가 상한(원): 충동구매형 꿀템만 (0이면 무제한)")
    ap.add_argument("--select-only", action="store_true", help="상품 선정(필터+비디오+링크 검증)까지만 하고 종료 (예약/렌더링/업로드 없음)")
    ap.add_argument("--no-history", action="store_true", help="렌더링한 상품을 사용 이력(data/trend_history.json)에 기록하지 않음")
    ap.add_argument("--out", help="출력 파일명 (output/ 아래, 기본: shorts_product_NN.mp4)")
    ap.add_argument("--min-video-res", type=int, default=720, help="--video-only: 영상 짧은 변 최소 해상도(px)")
    ap.add_argument("--rank", type=int, help="--csv 사용 시 엑셀 N위 상품을 필터 없이 직접 지정 (생략하면 자동 선별)")
    ap.add_argument("--ali-url", help="알리익스프레스 상품 URL (sample_images에 소재 다운로드)")
    ap.add_argument("--image-url", action="append", help="상품 이미지 URL (여러 번 지정 가능, 지정 시 sample_images보다 앞에 사용)")
    ap.add_argument("--reuse-script", action="store_true", help="새 대본을 만들지 않고 직전 대본(output/result_*)을 재사용 (문장만 고쳐 다시 렌더링할 때)")
    ap.add_argument("--replace", action="append", default=[], metavar="원문=>수정문", help="--reuse-script 와 함께: 대본 문장/제목의 일부를 바꾼다 (여러 번 지정 가능)")
    ap.add_argument("--bgm", help="BGM 파일 경로 (기본: assets/ 안 mp3 중 무작위)")
    ap.add_argument("--upload", action="store_true", help="렌더링 후 YouTube에 업로드")
    ap.add_argument("--privacy", default=None, choices=["private", "unlisted", "public"],
                    help="업로드 공개 범위 (기본: uploader.DEFAULT_PRIVACY = unlisted)")
    ap.add_argument("--link", help="고정 댓글/설명의 제휴 링크 (자리표시자를 대체)")
    args = ap.parse_args()

    FFMPEG, FFPROBE = find_tool("ffmpeg"), find_tool("ffprobe")
    api_key = ensure_env()
    OUT_DIR.mkdir(exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    pick_lines()
    pre_data = None                 # 선정 단계에서 미리 만든 대본
    product = None
    finished = {"ok": False}        # 렌더링 성공 전에 죽으면 예약(used)을 풀어준다
    if args.csv:
        from concepts import classify
        from ali_csv_loader import (check_affiliate_link, download_gallery, load_products, product_features, rank_candidates,
                                    priority_hits, top_product)
        from ali_trend_collector import _load_history, mark_used, release_used
        pool = load_products(verbose=True)
        used = _load_history()
        if args.rank:
            product = pool[args.rank - 1]
            ok, why = check_affiliate_link(product["affiliate_link"], product["product_id"])
            if not ok:
                print(f"  [경고] 직접 지정한 {args.rank}위의 제휴 링크가 유효하지 않습니다: {why}")
        else:
            # 제외 키워드 필터 -> 우선 키워드/판매량 순 -> 비디오 해상도 확인
            for rk, cand in rank_candidates(pool, need_video=False, exclude_ids=used, max_price=args.max_price,
                                            min_price=args.min_price):
                has_broll = bool(broll.list_clips(classify(cand["name"])[0]["key"]))
                if not cand["video"] and not has_broll:       # 상품 영상도 b-roll 도 없으면 슬라이드쇼가 되므로 제외
                    continue
                w, h = probe_video_size(cand["video"]) if cand["video"] else (args.min_video_res, args.min_video_res)
                tag = ",".join(priority_hits(cand["name"])) or "-"
                print(f"  [후보] {rk}위 {cand['price']} 판매 {cand['sales']} 비디오 {w}x{h} 키워드[{tag}] {cand['name'][:40]}")
                if min(w, h) < args.min_video_res:           # 해상도 미달 비디오는 큐에서 제외 (이미지 대체 없음)
                    continue
                ok, why = check_affiliate_link(cand["affiliate_link"], cand["product_id"])
                print(f"    제휴 링크 검증: {'통과' if ok else '탈락'} ({why})")
                if not ok:
                    continue
                if not (args.select_only or args.offline or not api_key or args.reuse_script):
                    # 대본이 이 상품으로 정상 생성되는지 먼저 확인: 실패하면 다른 상품 대본으로 대체하지 않고 다음 상품으로 넘어간다
                    try:
                        pre_data = generate_script(api_key, cand["name"][:80], product_features(cand), classify(cand["name"])[0])
                        print("  [DeepSeek] 대본 생성 성공")
                    except RuntimeError as e:
                        print(f"  [건너뜀] {rk}위 대본 생성 실패 → 큐의 다음 상품으로 넘어갑니다: {e}")
                        continue
                args.rank, product = rk, cand
                break
            if not product:
                sys.exit(f"[오류] 필터/비디오(해상도 {args.min_video_res}px 이상)/제휴 링크 검증을 통과한 상품이 없습니다.")
        if args.select_only:
            print(f"[선정만] {args.rank}위 {product['product_id']} {product['name'][:50]} / {product['affiliate_link']}")
            return
        if not args.no_history:
            # 렌더링 시작 전에 예약 기록: 같은 큐를 도는 다음 실행이 이 상품을 절대 다시 잡지 않는다
            mark_used(product["product_id"])
            atexit.register(lambda pid=product["product_id"]: None if finished["ok"] else release_used(pid))
        args.name, args.features = product["name"][:80], product_features(product)
        args.link = args.link or product["affiliate_link"]
        print(f"[엑셀] {args.rank}위: {product['name'][:50]} / {product['price']} / {product['affiliate_link']}")

    if args.ali_url:
        from ali_downloader import download_product_media
        n = download_product_media(args.ali_url, SAMPLE_DIR / "ali")
        print(f"[알리] {n}개 파일 다운로드 완료")

    full_name = product["name"] if product else args.name       # 80자로 잘린 이름이 아니라 전체 상품명으로 분류
    concept, matched = classify(full_name)
    print(f"  [콘셉트] {concept['name']} ({'키워드 매칭' if matched else '기본값'}) / 뱃지: {concept['badge']}")
    print("1) 대본 생성")
    if args.reuse_script:
        data = load_reuse_script(args.replace)
        print("  [재사용] 직전 대본을 그대로 사용합니다.")
    elif args.offline or not api_key:
        if not args.offline:
            print("  [경고] DEEPSEEK_API_KEY가 비어 있어 내장 샘플 대본을 사용합니다.")
        data = OFFLINE_SCRIPT           # 샘플 대본은 --offline(또는 키 없음)일 때만 쓴다
    elif pre_data is not None:
        data = pre_data
    else:
        try:
            data = generate_script(api_key, args.name, args.features, concept)    # 직접 지정(--rank/--name) 경로
            print("  [DeepSeek] 대본 생성 성공")
        except RuntimeError as e:
            sys.exit(f"[오류] 대본 생성 실패: {e}\n  (다른 상품용 샘플 대본으로 대체하지 않고 중단합니다)")
    if not args.reuse_script:
        data = normalize_script(data)
    if args.link:
        data["pinned_comment"] = data["pinned_comment"].replace(PLACEHOLDER, args.link)
    save_result_text(data)
    (OUT_DIR / "result_meta.json").write_text(json.dumps({     # uploader.py가 읽는 메타데이터
        "concept": concept["key"], "concept_name": concept["name"], "hook": data["sentences"][0], "title": data["title"], "headline": data.get("headline", ""),
        "keywords": data["keywords"], "hashtags": data["hashtags"], "pinned_comment": data["pinned_comment"],
        "link": args.link or "", "product_id": product["product_id"] if product else "",
        "product_name": product["name"] if product else args.name,
        "image": (product["images"][0] if product and product.get("images") else (args.image_url or [""])[0]),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for s in data["sentences"]:
        print("  -", s)

    print(f"2) 음성 생성 (귀차니스트 마멋 보이스: {VOICE} {PITCH} {RATE})")
    spoken = data["sentences"]                    # 인사말 없이 첫 문장부터 훅으로 진입
    audio, durs, words = synth_audio(spoken)
    print(f"  음성 길이 {sum(durs):.1f}s ({len(spoken)}문장)")

    print("3) Remotion 데이터 생성")
    if product:
        from ali_csv_loader import download_gallery
        from ali_csv_loader import download_video
        video = download_video(product, WORK_DIR / "product_video.mp4")       # 엑셀 Video Url 을 그대로 내려받는다
        if video:
            print("  시연 비디오: 다운로드 완료")
        elif broll.list_clips(concept["key"]):
            print(f"  시연 비디오 없음 → 상황 b-roll({concept['key']}) + 상품 이미지로 구성")
        else:
            sys.exit(f"[오류] 시연 비디오가 없고 b-roll 도 없습니다: {product.get('name', '')[:50]}")
        media = download_gallery(product, WORK_DIR / "gallery")        # 선정된 1개 상품의 상세 사진(컷 1·3용)만 가져온다
        if video:
            product["video_path"] = video
        if not media:
            if not (video or broll.list_clips(concept["key"])):
                sys.exit(f"[오류] 쓸 수 있는 상품 이미지가 없습니다(글자/도표 위주 이미지만 있거나 다운로드 실패): {product['image']}")
            print("  [안내] 쓸 수 있는 상품 이미지가 없어 영상/b-roll 컷만으로 구성합니다.")
        else:
            print(f"  상품 이미지 {len(media)}장 사용 (엑셀 대표 + 상세 페이지 사진) → 비디오와 교차 배치")
    else:
        media = collect_media()
    bgm = Path(args.bgm) if args.bgm else pick_bgm()
    if bgm and bgm.exists():
        print(f"  BGM 랜덤 선택: {bgm.name}")
    else:
        print("  [안내] assets/에 mp3 없음 → BGM 없이 렌더링합니다. (--bgm 경로 지정 또는 assets/에 배치)")
        bgm = None
    payload = build_remotion_data(data, spoken, durs, audio, media, bgm, args.image_url or [],
                       video=product.get("video_path") if product else None, words=words, badge=concept["badge"],
                       broll_clips=broll.pick(concept["key"], 3 if (product and product.get("video_path")) else 4, classify_sub(full_name, concept["key"])),
                       hero=bool(broll.list_clips("_mascot")),          # 마멋 AI 훅 영상은 상품 영상 유무와 상관없이 첫 컷에 쓴다
                       concept_key=concept["key"])
    print(f"  저장: {REMOTION_DATA}")

    print("4) Remotion 렌더링 (npx remotion render)")
    out = render_remotion(OUT_DIR / (args.out or f"{work_stem(data, full_name)}.mp4"))
    print(f"완료: {out}  ({duration(out):.1f}s)")
    finished["ok"] = True                  # 렌더링 성공: 예약 유지 (업로드 성공 시 uploader가 상세 이력을 추가 기록)
    log_path = write_work_log(data, product, args, concept, full_name, payload, out)
    print(f"작업 기록: {log_path.relative_to(ROOT)}")
    meta_file = OUT_DIR / "result_meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta["log_md"] = str(log_path)
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.upload:
        from uploader import upload_from_result
        print("5) YouTube 업로드")
        url = upload_from_result(out, OUT_DIR / "result_text.txt", args.privacy, args.link)
        print(f"업로드 완료: {url}")


if __name__ == "__main__":
    main()
