import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { FPS, buildTimings } from "./timing";
import { SentenceSubtitle } from "./Subtitle";
import { ProductCard } from "./Card";
import { CROSSFADE, FONT, MAIN_H, MAIN_SIDE, MAIN_TOP, NEON } from "./layout";
import { ShortsData } from "./types";

const PUNCT = /[,."\u201c\u201d'\u2018\u2019()]/g;

// ───────── 배경 ─────────
const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = (s: number, a: number) => Math.sin(frame / s) * a;
  return (
    <AbsoluteFill style={{ background: "linear-gradient(180deg,#18205a 0%,#231a6b 42%,#101845 100%)" }}>
      {/* 카드 뒤 스포트라이트: 어두운 영상도 배경과 구분되도록 중앙을 밝힌다 */}
      <div
        style={{
          position: "absolute", left: 0, right: 0, top: 260, height: 1300,
          background: "radial-gradient(ellipse at 50% 46%, rgba(95,120,255,0.55) 0%, rgba(120,80,255,0.28) 38%, transparent 70%)",
        }}
      />
      <div
        style={{
          position: "absolute", width: 900, height: 900, borderRadius: "50%",
          left: -300 + drift(60, 40), top: 200 + drift(80, 60),
          background: "radial-gradient(circle,rgba(140,100,255,0.45),transparent 65%)",
        }}
      />
      <div
        style={{
          position: "absolute", width: 800, height: 800, borderRadius: "50%",
          right: -280 + drift(70, 40), top: 950 + drift(90, 60),
          background: "radial-gradient(circle,rgba(40,170,255,0.30),transparent 65%)",
        }}
      />
      {/* 비네팅: 가장자리를 어둡게 눌러 중앙(영상)에 시선을 모은다 */}
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 48%, transparent 58%, rgba(3,4,16,0.6) 100%)" }} />
    </AbsoluteFill>
  );
};

// ───────── 상단 훅 타이틀 ─────────
const BOX_W = 920;
const BOX_H = 260; // 훅(2줄)과 3초 뒤 상품명(1~2줄)이 바뀌어도 박스 크기는 그대로
const TEXT_W = BOX_W - 90;

/** 글자 수에 맞춰 2줄 안에 들어오는 가장 큰 크기 (최대 96px, 최소 68px) */
const fitSize = (text: string) => {
  const n = text.replace(/\s+/g, " ").length;
  const perLine = Math.ceil(n / 2) + 1;
  return Math.max(68, Math.min(96, Math.floor(TEXT_W / (perLine * 0.95))));
};

