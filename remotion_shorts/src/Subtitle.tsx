import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const NEON = "#FFF01F";
const FONT = "'Pretendard', 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif";
const PUNCT = /[,."“”'‘’()]/g;
const ONE_LINE_MAX = 14; // 이 글자 수 이하면 한 줄, 넘으면 어절 기준으로 두 줄
const LINE_WIDTH = 930; // 자막이 쓸 가로 폭(px)

export type SubWord = { text: string; start: number; end: number }; // 초, 문장 시작 기준

/** 키워드가 차지하는 글자 위치 */
const highlightMask = (text: string, keywords: string[]) => {
  const mask: boolean[] = new Array(text.length).fill(false);
  for (const k of keywords) {
    let i = text.indexOf(k);
    while (i !== -1) {
      for (let j = i; j < i + k.length; j++) mask[j] = true;
      i = text.indexOf(k, i + k.length);
    }
  }
  return mask;
};

/** 어절 배열을 한 줄 또는 길이가 가장 고른 두 줄로 나눈다 (줄 인덱스 배열을 돌려줌) */
const splitLines = (tokens: string[]): number[][] => {
  const len = (a: number, b: number) => tokens.slice(a, b).join(" ").length;
  if (tokens.length < 2 || len(0, tokens.length) <= ONE_LINE_MAX) return [tokens.map((_, i) => i)];
  let best = 1;
  let bestMax = Infinity;
  for (let k = 1; k < tokens.length; k++) {
    const m = Math.max(len(0, k), len(k, tokens.length));
    if (m < bestMax) {
      bestMax = m;
      best = k;
    }
  }
  const idx = tokens.map((_, i) => i);
  return [idx.slice(0, best), idx.slice(best)];
};

/**
 * 쇼츠 표준 자막: 한 문장이 말해지는 동안 문장 전체(최대 2줄)를 그대로 고정해서 보여준다.
 * 텍스트는 절대 바뀌지 않고, 아직 말하지 않은 단어만 흐리게 보였다가 발화 시점에 또렷해지며 통통 튄다(노래방+팝업 방식).
 * 키워드는 항상 네온 옐로우.
 */
export const SentenceSubtitle: React.FC<{
  sentence: string;
  keywords: string[];
  words?: SubWord[];
}> = ({ sentence, keywords, words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const tokens = sentence.replace(PUNCT, " ").split(/\s+/).filter(Boolean);
  const mask = highlightMask(sentence, keywords);
  let cursor = 0;
  const hit = tokens.map((w) => {
    const idx = sentence.indexOf(w, cursor);
    if (idx !== -1) cursor = idx + w.length;
    return idx !== -1 && mask.slice(idx, idx + w.length).some(Boolean);
  });

  const lines = splitLines(tokens);
  const maxLine = Math.max(...lines.map((l) => l.map((i) => tokens[i]).join(" ").length));
  const size = Math.max(46, Math.min(80, Math.floor(LINE_WIDTH / (maxLine * 0.98))));
  const timed = words && words.length === tokens.length ? words : null;

  const enter = spring({ frame, fps, config: { damping: 16, stiffness: 180, mass: 0.7 } });

  return (
    <div
      style={{
        position: "absolute", left: 0, right: 0, top: 1450, height: 190,   // 하단 UI(채널명/구독/제목) 안전지대: 블록 하단이 화면 아래에서 280px
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        gap: size * 0.12, opacity: Math.min(1, enter * 1.6),
        transform: `translateY(${(1 - enter) * 24}px)`,
      }}
    >
      {lines.map((line, li) => (
        <div key={li} style={{ display: "flex", gap: size * 0.28, whiteSpace: "nowrap" }}>
          {line.map((i) => {
            // 단어가 발화되는 순간 통통 튀며 등장(오버슈트), 키워드는 더 크게 튀고 확대된 채 유지
            const pop = timed
              ? spring({ frame: frame - Math.round(timed[i].start * fps), fps, config: { damping: 8, stiffness: 300, mass: 0.5 } })
              : 1;
            const started = !timed || t >= timed[i].start - 0.06;
            // scale 은 레이아웃을 밀어내지 않으므로 키워드는 최대 1.12배로 제한하고 좌우 여백(margin)으로 이웃 단어와 겹치지 않게 한다
            const scale = started ? (hit[i] ? 1.0 + 0.12 * Math.min(1.2, pop) : 0.9 + 0.1 * pop) : 0.94;
            const on = timed ? interpolate(t, [timed[i].start - 0.06, timed[i].start + 0.04], [0.42, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
            return (
              <span
                key={i}
                style={{
                  fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.15, letterSpacing: -size * 0.02,
                  color: hit[i] ? NEON : "#fff", opacity: on,
                  display: "inline-block", margin: hit[i] ? `0 ${size * 0.1}px` : 0, transform: `scale(${scale}) translateY(${started ? (1 - Math.min(1, pop)) * 10 : 0}px)`,
                  transformOrigin: "50% 80%",
                  WebkitTextStroke: `${Math.round(size * 0.13)}px #000`, paintOrder: "stroke fill",
                  textShadow: hit[i] ? `0 0 ${size * 0.35}px ${NEON}99, 0 8px 14px rgba(0,0,0,0.6)` : "0 8px 14px rgba(0,0,0,0.6)",
                }}
              >
                {tokens[i]}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
};
