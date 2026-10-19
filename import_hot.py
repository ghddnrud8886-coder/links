"""다운로드 폴더의 알리 Hot Products 엑셀/CSV 를 data/ 로 옮긴다 (이름이 겹치지 않게 날짜 붙임).

포털에서 파일을 내려받은 뒤 이것만 실행하면 된다:
    python import_hot.py
옮긴 파일은 다운로드 폴더에서 사라지므로 같은 파일이 두 번 들어가지 않는다.
상품 중복은 product_id 기준으로 ali_csv_loader 가 걸러낸다.
"""
import datetime
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DOWNLOADS = Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"
PATTERNS = ["hot_products*.xls*", "hot_products*.csv"]


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    files = sorted({p for pat in PATTERNS for p in DOWNLOADS.glob(pat) if not p.name.startswith("~$")},
                   key=lambda p: p.stat().st_mtime)
    if not files:
        print(f"[안내] {DOWNLOADS} 에 hot_products 파일이 없습니다. 포털에서 Hot Products 를 내려받으세요.")
        return 0
    stamp = datetime.date.today().strftime("%Y%m%d")
    for f in files:
        n = 1
        while (dest := DATA_DIR / f"hot_products_{stamp}_{n}{f.suffix}").exists():
            n += 1
        shutil.move(str(f), dest)
        print(f"  가져옴: {f.name} → data/{dest.name}")
    print(f"[완료] {len(files)}개 파일을 가져왔습니다.")
    return len(files)


if __name__ == "__main__":
    main()
