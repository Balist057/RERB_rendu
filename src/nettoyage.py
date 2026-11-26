import duckdb
import pandas as pd

try:
    from src.lecture import DATE_DEBUT, RAW_DIR, init_s3, update_all
except ImportError:
    from lecture import DATE_DEBUT, RAW_DIR, init_s3, update_all


PROCESSED_DIR = RAW_DIR.parent / "processed"

GARES_CENTRALES = {
    "a": [
        "Charles De Gaulle-Étoile",
        "Auber",
        "Châtelet-Les Halles",
        "Gare de Lyon",
        "Nation",
    ],
    "b": [
        "Denfert-Rochereau",
        "Port Royal",
        "Luxembourg",
        "Saint-Michel Notre-Dame",
        "Châtelet-Les Halles",
        "Gare du Nord",
        "La Plaine Stade de France",
        "La Courneuve - Aubervilliers",
        "Le Bourget",
        "Drancy",
        "Le Blanc-Mesnil",
        "Aulnay-sous-Bois",
    ],
    "d": [
        "Gare de Lyon",
        "Châtelet-Les Halles",
        "Gare du Nord",
        "Stade de France-Saint-Denis",
        "Saint-Denis",
    ],
}

FICHIERS_BRUTS = {
    "a": RAW_DIR / "rer_a.parquet",
    "b": RAW_DIR / "rer_b.parquet",
    "d": RAW_DIR / "rer_d.parquet",
    "incidents": RAW_DIR / "incidents.parquet",
}


def charger_ligne(con, ligne, source="local", toutes_gares=False, date_jour=None):
    """Extraire les arrêts d'une ligne en local ou depuis S3 (tronçon central ou toutes gares)."""
    if source not in ("local", "s3"):
        raise ValueError("source doit valoir 'local' ou 's3'")

    if source == "local":
        chemin = str(FICHIERS_BRUTS[ligne])
    else:
        init_s3(con)
        if date_jour:
            chemin = f"s3://gpichonlegroux/rer-{ligne}/date={date_jour}/part-0.parquet"
        else:
            chemin = f"s3://gpichonlegroux/rer-{ligne}/date=*/*.parquet"

    filtre_date = "WHERE CAST(date AS DATE) = CAST(? AS DATE)" if date_jour else "WHERE date >= ?"
    filtre_gares = "" if toutes_gares else "WHERE list_contains(?, stop_name)"
    params = [chemin, date_jour or DATE_DEBUT] if toutes_gares else [chemin, date_jour or DATE_DEBUT, GARES_CENTRALES[ligne]]

    query = f"""
    WITH base AS (
        SELECT * EXCLUDE (stops),
               UNNEST(from_json(stops, '[{{"n":"VARCHAR","ad":"TIMESTAMPTZ","ed":"TIMESTAMPTZ","dt":"BIGINT","v":"VARCHAR","s":"VARCHAR"}}]')) AS stop
        FROM read_parquet(?, hive_partitioning=true, union_by_name=true)
        {filtre_date}
    ),
    ord AS (
        SELECT * EXCLUDE (stop),
               CASE WHEN stop.n = 'Châtelet - Les Halles' THEN 'Châtelet-Les Halles' ELSE stop.n END AS stop_name,
               stop.ad AS aimed_time,
               stop.ed AS expected_time,
               stop.dt AS delay_sec,
               stop.v AS platform,
               stop.s AS status,
               ROW_NUMBER() OVER (PARTITION BY date, journey_id ORDER BY stop.ad) AS stop_order,
               stop.dt - LAG(stop.dt, 1, 0) OVER (PARTITION BY date, journey_id ORDER BY stop.ad) AS delay_added_sec
        FROM base
    )
    SELECT * FROM ord
    {filtre_gares}
    ORDER BY date, journey_id, aimed_time
    """
    df = con.execute(query, params).df()
    df["line"] = df["line"].fillna(f"rer_{ligne}")
    df["aimed_time"] = df["aimed_time"].dt.tz_convert("Europe/Paris")
    df["expected_time"] = df["expected_time"].dt.tz_convert("Europe/Paris")
    return df


