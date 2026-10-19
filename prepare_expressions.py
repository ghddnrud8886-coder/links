"""마멋선생/이미지 의 표정 원본(Gemini 생성, 검은 배경)을 투명 PNG 로 만들어 마멋선생/표정/ 에 저장한다.

    python prepare_expressions.py

- Gemini 로고(우하단 별 마크)를 지운 뒤 배경을 제거하고, 여백을 잘라 모든 표정을 같은 높이로 맞춘다.
- 배경이 순수한 검정이라 rembg 는 어두운 파란 조끼/바지를 배경으로 오인해 구멍을 낸다. 그래서 테두리와 이어진
  '어두운 영역'만 배경으로 보는 방식(연결 영역 + 가장자리 페더링)을 쓴다. (numpy, scipy 필요)
- 표정 이름은 EXPRESSIONS 의 값(파일명 끝부분)으로 연결한다. 시트(여러 표정이 한 장)는 건너뛴다.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "마멋선생" / "이미지"
DST = ROOT / "마멋선생" / "표정"

# 원본 파일명(고유 접미사) -> 표정 이름
EXPRESSIONS = {
    "nll661nll661nll6": "worried",    # 머리 긁적, 곤란
    "uciahluciahlucia": "shocked",    # 입 벌리고 놀람
    "f0vly5f0vly5f0vl": "laugh",      # 크게 웃음
    "3oyhyt3oyhyt3oyh": "think",      # 턱 괴고 생각
    "zdvfmvzdvfmvzdvf": "wink",       # 윙크, 능글
    "art2zcart2zcart2": "angry",      # 인상 쓰며 닦달
}
TARGET_H = 900
BG_MAX = 24        # 이 밝기(채널 최댓값) 이하이면서 테두리와 이어진 영역 = 배경(상한)
BG_CAP: dict[str, int] = {}   # 이미지별 배경 밝기 상한 재정의(기본 BG_MAX). 너무 높이면 어두운 귀/발톱이 지워진다
HALO = {"wink"}
HALO_FRAC = (0.11, 0.31)   # 후광 보정을 적용할 세로 범위(이미지 비율): 귀 아래부터 흰 칼라가 시작되기 전까지
HEAD_FRAC = 0.42   # 이미지 위쪽 이 비율까지를 머리(수염) 영역으로 본다
FEATHER = 3        # 경계 부드럽게 처리할 폭(px)


def cut_out(im: Image.Image, cap: int = BG_MAX, halo: bool = False) -> Image.Image:
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    mx = a.max(axis=2)
    border = np.concatenate([mx[0], mx[-1], mx[:, 0], mx[:, -1]])
    thr = int(max(14, min(cap, np.percentile(border, 98) + 5)))    # 이미지마다 배경 밝기에 맞춘다(비네팅 대응)


    def edge_connected(dark: np.ndarray) -> np.ndarray:
        lab, _ = ndimage.label(dark)
        edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        return np.isin(lab, edge[edge > 0])

    bg = edge_connected(mx <= thr)
    # 머리 영역은 수염 같은 얇은 선을 무시하고 한 번 더 판정 → 수염 사이에 갇힌 배경 조각 제거
    # (아래쪽은 어두운 발톱/발이 얇은 선으로 오인돼 지워지므로 적용하지 않는다)
    head = np.zeros_like(bg)
    head[: int(mx.shape[0] * HEAD_FRAC)] = True
    bg |= edge_connected(~ndimage.binary_opening(mx > thr, iterations=2)) & head
    alpha = np.where(bg, 0.0, 1.0)
    band = ndimage.binary_dilation(bg, iterations=FEATHER) & ~bg
    alpha[band] = np.clip((mx[band] - 6) / (thr + 6), 0.0, 1.0)      # 경계 픽셀은 밝기에 비례해 반투명
    lab2, n = ndimage.label(alpha > 0.5)                              # 본체에 비해 아주 작은 떠다니는 조각만 제거
    if n > 1:
        sizes = np.asarray(ndimage.sum(np.ones_like(mx), lab2, range(1, n + 1)))
        for i in np.where(sizes < 0.02 * sizes.max())[0]:
            alpha[lab2 == i + 1] = 0.0
    if halo:
        # 배경의 어두운 후광이 밝은 테두리에 갇혀 남는 이미지: 머리 영역은 털 색(r>b)만 남기고 구멍(눈/코)은 메운다
        rgb = np.asarray(im.convert("RGB")).astype(np.int16)
        fur = ndimage.binary_fill_holes(ndimage.binary_closing(rgb[..., 0] - rgb[..., 2] > 10, iterations=6))
        zone = np.zeros_like(fur)
        zone[int(fur.shape[0] * HALO_FRAC[0]): int(fur.shape[0] * HALO_FRAC[1])] = True
        alpha[zone & ~fur] = 0.0
    out = im.convert("RGBA")
    out.putalpha(Image.fromarray((alpha * 255).astype(np.uint8)))
    return out


def main():
    DST.mkdir(exist_ok=True)
    for key, name in EXPRESSIONS.items():
        hits = list(SRC.glob(f"*{key}*.png"))
        if not hits:
            print(f"  [건너뜀] {key} 원본 없음")
            continue
        im = Image.open(hits[0]).convert("RGB")
        w, h = im.size
        ImageDraw.Draw(im).rectangle((int(w * 0.86), int(h * 0.90), w, h), fill=(0, 0, 0))   # Gemini 로고 제거
        out = cut_out(im, BG_CAP.get(name, BG_MAX), name in HALO)
        out = out.crop(out.getchannel("A").getbbox())
        out = out.resize((round(out.width * TARGET_H / out.height), TARGET_H), Image.LANCZOS)
        out.save(DST / f"marmot_{name}.png")
        print(f"  {name}: {out.size}")


if __name__ == "__main__":
    main()
