import duckdb
import pandas as pd
import datetime
import json

"""
TYPE S3: Indique que le secret s'applique au protocole s3://
KEY_ID '' et SECRET '': Identifiant vide car l'accès est anonyme (public)
ENDPOINT 'minio.lab.sspcloud.fr': Redirige les requêtes du S3 officiel AWS vers le MinIO du SSP Cloud
URL_STYLE 'path': Force l'utilisation d'une structure d'URL par chemin (http://endpoint/bucket)
"""
duckdb.execute("INSTALL httpfs; LOAD httpfs;")
duckdb.execute("CREATE OR REPLACE SECRET (TYPE S3, KEY_ID '', SECRET '', ENDPOINT 'minio.lab.sspcloud.fr', URL_STYLE 'path');")

def read_data(ligne, date):
    """Lire la table de donnees d'une ligne a une date"""
    return duckdb.sql(f"SELECT * FROM 's3://gpichonlegroux/rer-{ligne}/date={date}/part-0.parquet'").df()

def read_data_ligne(ligne):
    """Lire l'integralite des donnees d'une ligne sur toutes les dates"""
    df = duckdb.sql(f"SELECT * FROM read_parquet('s3://gpichonlegroux/rer-{ligne}/date=*/*.parquet', union_by_name=true) ORDER BY date DESC").df()
    df["line"] = df["line"].fillna(f"rer_{ligne}")
    return df

def read_incidents():
    """Lire l'integralite des incidents sur toutes les dates"""
    return duckdb.sql("SELECT * FROM read_parquet('s3://gpichonlegroux/incidents/date=*/*.parquet', union_by_name=true) ORDER BY date DESC").df()

def save_data(ligne):
    """Sauvegarder un dataset localement avec la date du jour pour éviter de requeter le serveur a chaque fois"""
    df = read_data_ligne(ligne)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    file_path = f"data/rer_{ligne}_{today}.parquet"
    
    df.to_parquet(file_path, index=False)
    print(f"Données sauvegardées : {file_path}")

def save_all():
    """Sauvegarder les 3 lignes et les incidents dans data/"""
    for ligne in ("a", "b", "d"):
        save_data(ligne)
    df_inc = read_incidents()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    file_path = f"data/incidents_{today}.parquet"
    df_inc.to_parquet(file_path, index=False)
    print(f"Données sauvegardées : {file_path}")

def conversion(df):
    """Exploser stops, convertir les horaires en Europe/Paris et trier les arrets dans l'ordre chronologique"""
    df = df.copy()
    df["stops"] = df["stops"].apply(json.loads)
    df = df.explode("stops").dropna(subset=["stops"]).reset_index(drop=True)

    stops = pd.json_normalize(df["stops"]).rename(columns={
        "n": "stop_name",
        "ad": "aimed_time",
        "ed": "expected_time",
        "dt": "delay_sec",
        "v": "platform",
        "s": "status",
    })
    df = pd.concat([df.drop(columns=["stops"]), stops[["stop_name", "aimed_time", "expected_time", "delay_sec", "platform", "status"]]], axis=1)

    df["aimed_time"] = pd.to_datetime(df["aimed_time"], format="ISO8601", utc=True, errors="coerce").dt.tz_convert("Europe/Paris")
    df["expected_time"] = pd.to_datetime(df["expected_time"], format="ISO8601", utc=True, errors="coerce").dt.tz_convert("Europe/Paris")

    group_cols = ["date", "journey_id"] if "date" in df.columns else ["journey_id"]
    df = df.sort_values(group_cols + ["aimed_time"]).reset_index(drop=True)
    df["stop_order"] = df.groupby(group_cols, sort=False).cumcount() + 1
    df["delay_added_sec"] = df.groupby(group_cols, sort=False)["delay_sec"].diff().fillna(df["delay_sec"]).astype(int)
    return df
