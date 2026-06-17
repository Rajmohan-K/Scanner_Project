import os
import pandas as pd
from datetime import datetime
from utils.logger import logger


OUTPUT_DIR = "reports/output"

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


def export_to_excel(
    data,
    filename=None
):
    """
    Export scan results to Excel
    """

    try:

        if filename is None:

            timestamp = datetime.now(
            ).strftime(
                "%Y%m%d_%H%M%S"
            )

            filename = (
                f"scan_report_{timestamp}.xlsx"
            )

        filepath = os.path.join(
            OUTPUT_DIR,
            filename
        )

        # ==========================
        # Save Excel
        # ==========================
        if isinstance(data, dict):

            with pd.ExcelWriter(filepath) as writer:
                for sheet_name, sheet_data in data.items():
                    if isinstance(sheet_data, list):
                        df = pd.DataFrame(sheet_data)
                    else:
                        df = sheet_data
                    df.to_excel(
                        writer,
                        sheet_name=str(sheet_name)[:31],
                        index=False
                    )

        else:

            if isinstance(
                data,
                list
            ):

                df = pd.DataFrame(
                    data
                )

            else:

                df = data

            df.to_excel(
                filepath,
                index=False
            )

        logger.info(
            f"Excel exported: {filepath}"
        )

        return filepath

    except Exception as e:

        logger.error(
            f"Excel export failed: {e}"
        )

        return None
