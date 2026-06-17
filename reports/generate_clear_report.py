from pathlib import Path

import pandas as pd

from reports.excel_export import export_to_excel
from reports.report_generator import build_clear_trade_report


def main():
    source_path = Path(r"C:\Users\rajmo\OneDrive\Desktop(1)\scanner_project\reports\output\scan_report_20260416_093613.xlsx")
    df = pd.read_excel(source_path)
    records = df.to_dict(orient="records")
    clear_report = build_clear_trade_report(records)
    output_name = "clear_scan_report_20260416_093613.xlsx"
    export_to_excel(
        {
            "Full_Scan": df,
            **clear_report,
        },
        filename=output_name,
    )
    print(output_name)


if __name__ == "__main__":
    main()