const HookTitle: React.FC<{ title: string; headline?: string; badge?: string }> = ({ title, headline, badge }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 11, stiffness: 140 } });
  const swapAt = 3 * fps; // 3초 이후 솔루션 요약 문구로 전환
  const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
  const texts = [
    { text: title, opacity: headline ? interpolate(frame, [swapAt, swapAt + 10], [1, 0], clamp) : 1, y: 0 },
    ...(headline
      ? [{ text: headline, opacity: interpolate(frame, [swapAt + 4, swapAt + 14], [0, 1], clamp),
           y: interpolate(frame, [swapAt + 4, swapAt + 14], [22, 0], clamp) }]
      : []),
  ];
  return (
    <div style={{ position: "absolute", top: 76, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center" }}>
      {/* 채널 뱃지 */}
      <div
        style={{
          padding: "8px 26px", marginBottom: 22, borderRadius: 999, background: "rgba(14,10,60,0.85)",
          border: `3px solid ${NEON}`, color: NEON, fontFamily: FONT, fontWeight: 900, fontSize: 32,
          boxShadow: `0 0 24px ${NEON}66`, opacity: Math.min(1, pop), transform: `scale(${pop})`,
        }}
      >
        {badge || "마멋의 귀차니즘 꿀템"}
      </div>
      {/* 훅 박스: 진한 노란 배경 + 검정 Black 글씨 + 네온 외곽 글로우 */}
      <div
        style={{
          width: BOX_W, height: BOX_H, borderRadius: 44, background: NEON, display: "grid", placeItems: "center",
          border: "6px solid #fff", boxShadow: `0 0 0 5px #000, 0 0 50px ${NEON}aa, 0 24px 50px rgba(0,0,0,0.55)`,
          opacity: Math.min(1, pop), transform: `scale(${0.94 + 0.06 * pop}) translateY(${(1 - pop) * 30}px)`,
        }}
      >
        {texts.map((h, i) => (
          <div
            key={i}
            style={{
              gridArea: "1 / 1", width: TEXT_W, textAlign: "center", fontFamily: FONT, fontWeight: 900,
              fontSize: fitSize(h.text), lineHeight: 1.14, letterSpacing: -2, wordBreak: "keep-all", color: "#0b0b0b",
              opacity: h.opacity, transform: `translateY(${h.y}px)`,
            }}
          >
            {h.text}
          </div>
        ))}
      </div>
    </div>
  );
};

// ───────── 시연 비디오 (메인 영역을 꽉 채움, 길이가 짧으면 루프) ─────────
type VideoInfo = NonNullable<ShortsData["videoInfo"]>;

const Clip: React.FC<{ src: string; trim: number; fit: "cover" | "contain" }> = ({ src, trim, fit }) => (
  <OffthreadVideo
    src={staticFile(src)}
    muted
    trimBefore={trim}
    style={{ width: "100%", height: "100%", objectFit: fit, filter: "brightness(1.1) contrast(1.05)" }}
  />
);

/** 시연 비디오 컷: trim 프레임부터 재생(알리 영상 앞 로고 구간 스킵) */
const DemoVideo: React.FC<{ src: string; info?: VideoInfo | null; trim: number; frames: number; hook?: boolean }> = ({
  src, info, trim, frames, hook,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 15, stiffness: 110 } });
  const fade = interpolate(frame, [0, CROSSFADE], [0, 1], { extrapolateRight: "clamp" });
  const landscape = !!info && info.width / info.height > 1.2;
  // 컷 내내 천천히 밀고 들어가는 푸시인 + (훅 컷만) 시작 순간 확 줄어드는 펀치인, 시작 프레임 화이트 플래시
  const push = 1 + 0.06 * Math.min(1, frame / Math.max(1, frames));
  const punch = hook ? interpolate(frame, [0, 9], [1.16, 1], { extrapolateRight: "clamp" }) : 1;
  const flash = hook ? interpolate(frame, [0, 6], [0.85, 0], { extrapolateRight: "clamp" }) : 0;
  return (
    <div
      style={{
        position: "absolute", left: MAIN_SIDE, right: MAIN_SIDE, top: MAIN_TOP, height: MAIN_H,
        borderRadius: 56, overflow: "hidden", background: "#000",
        opacity: fade, transform: `scale(${0.96 + 0.04 * pop})`,
        boxShadow: "0 0 0 4px rgba(150,215,255,0.75), 0 0 60px rgba(120,160,255,0.8), 0 0 140px rgba(160,100,255,0.55), 0 40px 90px rgba(0,0,0,0.6)",
      }}
    >
      {landscape && (
        // 가로 영상은 흐린 확대본으로 영역을 채우고 원본은 폭에 맞춰 선명하게 올린다 (과도한 크롭/업스케일 방지)
        <div style={{ position: "absolute", inset: -60, filter: "blur(40px) brightness(0.55)" }}>
          <Clip src={src} trim={trim} fit="cover" />
        </div>
      )}
      <div style={{ position: "absolute", inset: 0, transform: `scale(${push * punch})`, transformOrigin: "50% 50%" }}>
        <Clip src={src} trim={trim} fit={landscape ? "contain" : "cover"} />
      </div>
      {flash > 0 && <div style={{ position: "absolute", inset: 0, background: "#fff", opacity: flash }} />}
    </div>
  );
};

type Visual =
  | { kind: "image"; src: string; crop: boolean }
  | { kind: "video"; trim: number; src?: string; info?: VideoInfo | null };

/** 컷별 화면 계획. 비디오가 있으면 첫 컷은 항상 비디오(훅: 이탈 방지) 이후 중간에 이미지 한 컷을 끼운다
 *  (6컷: 비디오 -> 비디오 -> 상품 이미지 줌인 -> 비디오 -> 비디오 -> 비디오),
 *  비디오 컷은 앞 컷에서 재생한 만큼 이어서 재생해 같은 장면이 반복되지 않게 한다. 비디오가 없으면 이미지만 순환. */
