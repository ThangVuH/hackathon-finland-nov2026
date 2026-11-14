"""Summarize questions.jsonl inside the full Junction zip without extracting it."""

from __future__ import annotations

import json
import struct
import urllib.request
import zlib
from collections import Counter
from pathlib import Path

URL = "https://fwjydgxpttajiqpfmqtj.supabase.co/storage/v1/object/public/stoa-junction-2026/junction-dataset.zip"
SIZE = 9_768_952_082
UA = "junction-counting"
OUT = Path(__file__).resolve().parent / "full_questions_summary.txt"


def get_range(start: int, end: int) -> bytes:
    request = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}", "User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def zip64_directory() -> bytes:
    chunk_start = SIZE - 3_000_000
    data = get_range(chunk_start, SIZE - 1)
    locator = data.rfind(b"PK\x06\x07")
    zip64_offset = struct.unpack_from("<Q", data, locator + 8)[0]
    relative = zip64_offset - chunk_start
    cd_size = struct.unpack_from("<Q", data, relative + 40)[0]
    cd_offset = struct.unpack_from("<Q", data, relative + 48)[0]
    if chunk_start <= cd_offset:
        return data[cd_offset - chunk_start : cd_offset - chunk_start + cd_size]
    return get_range(cd_offset, cd_offset + cd_size - 1)


def find_questions(blob: bytes) -> tuple[int, int, int]:
    position = 0
    while position + 46 <= len(blob) and blob[position : position + 4] == b"PK\x01\x02":
        method = struct.unpack_from("<H", blob, position + 10)[0]
        comp, uncomp = struct.unpack_from("<II", blob, position + 20)
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", blob, position + 28)
        offset = struct.unpack_from("<I", blob, position + 42)[0]
        name = blob[position + 46 : position + 46 + name_len].decode("utf-8")
        extra = blob[position + 46 + name_len : position + 46 + name_len + extra_len]
        extra_pos = 0
        while extra_pos + 4 <= len(extra):
            header_id, size = struct.unpack_from("<HH", extra, extra_pos)
            extra_pos += 4
            payload = extra[extra_pos : extra_pos + size]
            extra_pos += size
            if header_id != 0x0001:
                continue
            cursor = 0
            if uncomp == 0xFFFFFFFF:
                uncomp = struct.unpack_from("<Q", payload, cursor)[0]
                cursor += 8
            if comp == 0xFFFFFFFF:
                comp = struct.unpack_from("<Q", payload, cursor)[0]
                cursor += 8
            if offset == 0xFFFFFFFF:
                offset = struct.unpack_from("<Q", payload, cursor)[0]
        if name.endswith("questions.jsonl"):
            return method, comp, offset
        position += 46 + name_len + extra_len + comment_len
    raise SystemExit("questions.jsonl not found")


def read_member(method: int, comp: int, offset: int) -> bytes:
    header = get_range(offset, offset + 511)
    name_len, extra_len = struct.unpack_from("<HH", header, 26)
    start = offset + 30 + name_len + extra_len
    payload = get_range(start, start + comp - 1)
    if method == 0:
        return payload
    if method == 8:
        return zlib.decompress(payload, -15)
    raise SystemExit(f"unsupported method {method}")


def main() -> None:
    method, comp, offset = find_questions(zip64_directory())
    raw = read_member(method, comp, offset)
    by_source_type = Counter()
    by_source = Counter()
    types = Counter()
    files = Counter()
    lines = 0
    for line in raw.splitlines():
        if not line:
            continue
        row = json.loads(line)
        parts = row["path"].split("/")
        source = parts[1] if len(parts) > 1 and parts[0] == "data" else parts[0]
        by_source_type[(source, row.get("type"))] += 1
        by_source[source] += 1
        types[row.get("type")] += 1
        files[source] += 0
        files[(source, row["path"])] = 1
        lines += 1
    file_counts = Counter()
    for key, value in files.items():
        if isinstance(key, tuple):
            file_counts[key[0]] += 1
    report = [f"lines {lines}"]
    report.append("types " + ", ".join(f"{name} {count}" for name, count in types.most_common()))
    report.append("files with questions")
    for source, count in file_counts.most_common():
        report.append(f"  {source:22} {count:5d} files  {by_source[source]:6d} lines")
    report.append("by source and type")
    for (source, kind), count in sorted(by_source_type.items()):
        report.append(f"  {source:22} {str(kind):8} {count:6d}")
    text = "\n".join(report) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
