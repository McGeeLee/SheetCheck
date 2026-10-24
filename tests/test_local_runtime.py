"""Core runtime must not depend on filesystem writes or network access."""
import builtins
from pathlib import Path
import socket

import pytest

from sheetcheck import FileSpec, Mapping, Rules, Side, read_source, reconcile, validate


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_processing_preloaded_bytes_needs_no_paths_or_network(monkeypatch, extension):
    root = Path(__file__).resolve().parents[1] / "samples"
    blobs = [(root / f"{name}.{extension}").read_bytes() for name in ("orders", "payments")]
    def forbidden(*args, **kwargs):
        raise AssertionError("Core attempted filesystem/network access")
    with monkeypatch.context() as scope:
        scope.setattr(builtins, "open", forbidden)
        scope.setattr(Path, "open", forbidden)
        scope.setattr(socket, "socket", forbidden)
        scope.setattr(socket, "create_connection", forbidden)
        rules = Rules(period="synthetic", same_currency_confirmed=True, same_period_confirmed=True)
        tables = [validate(read_source(blob, FileSpec(f"sample.{extension}", side)), Mapping(1, 2), rules)
                  for blob, side in zip(blobs, Side)]
        result = reconcile(*tables, rules)
    assert len(result.ledger) == 14
