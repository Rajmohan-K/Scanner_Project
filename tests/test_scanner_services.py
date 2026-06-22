from scanners.services import (
    GrowwScannerService,
    IntradayScannerService,
    OpenConfirmationScannerService,
    PremarketScannerService,
    SwingScannerService,
    scanner_service,
)


def test_scanner_services_have_separate_contracts():
    services = [
        PremarketScannerService,
        OpenConfirmationScannerService,
        IntradayScannerService,
        SwingScannerService,
        GrowwScannerService,
    ]
    families = {service.contract().scan_family for service in services}
    field_sets = {service.contract().scan_family: set(service.contract().fields) for service in services}

    assert families == {"premarket", "open_confirmation", "intraday", "swing", "groww"}
    assert "gap_percent" in field_sets["premarket"]
    assert "price_at_0908" in field_sets["open_confirmation"]
    assert "vwap" in field_sets["intraday"]
    assert "holding_period" in field_sets["swing"]
    assert "resolved_symbol" in field_sets["groww"]


def test_scanner_service_lookup_normalizes_aliases():
    assert scanner_service("open-confirmation") is OpenConfirmationScannerService
    assert scanner_service("open_confirmation") is OpenConfirmationScannerService
    assert scanner_service("groww-intraday") is GrowwScannerService
