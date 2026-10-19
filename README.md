# 마멋선생 쇼츠 자동 생성기

DeepSeek 대본 → Edge-TTS 음성 → Pillow 프레임 → FFmpeg 합성으로 1080x1920 쇼츠(`output/shorts_marmot_v2.mp4`)를 만든다.

## 1. DeepSeek API 키 설정

1. https://platform.deepseek.com 에서 API 키 발급(잔액 충전 필요).
2. 프로젝트 루트의 `.env` 파일을 열어 `DEEPSEEK_API_KEY=` 뒤에 키를 붙여넣는다. 따옴표/공백 없이.
   ```
   DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
   ```
3. 실행: `python main.py --name "상품명" --features "특징1, 특징2, ..."`
   - 키가 비어 있으면 자동으로 내장 샘플 대본(오프라인 모드)으로 진행한다.
   - `.env`는 절대 공유/커밋하지 말 것.

## 2. 실행

```
python main.py --offline                      # API 없이 샘플 대본으로 테스트
python main.py --name "..." --features "..."  # 실제 AI 대본
python main.py ... --bgm path/to/bgm.mp3      # BGM 지정(기본 assets/bgm.mp3)
python main.py ... --upload --privacy private # 렌더 후 YouTube 업로드
```

## 3. 파이프라인 구조

| 파일 | 역할 |
|---|---|
| `main.py` | 대본 생성/검증, TTS, 프레임 타이밍, FFmpeg 합성 |
| `card_renderer.py` | 프레임 1장 렌더(헤드라인, 상품 카드, 자막 바, CTA), 마멋 컷아웃 전처리 |
| `마멋선생/` | 레퍼런스 영상 3편 + 캐릭터 이미지(마멋 PNG를 파이프라인이 직접 로드) |
| `output/result_text.txt` | 제목/해시태그/고정 댓글/대본 (상단 훅 제목의 출처) |
| `output/work/deepseek_response.json` | DeepSeek 원본 응답(디버깅용) |

## 4. 마멋선생 컨셉 규칙 (기록)

- **보이스**: `ko-KR-InJoonNeural`, 피치 +40Hz, 속도 +10%.
  레퍼런스 영상 음성의 피치 분포(P10/P50/P90 = 155/225/281Hz)가 InJoonNeural +40Hz 합성음과 일치해서 선택. 속도는 추정 불가라 +10%로 설정.
- **대본**: 정확히 5문장(본문 4 + 고정 CTA 1), 약 20~25초. 인사말 금지, 첫 문장은 "자네, 아직도 ~하나?" 식 팩폭 훅.
  어투는 능청스러운 반말 노신사(~라네/~보게나/~말이지). 마지막 문장은 고정: "프로필 링크 눌러라" 계열 (쇼츠 설명/댓글 링크는 클릭이 안 돼서 프로필 링크로 유도)
- **JSON 필드**: `sentences`, `title`(공백 포함 20자 이내, 초과 시 자동 절단), `keywords`(자막 노란 강조, 대본에 실제 있는 단어만 통과), `hashtags`(5개), `pinned_comment`.
- **레이아웃**: 상단 y100~335 노랑 태그 "마멋의 팩폭 추천" + 훅 제목, 중앙 840x840 둥근 상품 카드(x200,y350), 좌측 하단 마멋 380px(y1112~), 하단 자막 바 y1500~1650(한 줄 최대 13자, 84px 볼드, 키워드 노랑), 우하단 CTA 버튼.
- **모션**: 자막 한 줄 단위로 컷 전환(0.15초 페이드), 문장마다 이미지 교체, 마멋은 말하는 동안 위로 8px 까딱임(자막 바 침범 없음).
- **오디오**: BGM 12% + 끝 페이드아웃, 문장 전환마다 효과음. `assets/bgm.mp3`, `assets/whoosh.mp3`(또는 `pop.mp3`)가 없으면 안내 후 무음 처리.

## 5. API 오류 처리

- 연결 10초/응답 60초 타임아웃, 최대 3회 재시도(점증 대기).
- 응답이 ```json 펜스나 잡설로 감싸져도 JSON 객체만 추출.
- 검증 실패(문장 수 3~6 범위 밖, title 누락, sentences 형식 오류) 시 재시도.
- 401/403(키 거부), 402(잔액 부족)은 즉시 중단하고 원인 안내.
- 3회 모두 실패하면 내장 샘플 대본으로 대체해 렌더링을 계속한다.

## 6. 변경 이력 요약

1. 카드뉴스 스타일(Pillow 카드 + xfade) 도입, 출력 `shorts_card.mp4`.
2. 마멋선생 레퍼런스 분석 후 보이스/대본/밸런스게임 레이아웃 적용, 출력 `shorts_marmot.mp4`.
3. 밸런스 UI·말풍선·인사말 제거, 팩폭 추천 레이아웃으로 개편, 출력 `shorts_marmot_v2.mp4`.
4. DeepSeek 호출 견고화(재시도/파싱/검증/폴백), 제목 20자 제한.

## 7. 알려진 한계

- 마멋 PNG 컷아웃 가장자리에 잔여물이 남아 좌우를 잘라 정리했다(완전한 투명 컷아웃 아님).
- 레퍼런스의 타자기 자막 효과, 입 모양 애니메이션은 미구현.
- 상품 이미지 안에 영어 텍스트가 있으면 한글 자막과 섞여 보인다(소재 선택 문제).

## Remotion 렌더링 (card_renderer.py/Pillow 대체)

- 필요: Node.js 18+, FFmpeg(문장별 음성 길이 측정), `pip install -r requirements.txt`
- 설치: `cd remotion_shorts && npm install` (생략해도 main.py가 첫 실행 때 자동 설치)
- 실행: `python main.py [--offline] [--bgm 경로] [--image-url URL ...]` → `output/shorts_remotion.mp4`
- 흐름: 대본/TTS → 문장별 길이(초)를 `remotion_shorts/src/data.json`에 저장, 에셋은 `remotion_shorts/public/`으로 복사 → `npx remotion render`
- 디자인 수정/미리보기: `cd remotion_shorts && npm run studio` (1080x1920, 30fps)
- BGM: `assets/bgm.mp3`를 두면 나레이션 중 10%, 끝 여운 구간 35%로 자동 덕킹
