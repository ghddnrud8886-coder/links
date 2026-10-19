import { staticFile } from "remotion";

export const NEON = "#FFF01F"; // 네온 옐로우
export const FONT = "'Pretendard', 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif";

// 시연 비디오/상품 카드가 쓰는 메인 영역: 상단 헤더 박스(~y430)와 자막(y1450~) 사이, 화면 정중앙(좌우 60px 여백)
export const CARD = 910; // 이미지 카드 크기 (메인 영역 높이와 같은 정사각형)
export const MAIN_TOP = 470;
export const MAIN_H = 910;
export const MAIN_SIDE = 60;
export const CROSSFADE = 8; // 컷 전환 크로스페이드 프레임 수

/** public/ 파일명 또는 http(s) URL */
export const resolve = (src: string) => (/^https?:\/\//.test(src) ? src : staticFile(src));
