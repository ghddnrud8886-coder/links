export type ShortsData = {
  /** 상단 훅 타이틀 */
  title: string;
  /** 자막에서 네온 옐로우로 강조할 키워드 */
  keywords: string[];
  /** 상품 이미지: public/ 안의 파일명 또는 http(s) URL. 문장 수보다 적으면 순환 사용 */
  images: string[];
  /** 문장별 대본 + TTS 재생 시간(초) */
  sentences: { text: string; duration: number; words?: { text: string; start: number; end: number }[] }[];
  /** TTS 음성(public/ 파일명). 문장들을 순서대로 이어붙인 파일. 빈 문자열이면 무음 */
  voice: string;
  /** BGM(public/ 파일명). 없으면 null */
  bgm: string | null;
  /** 시연 비디오(public/ 파일명). 있으면 이미지 카드 대신 메인 영역에 재생 */
  video?: string | null;
  /** 시연 비디오 메타(가로/세로 px, 길이 초): 레이아웃과 루프 판단용 */
  /** 비디오 앞부분 로고/흰 화면을 건너뛸 초 (기본 2) */
  videoSkip?: number;
  videoInfo?: { width: number; height: number; duration: number } | null;
  /** 상황 컷용 b-roll 영상(public/ 파일명들). 상품 영상이 없을 때 훅/팁 컷에 쓴다 */
  broll?: string[];
  /** broll[0] 이 마멋선생 영상(훅 컷)이면 true: 그 컷 동안 우하단 2D 마멋을 숨긴다 */
  /** true 면 상품 이미지를 확대·크롭·모션 없이 원본 그대로(contain) 보여준다 (변형 금지 이미지/스크린샷용) */
  plainImages?: boolean;
  heroFirst?: boolean;
  /** 마멋 훅 영상을 이 초부터 재생(앞부분 정지 구간 건너뛰기) */
  heroTrim?: number;
  /** 영상 안에 작게 넣는 대가성(제휴) 문구 */
  disclosure?: string;
  /** 추가 면책 문구(브랜드 허락 조건 등). 대가성 문구 아래 두 번째 줄로 표시 */
  notice?: string;
  /** 마멋선생 캐릭터(public/ 파일명, 투명 PNG). 없으면 null */
  marmot?: string | null;
  /** 문장별 마멋 표정 이미지(public/ 파일명, 문장 수와 같은 길이). 있으면 marmot 대신 문장마다 교체 */
  marmotExpressions?: string[] | null;
  /** 상단 뱃지 문구 (콘셉트별: 마멋의 캠핑 꿀템 등) */
  badge?: string;
  /** 상단 문구를 3초 이후 교체할 상품 핵심 솔루션 요약 */
  headline?: string;
  /** 실험: true 면 비디오 컷을 화면 전체(풀블리드)로 채우고 첫 프레임부터 또렷하게 시작한다 */
  fullBleed?: boolean;
  /** 마지막 문장 이후 여운(초) */
  tail: number;
};