const planVisuals = (data: ShortsData, frames: number[]): (Visual | null)[] => {
  const n = frames.length;
  const imgs = data.images;
  if (!data.video && data.broll?.length) {
    // 상품 영상이 없으면: 상황 b-roll 과 상품 이미지(Ken Burns)를 번갈아 (6컷: B I I B I B)
    let bi = 0;
    let ii = 0;
    return frames.map((_, i) => {
      // 이미지 컷은 가진 이미지 수만큼만 (1장이면 1컷, 같은 사진 반복 금지): 우선순위 1번 컷 -> 4번 컷 -> 2번 컷
      const imageSlots = [1, 4, 2].slice(0, Math.min(3, imgs.length));
      const useImage = imageSlots.includes(i);
      if (useImage) {
        const crop = ii === 0;
        return { kind: "image", src: imgs[ii++ % imgs.length], crop };
      }
      return { kind: "video", trim: 0, src: data.broll![bi++ % data.broll!.length], info: null };
    });
  }
  if (!data.video) {
    return frames.map((_, i) => (imgs.length ? { kind: "image", src: imgs[i % imgs.length], crop: i === 0 } : null));
  }
  const mixBroll = !!data.broll?.length && n >= 6; // 상품 영상 + b-roll 혼합. 마멋 훅이 있으면: 마멋 영상 이미지 b-roll 영상 b-roll, 없으면: 영상 영상 이미지 b-roll 영상 b-roll
  const kinds: ("image" | "video" | "broll")[] = mixBroll
    ? frames.map((_, i) => (i === 2 ? (imgs.length ? "image" : "broll") : i === 0 && !data.heroFirst ? "video" : i === 0 || i === 3 || i === 5 ? "broll" : "video"))
    : imgs.length === 0
      ? frames.map(() => "video")
      : n >= 5
        ? frames.map((_, i) => (i === 2 ? "image" : "video"))
        : frames.map((_, i) => (i === 0 || i === n - 1 || i % 2 === 1 ? "video" : "image"));
  let brollIdx = 0;
  const skip = Math.round((data.videoSkip ?? 2) * FPS);
  const srcFrames = Math.floor((data.videoInfo?.duration ?? 0) * FPS);
  let imageIdx = 0;
  let cursor = skip;
  return kinds.map((k, i) => {
    if (k === "broll") {
      const first = brollIdx === 0 && !!data.heroFirst; // 마멋 훅 영상은 지정한 시작 지점부터
      const src = data.broll![brollIdx++ % data.broll!.length];
      return { kind: "video", trim: first ? Math.round((data.heroTrim ?? 0) * FPS) : 0, src, info: null };
    }
    if (k === "image") {
      const crop = imageIdx === 0; // 대표 이미지(하단 배송 배너)를 처음 쓸 때만 크롭
      const src = imgs[imageIdx++ % imgs.length];
      return { kind: "image", src, crop };
    }
    const need = frames[i] + CROSSFADE;
    if (srcFrames && cursor + need > srcFrames) cursor = skip; // 원본이 모자라면 처음(스킵 이후)부터 다시
    const v: Visual = { kind: "video", trim: cursor };
    cursor += need;
    return v;
  });
};

// ───────── 마멋선생 (좌측 하단 앵커) ─────────
const MARMOT_H = 300; // 원래 370px의 약 81%
const MARMOT_BOTTOM = 1452; // 발이 카드 하단(1380)과 자막(1450~) 사이. 머리/몸 윗부분이 카드 왼쪽 하단 모서리에 걸친다
const Marmot: React.FC<{ srcs: string[]; starts: number[]; narrationFrames: number; hideUntil?: number }> = (p) => {
  const frame = useCurrentFrame();
  if (frame < (p.hideUntil ?? 0)) return null; // 훅 컷에 3D 마멋 영상이 나오는 동안은 2D 마멋을 숨긴다
  return <MarmotBody {...p} />;
};