def charger_incidents(con, source="local"):
    """Charger les messages d'incidents en local ou depuis S3."""
    if source not in ("local", "s3"):
        raise ValueError("source doit valoir 'local' ou 's3'")

    if source == "local":
        chemin = str(FICHIERS_BRUTS["incidents"])
    else:
        init_s3(con)
        chemin = "s3://gpichonlegroux/incidents/date=*/*.parquet"

    return con.execute("SELECT * FROM read_parquet(?, union_by_name=true) WHERE date >= ?", [chemin, DATE_DEBUT]).df()


def ajout_variables(df):
    """Ajouter les variables d'analyse et écarter les retards aberrants."""
    df = df.copy()
    df["retard_min"] = df["delay_sec"] / 60
    df = df[df["retard_min"].between(-15, 180)].copy()

    df["est_supprime"] = df["status"] == "CANCELLED"
    df["zone_tunnel"] = df["stop_name"].isin(["Châtelet-Les Halles", "Gare du Nord"])

    semaine = df["aimed_time"].dt.day_of_week < 5
    heure = df["aimed_time"].dt.hour + df["aimed_time"].dt.minute / 60
    pointe_matin = semaine & (heure >= 7.5) & (heure < 9.5)
    pointe_soir = semaine & (heure >= 17.0) & (heure < 19.5)

    df["heure_pointe"] = pointe_matin | pointe_soir

    tranche = pd.Series("Heures creuses", index=df.index)
    tranche.loc[~semaine] = "Week-end"
    tranche.loc[semaine & ((heure >= 20.0) | (heure < 6.0))] = "Soirée"
    tranche.loc[pointe_matin] = "Pointe matin"
    tranche.loc[pointe_soir] = "Pointe soir"
    df["tranche_horaire"] = tranche
    return df


def preparer_donnees(source="local", sauvegarder=True, maj=False):
    """Nettoyer les données et exporter les Parquet prêts pour l'analyse."""
    if source == "local" and (maj or not all(f.exists() for f in FICHIERS_BRUTS.values())):
        update_all()

    con = duckdb.connect()
    resultats = {}

    if sauvegarder:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    for ligne in ("a", "b", "d"):
        df = charger_ligne(con, ligne, source=source)
        df = ajout_variables(df)
        if sauvegarder:
            df.to_parquet(PROCESSED_DIR / f"clean_rer_{ligne}.parquet", index=False)
        resultats[ligne] = df

    df_incidents = charger_incidents(con, source=source)
    con.close()

    if sauvegarder:
        df_incidents.to_parquet(PROCESSED_DIR / "clean_incidents.parquet", index=False)

    return resultats["a"], resultats["b"], resultats["d"], df_incidents


def charger_donnees_propres(source="local", maj=False):
    """Lire les Parquet nettoyés (ou les générer depuis local/S3)."""
    fichiers = [
        PROCESSED_DIR / "clean_rer_a.parquet",
        PROCESSED_DIR / "clean_rer_b.parquet",
        PROCESSED_DIR / "clean_rer_d.parquet",
        PROCESSED_DIR / "clean_incidents.parquet",
    ]
    if source == "local" and not maj and all(f.exists() for f in fichiers):
        return tuple(pd.read_parquet(f) for f in fichiers)
    return preparer_donnees(source=source, sauvegarder=True, maj=maj)


def charger_jour_complet(date_jour, source="local"):
    """Charger toutes les gares des 3 lignes sur une journée donnée (pour visualiser un incident)."""
    jour = pd.Timestamp(date_jour).strftime("%Y-%m-%d")
    if source == "local" and not all(FICHIERS_BRUTS[l].exists() for l in ("a", "b", "d")):
        source = "s3"

    con = duckdb.connect()
    dfs = [ajout_variables(charger_ligne(con, l, source=source, toutes_gares=True, date_jour=jour)) for l in ("a", "b", "d")]
    con.close()
    return pd.concat(dfs, ignore_index=True)
