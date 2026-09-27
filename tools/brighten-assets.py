"""Brighten (or restore) the dsh-dafeiyu desktop pet's frame assets.

The frozen helper renders from the asset copy next to its exe
(%LOCALAPPDATA%/dsh-dafeiyu/<version>/assets/pet); the plugin ships the same
frames inside its package (used by the optional in-page overlay). Both trees are
handled, the untouched originals are kept in a sibling `pet.orig` tree, and a
per-tree state file makes the pass resumable and idempotent (an interrupted run
never double-brightens a frame).

Each frame is written to a temp file and moved into place, so a running helper
never reads a half-written image.

Usage:
    python brighten-dafeiyu.py apply [factor]
    python brighten-dafeiyu.py restore
"""
import glob
import json
import os
import shutil
import sys

from PIL import Image, ImageEnhance

PKG_PET = r"C:\Users\Administrator\.dsh\profiles\desktop\node_modules\dsh-dafeiyu\assets\pet"
LOCAL_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", r"C:\Users\Administrator\AppData\Local"),
    "dsh-dafeiyu",
)
# Every installed helper version keeps its own asset cache; cover them all so an
# upgrade to a new version directory is handled without editing this script.
TARGETS = [PKG_PET] + sorted(glob.glob(os.path.join(LOCAL_ROOT, "*", "assets", "pet")))
DEFAULT_FACTOR = 1.25
STATE_NAME = ".brighten-state.json"


def frame_paths(root):
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".webp"):
                yield os.path.join(base, name)


def state_path(backup_dir):
    return os.path.join(backup_dir, STATE_NAME)


def load_state(backup_dir, factor):
    path = state_path(backup_dir)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
        if state.get("factor") != factor:
            raise SystemExit(
                f"refusing to re-brighten {backup_dir}: it was already done at factor "
                f"{state.get('factor')} (restore first, or pass that factor)"
            )
        return state
    return {"factor": factor, "done": []}


def save_state(backup_dir, state):
    with open(state_path(backup_dir), "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def backup(root):
    dst = root + ".orig"
    if not os.path.isdir(dst):
        shutil.copytree(root, dst)
        print("backup created:", dst)
    return dst


def mean_lum(path):
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        width, height = rgba.size
        total = 0.0
        count = 0
        for y in range(0, height, 3):
            for x in range(0, width, 3):
                r, g, b, a = pixels[x, y]
                if a < 200:
                    continue
                total += 0.2126 * r + 0.7152 * g + 0.0722 * b
                count += 1
        return total / count if count else 0.0


def apply(root, factor):
    backup_dir = backup(root)
    state = load_state(backup_dir, factor)
    done = set(state.get("done", []))
    paths = list(frame_paths(root))
    processed = failed = skipped = 0
    for index, path in enumerate(paths, 1):
        relative = os.path.relpath(path, root)
        if relative in done:
            skipped += 1
            continue
        temporary = path + ".brightening"
        try:
            with Image.open(path) as image:
                rgba = image.convert("RGBA")
            ImageEnhance.Brightness(rgba).enhance(factor).save(
                temporary, format="WEBP", quality=95, method=4
            )
            os.replace(temporary, path)
            done.add(relative)
            processed += 1
        except Exception as error:  # noqa: BLE001
            failed += 1
            if os.path.exists(temporary):
                os.remove(temporary)
            print("  FAIL", relative, error)
        if index % 250 == 0:
            state["done"] = sorted(done)
            save_state(backup_dir, state)
            print(f"  {index}/{len(paths)}  ok={processed} fail={failed}")
    state["done"] = sorted(done)
    save_state(backup_dir, state)
    print(f"{root}: brightened {processed}, skipped {skipped}, failed {failed}, total {len(paths)}")


def restore(root):
    backup_dir = root + ".orig"
    if not os.path.isdir(backup_dir):
        print("no backup for", root)
        return
    shutil.copytree(backup_dir, root, dirs_exist_ok=True)
    path = state_path(backup_dir)
    if os.path.exists(path):
        os.remove(path)
    print("restored from", backup_dir)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "apply"
    factor = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_FACTOR
    targets = TARGETS + [path for path in sys.argv[3:] if os.path.isdir(path)]
    for root in targets:
        if not os.path.isdir(root):
            print("skip (missing):", root)
            continue
        if mode == "restore":
            restore(root)
            continue
        sample = os.path.join(root, "idle", "idle_001.webp")
        before = mean_lum(sample)
        apply(root, factor)
        after = mean_lum(sample)
        print(f"  idle_001 mean luminance: {before:.1f} -> {after:.1f}  (x{factor})")


if __name__ == "__main__":
    main()
