"""마멋선생 콘셉트: 상품 종류에 따라 상단 뱃지/훅 각도/상황 묘사를 바꾼다. 마멋 캐릭터와 찐친 말투는 모든 콘셉트에서 공통.

classify(상품명) -> (콘셉트 dict, 키워드로 분류됐는지). 어디에도 안 맞으면 기본 콘셉트(귀차니스트 꿀템)를 쓴다.
"""
import re

BADGE = "쇼핑천재 마멋선생의 꿀템 추천"      # 상단 뱃지: 모든 콘셉트 공통

CONCEPTS = [
    {
        "key": "camp",
        "hook_rule": "공감 질문('~해본 적 있지?') 또는 호기심형. '귀찮'이라는 단어는 쓰지 않는다.",
        "broll": ["camping tent night", "campfire outdoor", "hiking nature backpack"],
        "name": "캠핑·야외",
        "badge": BADGE,
        "keywords": ["캠핑", "텐트", "침낭", "랜턴", "야외", "낚시", "등산", "아웃도어", "아이스박스", "바베큐", "차박"],
        "situation": "캠핑장 야외에서 겪는 불편 (더위/벌레/어둠/짐 많음/설치 귀찮음)",
        "hooks": ["캠핑 가서 밤에 텐트 안이 찜통인 거 겪어봤지?", "야외에서 짐 챙기다 지치는 거 은근 귀찮지?"],
    },
    {
        "key": "sport",
        "hook_rule": "공감 질문 또는 호기심형. '귀찮'이라는 단어는 쓰지 않는다.",
        "broll": ["cycling road bike", "running outdoor jogging", "gym workout"],
        "name": "운동·자전거",
        "badge": BADGE,
        "keywords": ["자전거", "사이클", "러닝", "달리기", "헬스", "요가", "선글라스", "펌프", "골프", "스포츠", "수영", "등산", "라이딩", "타이어"],
        "situation": "운동/라이딩 중이나 전후에 겪는 불편 (햇빛/땀/장비 챙기기/바람 빠진 타이어)",
        "hooks": ["자전거 타다 햇빛에 눈 부셔서 인상 쓴 적 있지?", "운동 나가려는데 장비 챙기기부터 귀찮은 사람?"],
    },
    {
        "key": "hobby",
        "hook_rule": "취향·감성을 건드리는 호기심형이나 반전형 (예: '이 모양 패드 아직도 있었어?' '옛날 게임 감성 그대로인 건 이거 하나뿐'). 불편 공감 질문이나 '귀찮'이라는 단어는 쓰지 않는다.",
        "broll": ["playing video game controller", "gamer playing console sofa", "arcade game"],
        "name": "취미·덕질",
        "badge": BADGE,
        "keywords": ["게임", "게임패드", "콘솔", "레트로", "컨트롤러", "조이스틱", "닌텐도", "8bitdo", "sega", "세가", "피규어", "무드등", "플라즈마", "램프", "프로젝터", "레고", "키링", "인형", "수집"],
        "situation": "취미/덕질을 즐기는 순간 (갖고 싶은 마음/인테리어 분위기/혼자 노는 시간)",
        "hooks": ["퇴근하고 소파에서 옛날 게임 하고 싶은 날 있지?", "방 분위기 바꾸고 싶은데 뭘 살지 고민되지?"],
    },
    {
        "key": "desk",
        "hook_rule": "공감 질문 또는 호기심형. '귀찮'이라는 단어는 쓰지 않는다.",
        "broll": ["working laptop desk", "typing keyboard desk", "home office workspace"],
        "name": "책상·방송",
        "badge": BADGE,
        "keywords": ["태블릿", "갤럭시탭", "아이패드", "마이크", "거치대", "마우스", "키보드", "데스크", "책상", "모니터", "웹캠", "스피커", "이어폰", "헤드폰", "USB", "허브", "스트리밍", "재택", "사무실"],
        "situation": "책상에서 일하거나 방송/회의할 때 겪는 불편 (목소리 작음/선 엉킴/자세/소음)",
        "hooks": ["화상회의 때 내 목소리만 작게 들린 적 있지?", "책상 위 선 엉킨 거 볼 때마다 한숨 나오지?"],
    },
    {
        "key": "lazy",
        "hook_rule": "매일 겪는 불편이나 궁금한 점을 짚는 질문 ('~하기 귀찮지?'도 허용하지만 매번 쓰지는 않는다).",
        "broll": ["man shaving mirror", "brushing teeth bathroom", "vacuum cleaner home cleaning", "kitchen cooking home", "relaxing sofa home"],
        "name": "생활 꿀템",
        "badge": BADGE,
        "keywords": ["청소기", "청소", "면도기", "트리머", "구강세정기", "플로서", "칫솔", "충전기", "주방", "자동", "믹서", "진공", "욕실", "정리", "커피", "선풍기", "세척", "건조", "차량"],
        "situation": "집이나 차에서 매일 반복되는 귀찮은 집안일/준비 과정",
        "hooks": ["아침에 피곤해 죽겠는데 거울 보면서 조심조심 수염 깎기 귀찮지 않냐?", "퇴근하고 청소기 꺼내기도 귀찮아서 미루는 사람?"],
    },
]
DEFAULT = CONCEPTS[-1]      # 귀차니스트: 마멋의 기본 정체성


