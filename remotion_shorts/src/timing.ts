import { ShortsData } from "./types";

export const FPS = 30;
export const WIDTH = 1080;
export const HEIGHT = 1920;

export type SentenceTiming = {
  text: string;
  start: number; // 영상 기준 시작 프레임
  frames: number; // 이 문장의 실제 오디오 길이(프레임) = 컷/자막이 유지되는 길이
};

/** 문장별 실제 TTS 오디오 길이(초)를 누적해 프레임으로 바꾼다. 누적값을 반올림해서 오차가 쌓이지 않는다.
 *  컷(이미지/비디오)과 자막은 모두 이 구간을 그대로 쓰므로 음성과 1:1로 맞는다. */
export const buildTimings = (
  data: ShortsData,
): { timings: SentenceTiming[]; narrationFrames: number; total: number } => {
  let acc = 0;
  const timings = data.sentences.map((s) => {
    const start = Math.round(acc * FPS);
    acc += s.duration;
    const frames = Math.max(1, Math.round(acc * FPS) - start);
    return { text: s.text, start, frames };
  });
  const narrationFrames = Math.round(acc * FPS);
  return { timings, narrationFrames, total: narrationFrames + Math.round(data.tail * FPS) };
};
