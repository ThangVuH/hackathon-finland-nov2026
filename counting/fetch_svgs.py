"""Download the CubiCasa5K model.svg files that match the preview plans.

The Zenodo archive is one 5.5 GB zip. Only the central directory and the
matched SVG payloads are fetched, via HTTP range requests.
"""

from __future__ import annotations

import json
import struct
import time
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ZIP_URL = "https://zenodo.org/api/records/2613548/files/cubicasa5k.zip/content"
ZIP_SIZE = 5_469_495_706
CD_OFFSET = 5_466_775_714
CD_SIZE = 2_719_894
ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT.parent / "junction-dataset-preview" / "data" / "cubicasa5k"
OUT = ROOT / "svg"
CACHE = ROOT / "cache"
UA = "junction-counting"


def get_range(start: int, end: int, timeout: int = 180) -> bytes:
    last_error = None
    for attempt in range(8):
        try:
            req = urllib.request.Request(
                ZIP_URL,
                headers={"Range": f"bytes={start}-{end}", "User-Agent": UA},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                time.sleep(2 + attempt * 3)
                continue
            time.sleep(1 + attempt)
        except Exception as exc:  # noqa: BLE001 — retry transient Zenodo errors
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"range {start}-{end} failed: {last_error}")


def preview_plans() -> list[tuple[str, str]]:
    plans = []
    for path in sorted(PREVIEW.glob("*.png")):
        style, sample_id = path.stem.rsplit("-", 1)
        plans.append((style, sample_id))
    return plans


def zip64_pair(fixed: int, sentinel: int, extra: bytes, cursor: list[int]) -> int:
    if fixed != sentinel:
        return fixed
    value = struct.unpack_from("<Q", extra, cursor[0])[0]
    cursor[0] += 8
    return value


def parse_extra(extra: bytes, comp: int, uncomp: int, offset: int) -> tuple[int, int, int]:
    """Apply the ZIP64 extra field when the 32-bit values overflowed."""
    position = 0
    while position + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, position)
        position += 4
        payload = extra[position : position + size]
        position += size
        if header_id != 0x0001:
            continue
        cursor = [0]
        uncomp = zip64_pair(uncomp, 0xFFFFFFFF, payload, cursor)
        comp = zip64_pair(comp, 0xFFFFFFFF, payload, cursor)
        offset = zip64_pair(offset, 0xFFFFFFFF, payload, cursor)
    return comp, uncomp, offset


def iter_central_directory(blob: bytes):
    position = 0
    while position + 46 <= len(blob) and blob[position : position + 4] == b"PK\x01\x02":
        method = struct.unpack_from("<H", blob, position + 10)[0]
        comp, uncomp = struct.unpack_from("<II", blob, position + 20)
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", blob, position + 28)
        offset = struct.unpack_from("<I", blob, position + 42)[0]
        name = blob[position + 46 : position + 46 + name_len].decode("utf-8")
        extra = blob[position + 46 + name_len : position + 46 + name_len + extra_len]
        comp, uncomp, offset = parse_extra(extra, comp, uncomp, offset)
        yield name, method, comp, uncomp, offset
        position += 46 + name_len + extra_len + comment_len


def load_directory() -> list[tuple[str, int, int, int, int]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "cubicasa5k_cd.bin"
    if not path.exists() or path.stat().st_size != CD_SIZE:
        path.write_bytes(get_range(CD_OFFSET, CD_OFFSET + CD_SIZE - 1))
    return list(iter_central_directory(path.read_bytes()))


def match_svgs(entries, plans: list[tuple[str, str]]):
    wanted = {f"{style}/{sample_id}/model.svg": (style, sample_id) for style, sample_id in plans}
    found = {}
    examples = []
    for name, method, comp, uncomp, offset in entries:
        normalized = name.replace("\\", "/")
        if len(examples) < 8 and normalized.endswith("model.svg"):
            examples.append(normalized)
        for suffix, key in wanted.items():
            if normalized.endswith(suffix):
                found[key] = (normalized, method, comp, uncomp, offset)
                break
    return found, examples


def extract_one(item: tuple[str, str, tuple]) -> str:
    style, sample_id, (name, method, comp, _uncomp, offset) = item
    destination = OUT / style / sample_id / "model.svg"
    if destination.exists() and destination.stat().st_size > 0:
        return f"skip {style}/{sample_id}"
    header = get_range(offset, offset + 511)
    if header[:4] != b"PK\x03\x04":
        raise RuntimeError(f"bad local header for {name}")
    name_len, extra_len = struct.unpack_from("<HH", header, 26)
    data_start = offset + 30 + name_len + extra_len
    payload = get_range(data_start, data_start + comp - 1)
    if method == 0:
        raw = payload
    elif method == 8:
        raw = zlib.decompress(payload, -15)
    else:
        raise RuntimeError(f"unsupported method {method} for {name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return f"ok {style}/{sample_id} {len(raw)}"


def main() -> None:
    plans = preview_plans()
    entries = load_directory()
    found, examples = match_svgs(entries, plans)
    missing = [f"{style}-{sample_id}" for style, sample_id in plans if (style, sample_id) not in found]
    report = {
        "plans": len(plans),
        "svg_found": len(found),
        "missing": missing,
        "example_svg_paths": examples,
    }
    (ROOT / "cache").mkdir(parents=True, exist_ok=True)
    (CACHE / "svg_match.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if missing:
        raise SystemExit("some preview plans have no model.svg")
    work = [(style, sample_id, found[(style, sample_id)]) for style, sample_id in plans]
    done = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(extract_one, item) for item in work]
        for future in as_completed(futures):
            done += 1
            message = future.result()
            if done <= 5 or done % 40 == 0 or message.startswith("ok") and done <= 3:
                print(f"[{done}/{len(work)}] {message}")
    print(f"svg files on disk: {len(list(OUT.glob('*/*/model.svg')))}")


if __name__ == "__main__":
    main()