def _hit(kw: str, low: str, nospace: str) -> bool:
    k = kw.lower().replace(" ", "")
    if k.isascii() and k.isalnum():           # 영문 약어는 단어 경계로
        return re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", low) is not None
    return k in nospace


def classify(name: str) -> tuple[dict, bool]:
    """키워드가 가장 많이 맞는 콘셉트. 동점이면 CONCEPTS 순서(구체적인 콘셉트 우선)."""
    low = name.lower()
    nospace = low.replace(" ", "")
    best, best_n = None, 0
    for c in CONCEPTS:
        n = sum(_hit(k, low, nospace) for k in c["keywords"])
        if n > best_n:
            best, best_n = c, n
    return (best, True) if best else (DEFAULT, False)


# ───── b-roll 세분: 콘셉트 안에서 상품 유형별 하위 폴더(assets/broll/<콘셉트>/<유형>/) ─────
# 첫 항목이 기본 유형. 키워드는 상품명(소문자, 공백 제거)에 포함되는지로 센다.
SUBTYPES = {
    "lazy": {
        "home": [],
        "bath": ["면도", "드라이어", "헤어", "욕실", "샤워", "트리머", "코털", "거울", "바디"],
        "oral": ["칫솔", "구강", "가글", "치약", "치실", "플로서", "양치", "입냄새", "세정"],
        "kitchen": ["커피", "주방", "믹서", "진공", "포장", "스케일", "요리", "조리", "에어프라이어", "포트", "텀블러", "냉장", "저울", "그라인더", "밀폐"],
        "phone": ["충전", "배터리", "케이블", "어댑터", "보조", "mah", "gan", "usb-c", "usbc", "폰"],
        "clean": ["청소", "먼지", "로봇", "빨래", "세탁", "걸레", "건조", "스팀", "다리미", "진공청소"],
    },
    "desk": {
        "typing": [],
        "stream": ["마이크", "웹캠", "조명", "링라이트", "방송", "스트리밍", "팟캐스트", "헤드셋", "녹음", "캡처"],
        "setup": ["모니터", "데스크", "허브", "책상", "스탠드", "거치대", "램프", "도킹", "선풍기", "정리"],
    },
    "camp": {
        "tent": [],
        "fire": ["화로", "불멍", "버너", "토치", "가스", "장작", "랜턴", "라이터"],
        "cook": ["조리", "식기", "쿠커", "코펠", "주전자", "그릴", "바베큐", "냄비", "아이스박스", "컵"],
        "car": ["차박", "차량", "트렁크", "카"],
        "hike": ["등산", "트레킹", "배낭", "스틱", "신발", "백팩"],
    },
    "sport": {
        "gym": [],
        "bike": ["자전거", "사이클", "타이어", "펌프", "라이딩", "헬멧", "bike", "팽창기"],
        "run": ["러닝", "달리기", "조깅", "골전도", "워치", "밴드", "수영"],
    },
    "hobby": {
        "game": [],
        "neon": ["무드등", "네온", "램프", "플라즈마", "오락", "조명", "피규어", "키링"],
        "setup": ["프로젝터", "키보드", "마우스", "모니터", "스피커"],
    },
}


def classify_sub(name: str, concept_key: str) -> str:
    """상품명에 키워드가 가장 많이 맞는 하위 유형 (동점/없음이면 콘셉트의 기본 유형)."""
    subs = SUBTYPES.get(concept_key, {})
    if not subs:
        return ""
    nospace = name.lower().replace(" ", "")
    best, best_n = next(iter(subs)), 0
    for sub, kws in subs.items():
        n = sum(k.replace(" ", "") in nospace for k in kws)
        if n > best_n:
            best, best_n = sub, n
    return best
