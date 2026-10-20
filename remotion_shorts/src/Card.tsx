import React from "react";
import { Img, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CARD, CROSSFADE, MAIN_H, MAIN_TOP, resolve } from "./layout";

/** 컷마다 달라지는 Ken Burns 동작: 줌인 / 왼쪽으로 팬하며 줌인 / 줌아웃 / 오른쪽으로 팬 */
const KEN_BURNS = [
  { s0: 1.0, s1: 1.12, x0: 0, x1: 0, y0: 0, y1: -1.5 },
  { s0: 1.06, s1: 1.14, x0: 3, x1: -3, y0: 0, y1: 0 },
  { s0: 1.14, s1: 1.02, x0: 0, x1: 0, y0: 1.5, y1: 0 },
  { s0: 1.08, s1: 1.1, x0: -3, x1: 3, y0: -1, y1: 1 },
];

/**
 * 상품 이미지 카드. 카드 틀은 고정(등장할 때만 살짝 튀어오름)하고 안쪽 사진이 Ken Burns 로 천천히 움직인다.
 * 한 컷에 이미지가 여러 장이면(srcs) 컷 길이를 균등하게 나눠 차례로 보여준다.
 * 다음 컷은 CROSSFADE 프레임 동안 위에서 페이드인하므로 이미지 슬라이드쇼에서도 부드럽게 교차된다.
 */
export const ProductCard: React.FC<{
  srcs: string[];
  frames: number;
  index: number;
  crop?: boolean; // 대표 이미지 하단의 배송/프로모션 배너를 프레임 밖으로 밀어낸다
  plain?: boolean; // 원본 그대로: 크롭/확대/이동 없이 전체가 보이게 (변형 금지 이미지/스크린샷)
}> = ({ srcs, frames, index, crop, plain }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 15, stiffness: 130 } });
  const fade = interpolate(frame, [0, CROSSFADE], [0, 1], { extrapolateRight: "clamp" });
  const total = frames + CROSSFADE;
  const seg = total / srcs.length;
  return (
    <div
      style={{
        position: "absolute", left: (1080 - CARD) / 2, top: MAIN_TOP + (MAIN_H - CARD) / 2, width: CARD, height: CARD,
        opacity: fade, transform: `scale(${0.94 + 0.06 * pop})`,
        borderRadius: 56, overflow: "hidden", background: "#fff",
        boxShadow: "0 0 0 4px rgba(150,215,255,0.75), 0 0 60px rgba(120,160,255,0.8), 0 0 140px rgba(160,100,255,0.55), 0 40px 90px rgba(0,0,0,0.6)",
      }}
    >
      {srcs.map((src, k) => {
        const start = k * seg;
        const opacity = k === 0 ? 1 : interpolate(frame, [start, start + 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        if (plain) {
          return (
            // 원본 비율을 그대로 보여주고(contain), 남는 자리는 같은 이미지를 흐리게 깔아 채운다 (흰/검은 띠가 생기지 않게)
            <div key={k} style={{ position: "absolute", inset: 0, opacity, overflow: "hidden", background: "#111" }}>
              <Img src={resolve(src)} style={{ position: "absolute", inset: -40, width: "calc(100% + 80px)", height: "calc(100% + 80px)", objectFit: "cover", filter: "blur(36px) brightness(0.75)" }} />
              <Img src={resolve(src)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain" }} />
            </div>
          );
        }
        const kb = KEN_BURNS[(index + k) % KEN_BURNS.length];
        const t = Math.min(1, Math.max(0, (frame - start) / Math.max(1, seg)));
        const ease = t * t * (3 - 2 * t); // smoothstep
        const lerp = (a: number, b: number) => a + (b - a) * ease;
        const useCrop = crop && k === 0;
        const base = useCrop ? 1.15 : 1;
        return (
          <Img
            key={k}
            src={resolve(src)}
            style={{
              position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity,
              transformOrigin: useCrop ? "10% 0%" : "50% 50%",
              transform: `translate(${lerp(kb.x0, kb.x1)}%, ${lerp(kb.y0, kb.y1)}%) scale(${base * lerp(kb.s0, kb.s1)})`,
            }}
          />
        );
      })}
    </div>
  );
};
