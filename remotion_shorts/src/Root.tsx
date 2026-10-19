import { Composition } from "remotion";
import { Shorts } from "./Shorts";
import { buildTimings, FPS, HEIGHT, WIDTH } from "./timing";
import data from "./data.json";
import { ShortsData } from "./types";

const typed = data as ShortsData;

export const RemotionRoot = () => (
  <Composition
    id="Shorts"
    component={Shorts}
    width={WIDTH}
    height={HEIGHT}
    fps={FPS}
    durationInFrames={buildTimings(typed).total}
    defaultProps={{ data: typed }}
    calculateMetadata={({ props }) => ({ durationInFrames: buildTimings(props.data).total })}
  />
);
