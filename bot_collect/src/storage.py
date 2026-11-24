import os
from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")

key_id = os.getenv("AWS_ACCESS_KEY_ID", "")
if key_id:
    secret = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    token = os.getenv("AWS_SESSION_TOKEN", "")
    raw_ep = os.getenv("AWS_S3_ENDPOINT", "minio.lab.sspcloud.fr")
    endpoint = raw_ep.replace("https://", "").replace("http://", "").strip("/")
    con.execute(f"""
        CREATE OR REPLACE SECRET s3_secret (
            TYPE S3,
            KEY_ID '{key_id}',
            SECRET '{secret}',
            SESSION_TOKEN '{token}',
            ENDPOINT '{endpoint}',
            URL_STYLE 'path',
            USE_SSL true
        );
    """)


def get_paths(day, prefix):
    bucket = os.getenv("S3_BUCKET", "gpichonlegroux")
    s3_path = f"s3://{bucket}/{prefix}/date={day}/part-0.parquet" if key_id else None
    local_path = DEFAULT_DATA_DIR / prefix / f"date={day}" / "part-0.parquet"
    return s3_path, local_path


def save_partition(rows, day, prefix, id_cols=("journey_id",)):
    if not rows:
        return

    s3_path, local_path = get_paths(day, prefix)
    new_df = pd.DataFrame(rows)

    existing_df = None
    for path in (s3_path, local_path.as_posix()):
        if not path:
            continue
        try:
            existing_df = con.sql(f"SELECT * FROM read_parquet('{path}')").df()
            break
        except Exception:
            pass

    if existing_df is not None and not existing_df.empty:
        df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        df = new_df

    df = (
        df.sort_values("last_seen")
        .drop_duplicates(subset=list(id_cols), keep="last")
        .reset_index(drop=True)
    )

    if s3_path:
        try:
            con.execute(f"COPY (SELECT * FROM df) TO '{s3_path}';")
            return
        except Exception as e:
            print(e)

    local_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM df) TO '{local_path.as_posix()}';")


def save_incidents(rows, day):
    save_partition(rows, day, prefix="incidents", id_cols=("line", "message_id"))
