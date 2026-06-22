from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from config import V30_SCANNER_CONTRACTS


@dataclass(frozen=True)
class ScannerContract:
    scan_type: str
    scan_family: str
    scanner_bucket: str
    pipeline_stage: str
    fields: tuple[str, ...]


class BaseScannerService:
    scan_type: ClassVar[str] = "standard"
    scan_family: ClassVar[str] = "standard"
    scanner_bucket: ClassVar[str] = "standard"
    pipeline_stage: ClassVar[str] = "standalone"

    @classmethod
    def contract(cls) -> ScannerContract:
        key = cls.scan_family if cls.scan_family in V30_SCANNER_CONTRACTS else cls.scan_type
        return ScannerContract(
            scan_type=cls.scan_type,
            scan_family=cls.scan_family,
            scanner_bucket=cls.scanner_bucket,
            pipeline_stage=cls.pipeline_stage,
            fields=tuple(V30_SCANNER_CONTRACTS.get(key, ())),
        )

    @classmethod
    def normalize_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "scan_type": cls.scan_type,
            "scan_family": cls.scan_family,
            "scanner_bucket": cls.scanner_bucket,
            "pipeline_stage": cls.pipeline_stage,
        }

    @classmethod
    def validate_contract_fields(cls, row: dict[str, Any]) -> tuple[bool, list[str]]:
        fields = cls.contract().fields
        missing = [field for field in fields if row.get(field) in (None, "")]
        return not missing, missing


class PremarketScannerService(BaseScannerService):
    scan_type = "premarket"
    scan_family = "premarket"
    scanner_bucket = "premarket"
    pipeline_stage = "premarket"


class OpenConfirmationScannerService(BaseScannerService):
    scan_type = "open-confirmation"
    scan_family = "open_confirmation"
    scanner_bucket = "open_confirmation"
    pipeline_stage = "open_confirmation"


class IntradayScannerService(BaseScannerService):
    scan_type = "intraday"
    scan_family = "intraday"
    scanner_bucket = "intraday"
    pipeline_stage = "intraday"


class SwingScannerService(BaseScannerService):
    scan_type = "swing"
    scan_family = "swing"
    scanner_bucket = "swing"
    pipeline_stage = "swing"


class GrowwScannerService(BaseScannerService):
    scan_type = "groww-intraday"
    scan_family = "groww"
    scanner_bucket = "groww"
    pipeline_stage = "groww_intraday"


class BreakoutScannerService(BaseScannerService):
    scan_type = "breakout"
    scan_family = "breakout"
    scanner_bucket = "breakout"
    pipeline_stage = "breakout"


class MomentumScannerService(BaseScannerService):
    scan_type = "momentum"
    scan_family = "momentum"
    scanner_bucket = "momentum"
    pipeline_stage = "momentum"


class ValueScannerService(BaseScannerService):
    scan_type = "value"
    scan_family = "value"
    scanner_bucket = "value"
    pipeline_stage = "value"


class DividendScannerService(BaseScannerService):
    scan_type = "dividend"
    scan_family = "dividend"
    scanner_bucket = "dividend"
    pipeline_stage = "dividend"


class LongTermScannerService(BaseScannerService):
    scan_type = "longterm"
    scan_family = "longterm"
    scanner_bucket = "longterm"
    pipeline_stage = "longterm"


SCANNER_SERVICES: dict[str, type[BaseScannerService]] = {
    "premarket": PremarketScannerService,
    "open-confirmation": OpenConfirmationScannerService,
    "open_confirmation": OpenConfirmationScannerService,
    "intraday": IntradayScannerService,
    "swing": SwingScannerService,
    "groww": GrowwScannerService,
    "groww-intraday": GrowwScannerService,
    "breakout": BreakoutScannerService,
    "momentum": MomentumScannerService,
    "value": ValueScannerService,
    "dividend": DividendScannerService,
    "longterm": LongTermScannerService,
}


def scanner_service(scan_type: str | None) -> type[BaseScannerService]:
    key = str(scan_type or "intraday").strip().lower().replace("_", "-")
    return SCANNER_SERVICES.get(key, IntradayScannerService)
