"""
export.py — CSV export (matching your Airtable-ready format) + Airtable push.

CSV FORMAT:
Name, Company, Role, LinkedIn URL, Location
With headers. Comma-separated.
"""
import os
import pandas as pd
from loguru import logger


# Column order matching your existing Airtable workflow
CSV_COLUMNS = [
    "full_name",
    "current_company",
    "current_title",
    "linkedin_public_url",
    "location",
    "review",
]


def write_csv(profiles: list[dict], filepath: str):
    """Write profiles to a CSV matching your Airtable format."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    df = pd.DataFrame(profiles)

    # Ensure all columns exist
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Write ONLY the 5 Airtable columns with headers
    df[CSV_COLUMNS].to_csv(
        filepath,
        sep=",",
        index=False,
        header=True,
    )
    logger.info(f"  Wrote {len(df)} rows → {filepath}")

    # Also write a detailed version with all fields (for your reference)
    detailed_path = filepath.replace(".csv", "_detailed.csv")
    df.to_csv(detailed_path, sep=",", index=False)
    logger.info(f"  Detailed version → {detailed_path}")


def push_to_airtable(profiles: list[dict], airtable_config: dict):
    """
    Push to Airtable with UPSERT (dedup by LinkedIn URL).
    Uses batch_upsert so re-runs update existing records instead
    of creating duplicates.
    """
    from pyairtable import Api

    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise ValueError("Set AIRTABLE_API_KEY in .env")

    api = Api(api_key)
    table = api.table(airtable_config["base_id"], airtable_config["table_name"])
    field_map = airtable_config.get("field_map", {})
    merge_field = airtable_config.get("merge_field", "LinkedIn URL")

    records = []
    for p in profiles:
        fields = {}
        for config_key, airtable_col in field_map.items():
            val = p.get(config_key)
            if val is not None and val != "":
                fields[airtable_col] = str(val) if not isinstance(val, (int, float)) else val
        if fields:
            records.append({"fields": fields})

    # Batch upsert (10 at a time, Airtable limit)
    batch_size = 10
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        try:
            table.batch_upsert(
                batch,
                key_fields=[merge_field],
                replace=False,  # merge, don't replace
            )
            logger.info(f"  Upserted batch {i // batch_size + 1}")
        except Exception as e:
            logger.error(f"  Airtable batch {i // batch_size + 1} failed: {e}")
