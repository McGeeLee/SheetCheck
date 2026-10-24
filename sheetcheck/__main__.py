"""Reproducible JSON inspection and explicitly requested safe XLSX reports."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
import json
import math
import os
from pathlib import Path
import sys

from . import FileSpec, Mapping, Rules, Side, read_source, reconcile, validate
from .errors import SheetCheckError
from .models import APP_VERSION


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error embeds offending values and paths. Help is
        # still available, but diagnostic stderr must not echo user input.
        self.exit(2, "CLI_ARGUMENTS: 参数无效或缺失；请运行 python -m sheetcheck --help 检查参数格式。\n")


def result_to_dict(result):
    """Mapped values only: unrelated source columns/formulas never leave the core."""
    return {"manifest": asdict(result.manifest), "records": [asdict(r) for r in result.records],
            "blocked_ids": result.blocked_ids,
            "ledger": [{"source_id": e.source_id, "side": e.row.source.side,
                        "source_position": asdict(e.row.source.position), "status": e.status,
                        "result_id": e.result_id, "id_raw": _json_raw(e.row.id_raw), "amount_raw": _json_raw(e.row.amount_raw),
                        "raw_types": e.row.raw_types, "normalized_id": e.row.normalized_id,
                        "amount_minor": e.row.amount_minor, "problem_codes": e.problem_codes,
                        "normalization_notes": e.row.normalization_notes} for e in result.ledger]}


def _json_raw(value):
    # JSON has no NaN/Infinity. Preserve the library-read value as a tagged
    # representation without pretending it was the source's lexical string.
    if isinstance(value, float) and not math.isfinite(value):
        return {"type": "nonfinite_number", "read_value": str(value)}
    return value


def _json_default(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    raise TypeError("Unsupported serialization type")


def _write_report(directory: Path, filename: str, data: bytes) -> None:
    """Save already audited bytes without replacing any existing filesystem entry."""
    if not directory.is_dir() or Path(filename).name != filename:
        raise OSError("Invalid report destination")
    destination = directory / filename
    # Exclusive creation also refuses existing symlinks. Remember our own inode
    # so cleanup never removes a pre-existing or concurrently replaced file.
    created_identity = None
    try:
        with destination.open("xb") as stream:
            stat = os.fstat(stream.fileno())
            created_identity = (stat.st_dev, stat.st_ino)
            if stream.write(data) != len(data):
                raise OSError("Incomplete report write")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created_identity is not None:
            try:
                stat = destination.lstat()
                if (stat.st_dev, stat.st_ino) == created_identity:
                    destination.unlink()
            except OSError:
                pass
        raise


def main(argv=None) -> int:
    parser = _SafeArgumentParser(description="SheetCheck: 本机一对一核对内核，JSON 审计输出与安全 Excel 报告。")
    parser.add_argument("--demo", action="store_true", help="使用随附虚构样例和明确样例规则")
    parser.add_argument("--export-dir", type=Path, help="明确保存 Excel 报告到已存在的目录；不覆盖已有文件，默认不写入")
    parser.add_argument("--currency", default="CNY")
    parser.add_argument("--period", default="")
    parser.add_argument("--confirm-same-currency", action="store_true")
    parser.add_argument("--confirm-same-period", action="store_true")
    for side in ("order", "payment"):
        parser.add_argument(f"--{side}-file", type=Path)
        parser.add_argument(f"--{side}-sheet")
        parser.add_argument(f"--{side}-header", type=int, default=1)
        parser.add_argument(f"--{side}-id", type=int, default=1)
        parser.add_argument(f"--{side}-amount", type=int, default=2)
        parser.add_argument(f"--{side}-encoding", default="utf-8-sig", choices=("utf-8", "utf-8-sig", "gb18030"))
        parser.add_argument(f"--{side}-delimiter", default="comma", choices=("comma", "tab", "semicolon"))
    args = parser.parse_args(argv)
    if args.demo:
        if args.order_file or args.payment_file:
            parser.error("--demo 不能与用户输入文件组合。")
        sample_root = Path(__file__).resolve().parent.parent / "samples"
        args.order_file, args.payment_file = sample_root / "orders.csv", sample_root / "payments.csv"
        rules = Rules(period="synthetic", same_currency_confirmed=True, same_period_confirmed=True)
    else:
        if not args.order_file or not args.payment_file:
            parser.error("请指定两份文件，或使用 --demo。")
        rules = Rules(args.currency, args.period, args.confirm_same_currency, args.confirm_same_period)
    try:
        if args.export_dir is not None and not args.export_dir.is_dir():
            raise OSError("Report destination must already be a directory")
        tables = []
        for side in Side:
            prefix = str(side)
            path = getattr(args, f"{prefix}_file")
            spec = FileSpec(path.name, side, sheet=getattr(args, f"{prefix}_sheet"),
                            header_row=getattr(args, f"{prefix}_header"), encoding=getattr(args, f"{prefix}_encoding"),
                            delimiter={"comma": ",", "tab": "\t", "semicolon": ";"}[getattr(args, f"{prefix}_delimiter")])
            # Bound disk reads too; core API itself accepts only bytes.
            with path.open("rb") as stream:
                data = stream.read(spec.limits.max_file_bytes + 1)
            source = read_source(data, spec)
            tables.append(validate(source, Mapping(getattr(args, f"{prefix}_id"), getattr(args, f"{prefix}_amount")), rules))
        result = reconcile(*tables, rules)
        output = json.dumps(result_to_dict(result), ensure_ascii=True, indent=2, default=_json_default, allow_nan=False)
        if args.export_dir is not None:
            from .report import export_xlsx, report_filename

            # The exporter completes its readback audit before any bytes reach
            # disk. Print no success JSON if export, audit, or saving fails.
            data = export_xlsx(result)
            filename = report_filename(result)
            _write_report(args.export_dir, filename, data)
            print(f"code=EXPORTED stage=EXPORT version={APP_VERSION}", file=sys.stderr)
        print(output)  # only after all requested operations succeed
        return 0
    except SheetCheckError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 2
    except OSError:
        print("FILE_IO: 文件无法读取或报告无法保存；请检查已有目录、文件重名和访问权限。", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("CANCELLED: 已取消，本次未产生成功结果。", file=sys.stderr)
        return 130
    except Exception:
        # Dependencies and serialization may raise exceptions containing raw
        # values. Do not let Python print their traceback to the terminal.
        print("INTERNAL_ERROR: 本次操作未完成，未产生成功结果；请重试或从可信来源重新导出普通值表。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
