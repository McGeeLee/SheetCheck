"""Exercise actual default import limits using synthetic files, one fresh process per case.

Unlike the fast unit tests, this command allocates real 10 MiB uploads, 50,000
records and 100 MiB expanded XLSX parts. It never lowers production limits.
Every child has a wall-clock timeout; fixture construction is included in peak
RSS and excluded from read timing. It is not a product process memory cap.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import resource
import subprocess
import sys
from time import perf_counter
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sheetcheck import FileSpec, Side, read_source
from sheetcheck.errors import InputError
from sheetcheck.models import APP_VERSION, Limits
from scripts.benchmark_export import _hardware


CASES = tuple(f"{kind}_{edge}" for kind in (
    "csv_file", "csv_rows", "csv_columns", "xlsx_file", "xlsx_rows", "xlsx_columns",
    "xlsx_expanded", "xlsx_entries", "xlsx_ratio", "xlsx_depth",
) for edge in ("exact", "over"))


def _workbook(rows=1, columns=2):
    from openpyxl import Workbook
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Synthetic")
    sheet.append(["id", "amount"] + [f"note{i}" for i in range(columns - 2)])
    for index in range(rows):
        sheet.append([f"S{index:08d}", "0.00"] + ["value"] * (columns - 2))
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _parts(data):
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {item.filename: archive.read(item) for item in archive.infolist()}


def _archive(parts, extra_name=None, extra_chunks=(), extra_compression=zipfile.ZIP_DEFLATED):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
        if extra_name:
            item = zipfile.ZipInfo(extra_name)
            item.compress_type = extra_compression
            with archive.open(item, "w") as output:
                for chunk in extra_chunks:
                    output.write(chunk)
    return buffer.getvalue()


def _chunks(pattern, size):
    # Bounded fixture generation; no 100 MiB string is created at once.
    chunk = pattern * max(1, (1024 * 1024) // len(pattern))
    while size:
        used = min(size, len(chunk))
        yield chunk[:used]
        size -= used


def _xml_chunks(size):
    if size < 13:
        raise ValueError("XML size too small")
    yield b"<root>"
    rng = random.Random(20261024)
    text = bytes(rng.choice(b"abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(4083))
    item = b"<item>" + text + b"</item>"
    assert len(item) == 4096
    count, tail = divmod(size - 13, len(item))
    yield from _chunks(item, count * len(item))
    yield b"x" * tail
    yield b"</root>"


def fixture(case):
    """Return a real input plus independently specified expected outcome."""
    if case not in CASES:
        raise ValueError("unknown capacity case")
    kind, edge = case.rsplit("_", 1)
    over = edge == "over"
    limits = Limits()
    expected_rows, expected_columns = 1, 2
    measured = {}
    if kind == "csv_file":
        header = b"id,amount,note\n"
        record = b"A,0," + b"x" * 131_000 + b"\n"
        count, remainder = divmod(limits.max_file_bytes - len(header), len(record))
        data = header + record * count + b"B,0," + b"x" * (remainder - 4)
        data += b"x" if over else b""
        expected_rows, expected_columns = count + 1, 3
        expected = "FILE_SIZE_LIMIT" if over else None
    elif kind == "csv_rows":
        count = limits.max_records + int(over)
        data = b"id,amount\n" + b"A,0\n" * count
        expected_rows = count
        expected = "RECORD_LIMIT" if over else None
    elif kind == "csv_columns":
        count = limits.max_columns + int(over)
        data = b",".join([b"header"] * count) + b"\n" + b",".join([b"value"] * count) + b"\n"
        expected_columns = count
        expected = "COLUMN_LIMIT" if over else None
    elif kind == "xlsx_rows":
        count = limits.max_records + int(over)
        data = _workbook(rows=count)
        expected_rows = count
        expected = "RECORD_LIMIT" if over else None
    elif kind == "xlsx_columns":
        count = limits.max_columns + int(over)
        data = _workbook(columns=count)
        expected_columns = count
        expected = "COLUMN_LIMIT" if over else None
    else:
        parts = _parts(_workbook())
        if kind == "xlsx_file":
            name = "docProps/capacity.txt"
            empty = _archive(parts, name, [b""], zipfile.ZIP_STORED)
            size = limits.max_file_bytes - len(empty)
            data = _archive(parts, name, _chunks(b"x", size), zipfile.ZIP_STORED)
            assert len(data) == limits.max_file_bytes
            data += b"x" if over else b""
            expected = "FILE_SIZE_LIMIT" if over else None
        elif kind == "xlsx_expanded":
            size = limits.max_uncompressed_bytes - sum(map(len, parts.values())) + int(over)
            data = _archive(parts, "docProps/capacity.xml", _xml_chunks(size))
            expected = "XLSX_UNCOMPRESSED_LIMIT" if over else None
        elif kind == "xlsx_entries":
            for index in range(limits.max_zip_entries + int(over) - len(parts)):
                parts[f"docProps/entry{index:04d}.txt"] = b"synthetic"
            data = _archive(parts)
            expected = "XLSX_ZIP_ENTRY_LIMIT" if over else None
        elif kind == "xlsx_ratio":
            # Raw DEFLATE of 4400 'A' bytes is exactly 22 bytes at ZIP's default
            # level: 200:1. One more byte retains 22 compressed bytes (>200:1).
            value = b"A" * (4400 + int(over))
            compressed = zlib.compress(value, wbits=-15)
            assert len(compressed) == 22, "Recheck fixture for this zlib version"
            data = _archive(parts, "docProps/ratio.txt", [value])
            expected = "XLSX_COMPRESSION_RATIO" if over else None
        elif kind == "xlsx_depth":
            depth = 128 + int(over)
            data = _archive(parts, "docProps/depth.xml", [b"<x>" * depth + b"</x>" * depth])
            measured["constructed_xml_depth"] = depth
            expected = "XLSX_XML_DEPTH" if over else None
        else:
            raise AssertionError(kind)
    fmt = "csv" if kind.startswith("csv_") else "xlsx"
    if fmt == "xlsx":
        with zipfile.ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            measured.update(zip_entries=len(infos), total_uncompressed_bytes=sum(i.file_size for i in infos),
                            max_member_compression_ratio=max(i.file_size / max(i.compress_size, 1) for i in infos))
    measured.update(file_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    return data, FileSpec(f"synthetic_{case}.{fmt}", Side.ORDER), expected, expected_rows, expected_columns, measured


def run_case(case):
    start = perf_counter()
    data, spec, expected, rows, columns, measured = fixture(case)
    fixture_seconds = perf_counter() - start
    start = perf_counter()
    actual = None
    observed_rows = observed_columns = None
    try:
        table = read_source(data, spec)
        observed_rows, observed_columns = len(table.rows), len(table.headers)
    except InputError as error:
        actual = error.code
    except Exception as error:
        actual = f"UNEXPECTED_{type(error).__name__}"
    elapsed = perf_counter() - start
    passed = actual == expected and (actual is not None or (observed_rows, observed_columns) == (rows, columns))
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"case": case, "status": "passed" if passed else "failed", "expected_error": expected,
            "actual_error": actual, "expected_rows_if_accepted": rows,
            "expected_columns_if_accepted": columns, "observed_rows": observed_rows,
            "observed_columns": observed_columns, "fixture": measured,
            "fixture_seconds": fixture_seconds, "read_seconds": elapsed,
            "process_peak_rss_mib": peak / (1024 * 1024 if sys.platform == "darwin" else 1024),
            "pid": os.getpid()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    if args.timeout <= 0 or (args.child and not args.case):
        parser.error("A positive timeout and a case for --child are required")
    if args.child:
        print(json.dumps(run_case(args.case)))
        return
    results = []
    for case in ([args.case] if args.case else CASES):
        start = perf_counter()
        try:
            completed = subprocess.run([sys.executable, __file__, "--case", case, "--child"],
                                       capture_output=True, text=True, timeout=args.timeout, check=False)
            if completed.returncode:
                result = {"case": case, "status": "failed", "returncode": completed.returncode,
                          "stderr": completed.stderr[-4000:]}
            else:
                result = json.loads(completed.stdout)
        except subprocess.TimeoutExpired:
            result = {"case": case, "status": "timeout", "timeout_seconds": args.timeout}
        result["child_wall_seconds"] = perf_counter() - start
        results.append(result)
    output = {"measured_at_utc": datetime.now(timezone.utc).isoformat(), "app_version": APP_VERSION,
              "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
              "hardware": _hardware(), "default_limits": asdict(Limits()), "xml_depth_limit": 128,
              "case_count": len(results), "passed": sum(result["status"] == "passed" for result in results),
              "child_timeout_seconds": args.timeout, "results": results,
              "measurement": "Fresh sequential child per real-default boundary. No lowered limits. "
                             "Fixture generation is included in process peak RSS, excluded from read_seconds. "
                             "100 MiB expanded test uses a streaming-generated unselected XML part. "
                             "Each dimension is isolated; this does not prove all maxima simultaneously."}
    print(json.dumps(output, indent=2))
    if output["passed"] != output["case_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