const MarmotBody: React.FC<{ srcs: string[]; starts: number[]; narrationFrames: number; hideUntil?: number }> = ({
  srcs, starts, narrationFrames, hideUntil = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 6 - hideUntil, fps, config: { damping: 12, stiffness: 110 } });
  // 문장이 시작될 때마다 한 번 통통 튀고, 말하는 동안은 가볍게 까딱인다
  let cur = 0;
  starts.forEach((st, i) => {
    if (st <= frame) cur = i;
  });
  const lastStart = starts[cur] ?? 0;
  const hop = spring({ frame: frame - lastStart, fps, config: { damping: 6, stiffness: 220, mass: 0.6 } });
  const speaking = frame < narrationFrames;
  const bob = speaking ? Math.abs(Math.sin(frame / 4.5)) * 7 : 0;
  const y = (1 - enter) * 120 - Math.sin(Math.PI * Math.min(1, hop)) * 14 - bob;
  // 표정 교체: 새 표정이 위에서 빠르게 페이드인하고 이전 표정은 아래에 깔려 있다가 사라진다
  const src = srcs[Math.min(cur, srcs.length - 1)];
  const prev = srcs[Math.max(0, Math.min(cur, srcs.length - 1) - 1)];
  const swap = interpolate(frame - lastStart, [0, 6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const layer = (file: string, opacity: number, key: string) => (
    <Img
      key={key}
      src={staticFile(file)}
      style={{ position: "absolute", left: 0, top: 0, height: MARMOT_H, opacity }}
    />
  );
  return (
    <div
      style={{
        position: "absolute", left: 8, top: MARMOT_BOTTOM - MARMOT_H, height: MARMOT_H, width: MARMOT_H * 0.72,
        opacity: Math.min(1, enter * 1.5),
        transform: `translateY(${y}px) rotate(${Math.sin(frame / 9) * (speaking ? 1.5 : 0.5)}deg)`,
        transformOrigin: "50% 100%",
        filter: "drop-shadow(0 18px 24px rgba(0,0,0,0.55))",
      }}
    >
      {prev !== src && swap < 1 ? layer(prev, 1, "prev") : null}
      {layer(src, prev !== src ? swap : 1, "cur")}
    </div>
  );
};

// ───────── 오디오 (BGM 덕킹) ─────────
const BGM_LOW = 0.1; // 나레이션 중
const BGM_HIGH = 0.35; // 여운 구간
const bgmVolume = (f: number, narrationFrames: number, total: number) => {
  const duck = interpolate(f, [narrationFrames - 6, narrationFrames + 15], [BGM_LOW, BGM_HIGH], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const fadeIn = interpolate(f, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(f, [total - 40, total], [1, 0], { extrapolateLeft: "clamp" });
  return duck * fadeIn * fadeOut;
};

// ───────── 메인 컴포지션 ─────────
export const Shorts: React.FC<{ data: ShortsData }> = ({ data }) => {
  const { timings, narrationFrames, total } = buildTimings(data);
  const frameCounts = timings.map((t, i) => (i === timings.length - 1 ? total - t.start : t.frames));
  const visuals = planVisuals(data, frameCounts);
  const marmotSrcs = data.marmotExpressions?.length ? data.marmotExpressions : data.marmot ? [data.marmot] : [];
  return (
    <AbsoluteFill>
      <Background />
      <HookTitle title={data.title} headline={data.headline} badge={data.badge} />

      {timings.map((t, i) => {
        const isLast = i === timings.length - 1;
        const frames = isLast ? total - t.start : t.frames;
        const vis = visuals[i];
        return (
          <React.Fragment key={i}>
            {vis && (
              // 다음 컷이 위에서 페이드인하는 동안 이전 컷이 깔려 있도록 CROSSFADE만큼 연장
              <Sequence from={t.start} durationInFrames={frames + (isLast ? 0 : CROSSFADE)} layout="none">
                {vis.kind === "image" ? (
                  <ProductCard src={vis.src} frames={frames} index={i} crop={vis.crop} />
                ) : (
                  <DemoVideo src={vis.src ?? (data.video as string)} info={vis.src ? vis.info : data.videoInfo} trim={vis.trim} frames={frames} hook={i === 0} />
                )}
              </Sequence>
            )}
            {/* 문장 하나가 말해지는 내내 문장 전체를 고정 표시 (단어 단위로 교체하지 않는다) */}
            <Sequence from={t.start} durationInFrames={frames} layout="none">
              <SentenceSubtitle sentence={t.text} keywords={data.keywords} words={data.sentences[i].words} />
            </Sequence>
          </React.Fragment>
        );
      })}

      {marmotSrcs.length ? (
        <Marmot
          srcs={marmotSrcs}
          starts={timings.map((t) => t.start)}
          narrationFrames={narrationFrames}
          hideUntil={data.heroFirst && timings[1] ? timings[1].start : 0}
        />
      ) : null}

      {data.disclosure ? (
        // 대가성 문구: 메인 카드 아래, 마멋 오른쪽의 빈 줄. 시청에 방해되지 않게 작고 흐리게
        <div
          style={{
            position: "absolute", left: 250, right: 40, top: 1392, height: 40, display: "flex", alignItems: "center",
            justifyContent: "flex-end", fontFamily: FONT, fontWeight: 700, fontSize: 25, color: "rgba(255,255,255,0.72)",
            textShadow: "0 2px 6px rgba(0,0,0,0.9)", letterSpacing: -0.5, textAlign: "right",
          }}
        >
          ※ {data.disclosure}
        </div>
      ) : null}

      {data.voice ? <Audio src={staticFile(data.voice)} /> : null}
      {data.bgm ? <Audio src={staticFile(data.bgm)} loop volume={(f) => bgmVolume(f, narrationFrames, total)} /> : null}
    </AbsoluteFill>
  );
};
