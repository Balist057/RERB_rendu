import json
import re
import unicodedata
import requests
from pathlib import Path
import duckdb
import pandas as pd

RAW_DIR = Path("data/raw")
OUT_CSV = Path("data/gares_coords.csv") # format plus simple que parquet vu la petite taille du fichier
IDFM_URL = (
    "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/emplacement-des-gares-idf/exports/json"
)

# Faciliter les comparaisons
def normaliser_nom(nom: str):
    """Supprime les accents et tirets et casse pour fiabiliser la jointure textuelle."""
    s = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def construire_referentiel_gares():
    # Lister toutes les gares uniques présentes dans nos données brutes
    con = duckdb.connect()
    gares_projet = set()
    for ligne in ["rer_a", "rer_b", "rer_d"]:
        path = RAW_DIR / f"{ligne}.parquet"
        df_n = con.execute(f"""
            SELECT DISTINCT s.n AS stop_name
            FROM (
                SELECT UNNEST(from_json(stops, '[{{"n":"VARCHAR"}}]')) AS s
                FROM read_parquet('{path}')
            )
        """).df()
        gares_projet.update(df_n["stop_name"])

    # Recuperation des coordonnes des gares qui nous interessent
    data_idfm = requests.get(IDFM_URL).json()

    cibles = {}
    for g in gares_projet:
        cle = normaliser_nom(g)
        nom_propre = "Châtelet-Les Halles" if cle == "chatelet les halles" else g.strip() # Forcer le nom pour Châtelet
        cibles[cle] = nom_propre

    lignes_csv = []
    vues = set()

    for row in data_idfm:
        geo = row.get("geo_point_2d")
        nom = row.get("nom_gares")
        if geo and nom: # Si existe
            cle = normaliser_nom(nom)
            if cle in cibles and cle not in vues:
                vues.add(cle)
                lignes_csv.append({"stop_name": cibles[cle], "lat": geo["lat"], "lon": geo["lon"]})

    df_out = pd.DataFrame(lignes_csv)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(OUT_CSV, index=False)
    return df_out

if __name__ == "__main__":
    construire_referentiel_gares()