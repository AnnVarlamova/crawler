from __future__ import annotations
#python tools/filter_similar_images.py "D:\diplom\crowler\dataset\collected\grasser" --threshold 5
import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
import imagehash


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class ImageInfo:
    path: Path
    phash: imagehash.ImageHash
    dhash: imagehash.ImageHash
    whash: imagehash.ImageHash
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


def read_image_info(path: Path) -> ImageInfo | None:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            width, height = img.size

            return ImageInfo(
                path=path,
                phash=imagehash.phash(img, hash_size=8),
                dhash=imagehash.dhash(img, hash_size=8),
                whash=imagehash.whash(img, hash_size=8),
                width=width,
                height=height,
            )
    except Exception as e:
        print(f"[WARN] Cannot read image {path}: {e}")
        return None


def is_similar(a: ImageInfo, b: ImageInfo, threshold: int) -> bool:
    """
    Чем меньше расстояние, тем похожее картинки.

    threshold:
      8-10  — очень строго, удалит почти одинаковые
      12-16 — умеренно, удалит похожие ракурсы
      18-22 — агрессивно, оставит только сильно разные
    """
    phash_dist = a.phash - b.phash
    dhash_dist = a.dhash - b.dhash
    whash_dist = a.whash - b.whash

    # Берём комбинацию, чтобы не зависеть от одного хэша.
    score = min(phash_dist, dhash_dist, whash_dist)

    return score <= threshold


def collect_images(images_dir: Path) -> list[ImageInfo]:
    result: list[ImageInfo] = []

    for path in sorted(images_dir.iterdir()):
        if not path.is_file():
            continue

        if path.suffix.lower() not in IMAGE_EXTS:
            continue

        info = read_image_info(path)
        if info:
            result.append(info)

    return result


def filter_one_images_dir(images_dir: Path, threshold: int, dry_run: bool) -> tuple[int, int]:
    images = collect_images(images_dir)

    if len(images) <= 1:
        return len(images), 0

    kept: list[ImageInfo] = []
    rejected: list[ImageInfo] = []

    for img in images:
        similar_to_index: int | None = None

        for index, kept_img in enumerate(kept):
            if is_similar(img, kept_img, threshold):
                similar_to_index = index
                break

        if similar_to_index is None:
            kept.append(img)
            continue

        current_kept = kept[similar_to_index]

        # Если новая похожая картинка крупнее, оставляем её, а старую выкидываем.
        if img.area > current_kept.area:
            rejected.append(current_kept)
            kept[similar_to_index] = img
        else:
            rejected.append(img)

    if not rejected:
        return len(kept), 0

    rejected_dir = images_dir.parent / "_rejected_similar"
    rejected_dir.mkdir(exist_ok=True)

    kept_names = {img.path.name for img in kept}
    rejected_names = {img.path.name for img in rejected}

    print(f"\n{images_dir}")
    print(f"  kept: {len(kept)}")
    print(f"  rejected: {len(rejected)}")

    for img in kept:
        print(f"    KEEP   {img.path.name}  {img.width}x{img.height}")

    for img in rejected:
        target = rejected_dir / img.path.name
        print(f"    REJECT {img.path.name} -> {target.name}")

        if not dry_run:
            shutil.move(str(img.path), str(target))

    if not dry_run:
        update_metadata(images_dir.parent / "metadata.json", kept_names, rejected_names)

    return len(kept), len(rejected)


def update_metadata(metadata_path: Path, kept_names: set[str], rejected_names: set[str]) -> None:
    if not metadata_path.exists():
        return

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] Cannot read metadata {metadata_path}: {e}")
        return

    images = data.get("images")
    if not isinstance(images, list):
        return

    new_images = []

    for item in images:
        local_path = str(item.get("local_path", ""))
        name = Path(local_path).name

        if name in rejected_names:
            continue

        new_images.append(item)

    data["images"] = new_images

    metadata_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_images_dirs(root: Path) -> list[Path]:
    if root.name == "images" and root.is_dir():
        return [root]

    return sorted(path for path in root.rglob("images") if path.is_dir())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        type=Path,
        help="Путь к папке images, папке продукта или dataset/collected/grasser",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=14,
        help="Порог похожести: 8-10 строго, 12-16 нормально, 18-22 агрессивно",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, что будет удалено, без перемещения файлов",
    )

    args = parser.parse_args()

    images_dirs = find_images_dirs(args.path)

    total_kept = 0
    total_rejected = 0

    for images_dir in images_dirs:
        kept, rejected = filter_one_images_dir(
            images_dir=images_dir,
            threshold=args.threshold,
            dry_run=args.dry_run,
        )
        total_kept += kept
        total_rejected += rejected

    print("\nDone")
    print(f"Images dirs: {len(images_dirs)}")
    print(f"Total kept: {total_kept}")
    print(f"Total rejected: {total_rejected}")


if __name__ == "__main__":
    main()