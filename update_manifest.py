"""
data/ 폴더의 xlsx 파일 목록을 data/manifest.json으로 생성
GitHub Actions의 download.py 실행 후 자동으로 호출됩니다.
"""
import os, json, glob

data_dir = "data"
os.makedirs(data_dir, exist_ok=True)

files = sorted([
    os.path.basename(f)
    for f in glob.glob(os.path.join(data_dir, "*.xlsx"))
    + glob.glob(os.path.join(data_dir, "*.xls"))
])

manifest_path = os.path.join(data_dir, "manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(files, f, ensure_ascii=False, indent=2)

print(f"✅ manifest.json 업데이트: {len(files)}개 파일")
for fname in files:
    print(f"   - {fname}")
