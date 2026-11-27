import re
import unicodedata
from pathlib import Path
import duckdb
import pandas as pd

# Dossiers et fichiers de données
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
COORDS_CSV = Path("data/gares_coords.csv")

# Périmètre géographique retenu (corridor petite couronne autour du goulot B/D)
# Pas besoin du reseau entier
PERIMETRE_LIGNES = {
    "rer_b": [
        "bourg la reine", "bagneux", "arcueil cachan", "laplace", "gentilly",
        "cite universitaire", "denfert rochereau", "port royal", "luxembourg",
        "saint michel notre dame", "chatelet les halles", "gare du nord",
        "la plaine stade de france", "la courneuve aubervilliers", "le bourget",
        "drancy", "le blanc mesnil", "aulnay sous bois",
    ],
    "rer_d": [
        "villeneuve saint georges", "villeneuve triage", "creteil pompadour",
        "le vert de maisons", "maisons alfort alfortville", "gare de lyon",
        "chatelet les halles", "gare du nord", "stade de france saint denis",
        "saint denis", "pierrefitte stains", "garges sarcelles",
        "villiers le bel gonesse arnouville",
    ],
    "rer_a": [
        "la defense", "charles de gaulle etoile", "auber",
        "chatelet les halles", "gare de lyon", "nation", "vincennes",
    ],
}

GARES_TUNNEL = {"chatelet les halles", "gare du nord"}

APPROCHES_TUNNEL = {
    ("saint michel notre dame", "chatelet les halles"),
    ("gare de lyon", "chatelet les halles"),
    ("la plaine stade de france", "gare du nord"),
    ("stade de france saint denis", "gare du nord"),
}

CAPACITE_MAX_TUNNEL = 6 # 3 cantons par voie et 2 sens donc 6 trains max simultanément

# Faciliter les comparaisons
def normaliser_nom(nom: str):
    """Supprime les accents et tirets et casse pour fiabiliser la jointure textuelle."""
    s = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def charger_incidents_perturbations():
    fichier_incidents = PROCESSED_DIR / "clean_incidents.parquet"
    df_incidents = pd.read_parquet(fichier_incidents)

    # Conversion des dates en heure de Paris
    df_incidents["t_debut"] = pd.to_datetime(df_incidents["first_seen"], utc=True)
    df_incidents["t_debut"] = df_incidents["t_debut"].dt.tz_convert("Europe/Paris")

    df_incidents["t_fin"] = pd.to_datetime(df_incidents["last_seen"], utc=True)
    df_incidents["t_fin"] = df_incidents["t_fin"].dt.tz_convert("Europe/Paris")

    # Retirer les indicents de travaux (car pas imprevu)
    lignes_a_garder = []
    for index, ligne in df_incidents.iterrows():
        message = str(ligne["short_message"]).lower()
        if "travaux" not in message:
            lignes_a_garder.append(ligne)

    df_filtre = pd.DataFrame(lignes_a_garder)
    df_filtre = df_filtre.sort_values("t_debut", ascending=False)

    # Création d'un texte lisible pour chaque incident
    labels = []
    for index, ligne in df_filtre.iterrows():
        date_str = ligne["t_debut"].strftime("%d/%m %H:%M")
        nom_ligne = str(ligne["line"]).upper()
        extrait_msg = str(ligne["short_message"])[:60]
        
        label = f"{date_str} | {nom_ligne} — {extrait_msg}..."
        labels.append(label)

    df_filtre["label"] = labels
    return df_filtre

def charger_journee_corridor(date_str: str):
    # Charger les coordonnées GPS des gares dans un dictionnaire
    df_coords = pd.read_csv(COORDS_CSV)
    coords_gares = {}
    
    for index, ligne in df_coords.iterrows():
        cle_gare = normaliser_nom(ligne["stop_name"])
        coords_gares[cle_gare] = {
            "lat": ligne["lat"],
            "lon": ligne["lon"]
        }

    # Créer la liste complète de toutes les gares autorisées
    gares_autorisees = set()
    for liste_gares in PERIMETRE_LIGNES.values():
        for gare in liste_gares:
            gares_autorisees.add(gare)

    # Lire les fichiers parquet de chaque ligne avec DuckDB
    connexion = duckdb.connect()
    tableaux_par_ligne = []

    for ligne in ["rer_a", "rer_b", "rer_d"]:
        chemin_parquet = RAW_DIR / f"{ligne}.parquet"
        
        requete_sql = f"""
        WITH arrets_deplies AS (
            SELECT
                line,
                journey_id,
                mission,
                destination,
                UNNEST(from_json(
                    stops,
                    '[{{"n":"VARCHAR","ad":"VARCHAR","ed":"VARCHAR","dt":"INT","s":"VARCHAR"}}]'
                )) AS arret
            FROM read_parquet('{chemin_parquet}')
            WHERE CAST(date AS DATE) = DATE '{date_str}'
        )
        SELECT
            line,
            journey_id,
            mission,
            destination,
            arret.n AS stop_name,
            (arret.ad::TIMESTAMPTZ) AT TIME ZONE 'Europe/Paris' AS aimed_time,
            COALESCE(arret.ed::TIMESTAMPTZ, arret.ad::TIMESTAMPTZ) AT TIME ZONE 'Europe/Paris' AS expected_time,
            arret.dt AS delay_sec,
            arret.s AS status
        FROM arrets_deplies
        WHERE arret.ad IS NOT NULL
        """
        
        df_ligne = connexion.execute(requete_sql).df()

        # Mise au format date avec fuseau horaire
        df_ligne["aimed_time"] = pd.to_datetime(df_ligne["aimed_time"]).dt.tz_localize("Europe/Paris")
        df_ligne["expected_time"] = pd.to_datetime(df_ligne["expected_time"]).dt.tz_localize("Europe/Paris")

        # Trier les arrêts dans l'ordre chronologique pour chaque train
        df_ligne = df_ligne.sort_values(["journey_id", "aimed_time"])

        # Calculs colonnes supplémentaires
        df_ligne["stop_order"] = df_ligne.groupby("journey_id").cumcount() + 1 # numerotation des arrets
        df_ligne["retard_min"] = (df_ligne["delay_sec"] / 60.0).round(1)
        df_ligne["est_supprime"] = df_ligne["status"] == "CANCELLED"

        tableaux_par_ligne.append(df_ligne)

    # Rassembler toutes les lignes (A, B et D)
    df_complet = pd.concat(tableaux_par_ligne, ignore_index=True)

    # Filtrer et completer avec les coordonnees
    lignes_valides = []
    for index, ligne in df_complet.iterrows():
        cle = normaliser_nom(ligne["stop_name"])
        
        # Uniformiser le nom de Châtelet
        if "chatelet" in cle and "halles" in cle:
            cle = "chatelet les halles"
            ligne["stop_name"] = "Châtelet-Les Halles"

        if cle in gares_autorisees and cle in coords_gares:
            ligne["key"] = cle
            ligne["lat"] = coords_gares[cle]["lat"]
            ligne["lon"] = coords_gares[cle]["lon"]
            lignes_valides.append(ligne)

    return pd.DataFrame(lignes_valides)