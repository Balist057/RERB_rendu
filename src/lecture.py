from pathlib import Path
import duckdb
import pandas as pd


RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
DATE_DEBUT = "2026-10-02"

# Table de correspondance (noms dans le code (rer_a) et sur le serveur (rer-a))
SOURCES = {
    "rer_a": "rer-a",
    "rer_b": "rer-b",
    "rer_d": "rer-d",
    "incidents": "incidents",
}


def init_s3(con=None):
    """Configurer DuckDB pour lire le bucket S3 public SSP Cloud."""
    if con is None:
        con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        "CREATE OR REPLACE SECRET (TYPE S3, KEY_ID '', SECRET '', "
        "ENDPOINT 'minio.lab.sspcloud.fr', URL_STYLE 'path');"
    )
    return con


def read_s3(nom, depuis=DATE_DEBUT, con=None):
    """Lire les partitions S3 d'une source depuis une date donnée."""
    if con is None:
        con = init_s3()

    pattern = f"s3://gpichonlegroux/{SOURCES[nom]}/date=*/*.parquet"

    # Liste des noms de fichiers verifiant le pattern
    fichiers = [row[0] for row in con.execute("SELECT file FROM glob(?) ORDER BY file", [pattern]).fetchall()]

    # Filtre les fichiers en fct de la date (extrait la date du nom)
    fichiers = [f for f in fichiers if f.split("date=")[1].split("/")[0] >= depuis]

    # Dataframe vide si aucun fichier ne correspond
    if not fichiers:
        return pd.DataFrame()

    # Fusionne les fichiers Parquet en extrayant la date des dossiers et en alignant les colonnes par nom
    df = con.execute(
        "SELECT * FROM read_parquet(?, hive_partitioning=true, union_by_name=true)",
        [fichiers],
    ).df()

    # Ajout du nom de la ligne
    if nom != "incidents":
        df["line"] = nom
    return df


def update_source(nom, con=None):
    """Mettre à jour le Parquet brut local d'une source."""
    if con is None:
        con = init_s3()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    chemin = RAW_DIR / f"{nom}.parquet"

    # Le fichier local n'existe pas --> creation
    if not chemin.exists():
        df = read_s3(nom, depuis=DATE_DEBUT, con=con)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df.to_parquet(chemin, index=False)
        return df

    # Récupère la dernière date locale (AAAA-MM-JJ) ou repart de DATE_DEBUT si le fichier est vide
    max_date = con.execute("SELECT CAST(MAX(date) AS VARCHAR)[:10] FROM read_parquet(?)", [str(chemin)]).fetchone()[0]
    depuis = max_date or DATE_DEBUT

    df_new = read_s3(nom, depuis=depuis, con=con)

    # Vide --> on renvoie le fichier local
    if df_new.empty:
        return pd.read_parquet(chemin)

    # Non vide --> on fusionne avec le fichier local
    df_old = pd.read_parquet(chemin)
    df_old["date"] = pd.to_datetime(df_old["date"])
    df_new["date"] = pd.to_datetime(df_new["date"])
    df = pd.concat([df_old[df_old["date"] < pd.Timestamp(depuis)], df_new], ignore_index=True)
    df.to_parquet(chemin, index=False)
    return df


def update_all():
    """Mettre à jour toutes les sources dans data/raw/."""
    con = init_s3()
    for nom in SOURCES:
        update_source(nom, con=con)
