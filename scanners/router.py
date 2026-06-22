from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScannerProfile:
    mode: str
    family: str
    bucket: str
    stage: str
    display_name: str
    default_top_n: int
    default_candidate_pool: int
    default_validation_pool: int
    allowed_sources: tuple[str, ...]


def normalize_scan_mode(scan_mode: str | None) -> str:
    mode = str(scan_mode or "standard").strip().lower().replace("_", "-")
    return mode or "standard"


def scanner_profile(scan_mode: str | None, pipeline_stage: str | None = None) -> ScannerProfile:
    mode = normalize_scan_mode(scan_mode)
    stage_hint = normalize_scan_mode(pipeline_stage)

    if "open-confirmation" in mode or "market-open" in mode or stage_hint == "open-confirmation":
        return ScannerProfile(
            mode="open-confirmation",
            family="open_confirmation",
            bucket="open_confirmation",
            stage="open_confirmation",
            display_name="9:08 Open Confirmation Scanner",
            default_top_n=10,
            default_candidate_pool=25,
            default_validation_pool=0,
            allowed_sources=("premarket",),
        )

    if "premarket" in mode:
        return ScannerProfile(
            mode="premarket",
            family="premarket",
            bucket="premarket",
            stage="premarket",
            display_name="Premarket Scanner",
            default_top_n=25,
            default_candidate_pool=150,
            default_validation_pool=0,
            allowed_sources=("market", "groww"),
        )

    if "intraday" in mode or "groww" in mode:
        return ScannerProfile(
            mode="intraday" if "groww" not in mode else "groww-intraday",
            family="intraday",
            bucket="intraday",
            stage="intraday_elite",
            display_name="Intraday Elite Scanner",
            default_top_n=10,
            default_candidate_pool=35,
            default_validation_pool=0,
            allowed_sources=("open_confirmation", "premarket", "market", "groww", "custom"),
        )

    if "swing" in mode:
        return ScannerProfile(
            mode="swing",
            family="swing",
            bucket="swing",
            stage="swing",
            display_name="Swing Scanner",
            default_top_n=20,
            default_candidate_pool=97,
            default_validation_pool=35,
            allowed_sources=("market", "watchlist", "custom"),
        )

    if "watchlist" in mode:
        return ScannerProfile(
            mode="watchlist",
            family="watchlist",
            bucket="watchlist",
            stage="watchlist",
            display_name="Watchlist Scanner",
            default_top_n=20,
            default_candidate_pool=50,
            default_validation_pool=0,
            allowed_sources=("watchlist", "custom"),
        )

    return ScannerProfile(
        mode=mode,
        family="standard",
        bucket="standard",
        stage="standalone",
        display_name="Standard Scanner",
        default_top_n=10,
        default_candidate_pool=150,
        default_validation_pool=25,
        allowed_sources=("market", "custom"),
    )


def build_scan_metadata(scan_mode: str | None, pipeline_stage: str | None = None) -> dict[str, Any]:
    profile = scanner_profile(scan_mode, pipeline_stage)
    return {
        "scan_mode": profile.mode,
        "scan_family": profile.family,
        "scanner_bucket": profile.bucket,
        "pipeline_stage": profile.stage,
        "scanner_display_name": profile.display_name,
        "scanner_top_n": profile.default_top_n,
        "scanner_candidate_pool": profile.default_candidate_pool,
        "scanner_validation_pool": profile.default_validation_pool,
    }


def tag_record(record: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    tagged = dict(record)
    for key in ("scan_mode", "scan_family", "scanner_bucket", "pipeline_stage", "scanner_display_name"):
        tagged.setdefault(key, metadata.get(key))
    return tagged


def tag_records(records: list[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    return [tag_record(record, metadata) for record in records if isinstance(record, dict)]
