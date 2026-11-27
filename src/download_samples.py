"""Download official Ugawa Dam test photos (no API key needed)."""
from pathlib import Path
from urllib.request import Request, urlopen
import tempfile
import cv2

ROOT = Path(__file__).resolve().parents[1]
PHOTOS = {
    "before.jpg": "https://www.pref.niigata.lg.jp/uploaded/image/146468.jpg",
    "after.jpg": "https://www.pref.niigata.lg.jp/uploaded/image/153976.jpg",
}

def main():
    folder = ROOT / "data"
    folder.mkdir(exist_ok=True)
    for name, url in PHOTOS.items():
        target = folder / name
        if target.exists():
            if cv2.imread(str(target)) is None:
                raise ValueError(f"Invalid existing image: {target}; remove it and retry")
            print(f"Already exists: {target}")
            continue
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=45) as response:
            data = response.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("Image too large")
        with tempfile.NamedTemporaryFile(dir=folder, suffix=".jpg", delete=False) as f:
            temp = Path(f.name)
            f.write(data)
        try:
            if cv2.imread(str(temp)) is None:
                raise ValueError(f"Not a valid image: {url}")
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
        print(f"Downloaded: {target}")

if __name__ == "__main__":
    main()
