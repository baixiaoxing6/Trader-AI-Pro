#!/usr/bin/env python3
"""Build Freqtrade candles from Bybit's public daily futures trade archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from freqtrade.data.history.datahandlers.featherdatahandler import FeatherDataHandler
from freqtrade.enums import CandleType


PUBLIC_ROOT = "https://public.bybit.com/trading"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def iter_days(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def download_archive(url: str, destination: Path) -> dict[str, object]:
    """Download one gzip archive with retries and return provenance metadata."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "Trader-AI-Pro-CI/1.0"})
            with urlopen(request, timeout=120) as response, destination.open("wb") as output:
                require(response.status == 200, f"unexpected HTTP status {response.status}: {url}")
                shutil.copyfileobj(response, output, length=1024 * 1024)
            with destination.open("rb") as archive:
                require(archive.read(2) == b"\x1f\x8b", f"not a gzip archive: {url}")
            require(destination.stat().st_size > 100, f"archive is unexpectedly small: {url}")
            hasher = hashlib.sha256()
            with destination.open("rb") as archive:
                for block in iter(lambda: archive.read(1024 * 1024), b""):
                    hasher.update(block)
            digest = hasher.hexdigest()
            return {"url": url, "bytes": destination.stat().st_size, "sha256": digest}
        except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}: {last_error}")


def archive_to_minutes(path: Path) -> pd.DataFrame:
    """Aggregate a daily Bybit trade archive into one-minute OHLCV rows."""
    parts: list[pd.DataFrame] = []
    wanted = {"timestamp", "price", "size"}
    for chunk in pd.read_csv(
        path,
        compression="gzip",
        usecols=lambda column: column in wanted,
        chunksize=250_000,
    ):
        require(wanted.issubset(chunk.columns), f"unexpected Bybit archive columns: {path}")
        chunk["timestamp"] = pd.to_numeric(chunk["timestamp"], errors="coerce")
        chunk["price"] = pd.to_numeric(chunk["price"], errors="coerce")
        chunk["size"] = pd.to_numeric(chunk["size"], errors="coerce")
        chunk = chunk.dropna(subset=["timestamp", "price", "size"])
        chunk["date"] = pd.to_datetime(chunk["timestamp"], unit="s", utc=True)
        chunk = chunk.sort_values("date").set_index("date")
        parts.append(
            chunk.resample("1min").agg(
                open=("price", "first"),
                high=("price", "max"),
                low=("price", "min"),
                close=("price", "last"),
                volume=("size", "sum"),
            )
        )

    require(bool(parts), f"archive contained no trade rows: {path}")
    minutes = pd.concat(parts).sort_index()
    return minutes.groupby(level=0).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )


def complete_minutes(minutes: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    """Create a continuous minute index without inventing traded volume."""
    index = pd.date_range(start=start, end=end - timedelta(minutes=1), freq="1min", tz=UTC)
    result = minutes.reindex(index)
    result["close"] = result["close"].ffill().bfill()
    for column in ("open", "high", "low"):
        result[column] = result[column].fillna(result["close"])
    result["volume"] = result["volume"].fillna(0.0)
    require(not result.isna().any().any(), "unable to fill the requested archive window")
    return result


def resample_ohlcv(minutes: pd.DataFrame, frequency: str) -> pd.DataFrame:
    frame = minutes.resample(frequency, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    frame.index.name = "date"
    return frame.reset_index().loc[:, ["date", "open", "high", "low", "close", "volume"]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SOLUSDT")
    parser.add_argument("--pair", default="SOL/USDT:USDT")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2021, 7, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2021, 7, 8))
    parser.add_argument("--datadir", type=Path, default=Path("/freqtrade/user_data/data/bybit"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        require(args.end > args.start, "end date must be after start date")
        args.datadir.mkdir(parents=True, exist_ok=True)
        minute_parts: list[pd.DataFrame] = []
        sources: list[dict[str, object]] = []

        with tempfile.TemporaryDirectory(prefix="trader-ai-pro-bybit-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            for day in iter_days(args.start, args.end):
                filename = f"{args.symbol}{day.isoformat()}.csv.gz"
                url = f"{PUBLIC_ROOT}/{args.symbol}/{filename}"
                archive_path = temporary_path / filename
                print(f"Downloading {url}")
                sources.append(download_archive(url, archive_path))
                minute_parts.append(archive_to_minutes(archive_path))

        start_time = datetime.combine(args.start, datetime.min.time(), tzinfo=UTC)
        end_time = datetime.combine(args.end, datetime.min.time(), tzinfo=UTC)
        minutes = complete_minutes(pd.concat(minute_parts).sort_index(), start_time, end_time)

        handler = FeatherDataHandler(args.datadir)
        candles_5m = resample_ohlcv(minutes, "5min")
        candles_15m = resample_ohlcv(minutes, "15min")
        mark_1h = resample_ohlcv(minutes, "1h")
        funding_1h = mark_1h.copy()
        for column in ("open", "high", "low", "close", "volume"):
            funding_1h[column] = 0.0

        handler.ohlcv_store(args.pair, "5m", candles_5m, CandleType.FUTURES)
        handler.ohlcv_store(args.pair, "15m", candles_15m, CandleType.FUTURES)
        handler.ohlcv_store(args.pair, "1h", mark_1h, CandleType.MARK)
        handler.ohlcv_store(args.pair, "1h", funding_1h, CandleType.FUNDING_RATE)

        manifest = {
            "source": PUBLIC_ROOT,
            "symbol": args.symbol,
            "pair": args.pair,
            "start": args.start.isoformat(),
            "end_exclusive": args.end.isoformat(),
            "candles": {"5m": len(candles_5m), "15m": len(candles_15m), "1h_mark": len(mark_1h)},
            "funding_rate_assumption": 0.0,
            "archives": sources,
        }
        manifest_path = args.datadir / "public-source-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2, sort_keys=True))
    except (OSError, RuntimeError, ValueError, pd.errors.ParserError) as exc:
        print(f"BYBIT DATA PREPARATION FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
