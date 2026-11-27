import math
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

CAPACITE_MAX_TUNNEL = 7  # 3 cantons par voie x 2 sens + zones d'approche = 7 trains max simultanément

# Faciliter les comparaisons
def normaliser_nom(nom: str):
    """Supprime les accents et tirets et casse pour fiabiliser la jointure textuelle."""
    s = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def construire_trace_lignes():
    """Déroule chaque ligne comme une ficelle graduée (distance cumulée de gare en gare)."""
    # Objectif: points (train) de la carte sur le parcours des lignes et pas ailleurs

    df_coords = pd.read_csv(COORDS_CSV)
    df_coords["key"] = df_coords["stop_name"].apply(normaliser_nom)
    df_coords = df_coords.drop_duplicates("key")

    # Dictionnaire rapide : cle_gare -> {"lat": ..., "lon": ...}
    coords_map = {}
    for row in df_coords.to_dict("records"):
        coords_map[row["key"]] = {"lat": row["lat"], "lon": row["lon"]}

    traces = {}
    for ligne, liste_gares in PERIMETRE_LIGNES.items():
        points_ligne = []
        dist_cumul = 0.0

        for gare in liste_gares:
            if gare not in coords_map:
                continue

            lat = coords_map[gare]["lat"]
            lon = coords_map[gare]["lon"]

            # Ajouter la longueur du tronçon depuis la gare précédente
            if points_ligne:
                prev = points_ligne[-1]
                dist_cumul += math.hypot(lat - prev["lat"], lon - prev["lon"])

            points_ligne.append({
                "key": gare,
                "lat": lat,
                "lon": lon,
                "dist": dist_cumul,
            })

        # Index rapide par nom de gare pour retrouver sa distance sur la ligne
        index_gares = {pt["key"]: pt for pt in points_ligne}
        traces[ligne] = {
            "points": points_ligne,
            "index": index_gares,
        }

    return traces

# Pré-calculé une seule fois au chargement du fichier
TRACE_LIGNES = construire_trace_lignes()

def charger_incidents_perturbations():
    fichier_incidents = PROCESSED_DIR / "clean_incidents.parquet"
    df_incidents = pd.read_parquet(fichier_incidents)

    # Conversion des dates en heure de Paris
    df_incidents["t_debut"] = pd.to_datetime(df_incidents["first_seen"], utc=True)
    df_incidents["t_debut"] = df_incidents["t_debut"].dt.tz_convert("Europe/Paris")

    df_incidents["t_fin"] = pd.to_datetime(df_incidents["last_seen"], utc=True)
    df_incidents["t_fin"] = df_incidents["t_fin"].dt.tz_convert("Europe/Paris")

    # Retirer les incidents de travaux (car pas imprevu)
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
    # Charger les coordonnées GPS des gares
    df_coords = pd.read_csv(COORDS_CSV)
    df_coords["key"] = df_coords["stop_name"].apply(normaliser_nom)
    df_coords = df_coords.drop_duplicates("key")[["key", "lat", "lon"]]

    # Créer la liste complète de toutes les gares autorisées
    gares_autorisees = set()
    for liste_gares in PERIMETRE_LIGNES.values():
        for gare in liste_gares:
            gares_autorisees.add(gare)

    # Lire les fichiers parquet de chaque ligne avec DuckDB
    connexion = duckdb.connect()
    tableaux_par_ligne = []
    jour_suivant = (pd.Timestamp(date_str) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

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
            WHERE date >= '{date_str}' AND date < '{jour_suivant}'
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
        if df_ligne.empty:
            continue

        # Mise au format date avec fuseau horaire
        df_ligne["aimed_time"] = pd.to_datetime(df_ligne["aimed_time"]).dt.tz_localize("Europe/Paris")
        df_ligne["expected_time"] = pd.to_datetime(df_ligne["expected_time"]).dt.tz_localize("Europe/Paris")

        # Trier les arrêts dans l'ordre chronologique pour chaque train
        df_ligne = df_ligne.sort_values(["journey_id", "aimed_time"])

        # Calculs colonnes supplémentaires
        df_ligne["stop_order"] = df_ligne.groupby("journey_id").cumcount() + 1
        df_ligne["retard_min"] = (df_ligne["delay_sec"] / 60.0).round(1)
        df_ligne["est_supprime"] = df_ligne["status"] == "CANCELLED"

        tableaux_par_ligne.append(df_ligne)

    if not tableaux_par_ligne:
        return pd.DataFrame()

    # Rassembler toutes les lignes (A, B et D)
    df_complet = pd.concat(tableaux_par_ligne, ignore_index=True)

    # Filtrer et compléter avec les coordonnées
    df_complet["key"] = df_complet["stop_name"].apply(normaliser_nom)

    est_chatelet = df_complet["key"].str.contains("chatelet") & df_complet["key"].str.contains("halles")
    df_complet.loc[est_chatelet, "key"] = "chatelet les halles"
    df_complet.loc[est_chatelet, "stop_name"] = "Châtelet-Les Halles"

    df_filtre = df_complet[df_complet["key"].isin(gares_autorisees)]
    return df_filtre.merge(df_coords, on="key", how="inner")

def preparer_segments(df_jour: pd.DataFrame):
    # Garder les trains actifs uniquement et les trier dans l'ordre de passage
    df_actifs = df_jour[~df_jour["est_supprime"]]
    df_actifs = df_actifs.sort_values(["journey_id", "stop_order"])

    # Conversion en liste pour parcourir rapidement les arrêts consécutifs
    arrets = df_actifs.to_dict("records")  # liste de dico
    segments = []

    for i in range(len(arrets) - 1):
        dep = arrets[i]
        arr = arrets[i + 1]

        # Vérifier qu'il s'agit du même train et que l'horaire avance bien
        # s'arrete au terminus car la prochaine ligne correspond a un autre train
        meme_train = dep["journey_id"] == arr["journey_id"]
        temps_coherent = arr["expected_time"] > dep["expected_time"]

        if meme_train and temps_coherent:
            segments.append({
                "line": dep["line"],
                "journey_id": dep["journey_id"],
                "mission": dep["mission"],
                "destination": dep["destination"],

                "stop_name": dep["stop_name"],
                "next_stop": arr["stop_name"],

                "key": dep["key"],
                "next_key": arr["key"],

                "t1": dep["expected_time"],
                "t2": arr["expected_time"],

                "lat": dep["lat"],
                "lon": dep["lon"],
                "lat2": arr["lat"],
                "lon2": arr["lon"],

                "retard_min": dep["retard_min"],
                "r2": arr["retard_min"],
            })

    return pd.DataFrame(segments)

def position_sur_ligne(ligne: str, gare_dep: str, gare_arr: str, avancement: float, seg: dict):
    """Place le train le long des gares intermédiaires de la ligne (abscisse curviligne)."""
    trace = TRACE_LIGNES.get(ligne)
    if not trace or gare_dep not in trace["index"] or gare_arr not in trace["index"]:
        lat = seg["lat"] + avancement * (seg["lat2"] - seg["lat"])
        lon = seg["lon"] + avancement * (seg["lon2"] - seg["lon"])
        return lat, lon

    # Distance cible sur la ficelle graduée de la ligne (marche dans les 2 sens)
    dist_dep = trace["index"][gare_dep]["dist"]
    dist_arr = trace["index"][gare_arr]["dist"]
    dist_cible = dist_dep + avancement * (dist_arr - dist_dep)

    # Chercher entre quelles gares consécutives tombe dist_cible
    points = trace["points"]
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]

        if p1["dist"] <= dist_cible <= p2["dist"]:
            longueur_troncon = p2["dist"] - p1["dist"]
            if longueur_troncon == 0:
                return p1["lat"], p1["lon"]

            ratio = (dist_cible - p1["dist"]) / longueur_troncon
            lat = p1["lat"] + ratio * (p2["lat"] - p1["lat"])
            lon = p1["lon"] + ratio * (p2["lon"] - p1["lon"])
            return lat, lon

    return seg["lat2"], seg["lon2"]

def interpoler_positions(segs: pd.DataFrame, t_now: pd.Timestamp):
    # Objectif: avancer un train le long du tracé de la ligne (même s'il saute des gares)
    # Filtrer uniquement les trains en cours de trajet à l'instant t_now
    en_cours = segs[(segs["t1"] <= t_now) & (segs["t2"] >= t_now)]
    actifs = en_cours.to_dict("records")  # liste de dico
    trains_en_circulation = []

    for seg in actifs:
        # Proportion du trajet déjà parcourue (entre 0 et 1)
        duree_totale = (seg["t2"] - seg["t1"]).total_seconds()
        temps_ecoule = (t_now - seg["t1"]).total_seconds()
        avancement = temps_ecoule / duree_totale

        # Position GPS sur le tracé de la ligne et retard estimé à l'instant t_now
        lat_actuelle, lon_actuelle = position_sur_ligne(
            seg["line"], seg["key"], seg["next_key"], avancement, seg
        )
        retard_actuel = round(seg["retard_min"] + avancement * (seg["r2"] - seg["retard_min"]), 1)

        # Couleur selon le niveau de retard
        if retard_actuel < 3:
            couleur = "#2ecc71"
        elif retard_actuel < 10:
            couleur = "#f39c12"
        else:
            couleur = "#e74c3c"

        trains_en_circulation.append({
            "lat_now": lat_actuelle,
            "lon_now": lon_actuelle,
            "retard_now": retard_actuel,
            "color": couleur,
            "hover": (
                f"<b>{str(seg['line']).upper()} — {seg['mission']}</b><br>"
                f"{seg['stop_name']} → {seg['next_stop']}<br>"
                f"Terminus : {seg['destination']}<br>"
                f"Retard : <b>{retard_actuel} min</b>"
            ),
        })

    # Garantir la structure des colonnes même s'il n'y a aucun train (pour eviter un crash KeyError)
    if not trains_en_circulation:
        return pd.DataFrame(columns=["lat_now", "lon_now", "retard_now", "color", "hover"])

    return pd.DataFrame(trains_en_circulation)

def calculer_etat_tunnel(segs_bd: pd.DataFrame, t_now: pd.Timestamp):
    # Objectif: indiquer le niveau de saturation du tunnel
    # Filtrer uniquement les trains RER B et D en mouvement à l'instant t_now
    en_cours = segs_bd[(segs_bd["t1"] <= t_now) & (segs_bd["t2"] >= t_now)]
    actifs = en_cours.to_dict("records")

    # les stats a afficher
    nb_trains_b = 0
    nb_trains_d = 0
    nb_trains_retenus = 0
    durees_traversee = []

    for seg in actifs:
        dep = seg["key"]
        arr = seg["next_key"]

        # Compter les trains dans le tunnel Châtelet - Gare du Nord
        if dep in GARES_TUNNEL and arr in GARES_TUNNEL:
            if seg["line"] == "rer_b":
                nb_trains_b += 1
            elif seg["line"] == "rer_d":
                nb_trains_d += 1

            duree_min = (seg["t2"] - seg["t1"]).total_seconds() / 60.0
            durees_traversee.append(duree_min)

        # Compter les trains ralentis (> 3 min) aux entrées du tunnel
        if (dep, arr) in APPROCHES_TUNNEL and seg["retard_min"] > 3:
            nb_trains_retenus += 1

    # Taux d'occupation physique borné à 100 % (7 trains max avec zones d'approche)
    nb_total_tunnel = nb_trains_b + nb_trains_d
    taux_saturation = min(100, int(round((nb_total_tunnel / CAPACITE_MAX_TUNNEL) * 100)))

    # Temps moyen de traversée du tunnel
    if durees_traversee:
        moyenne_traversee = sum(durees_traversee) / len(durees_traversee)
        texte_traversee = f"{moyenne_traversee:.1f} min"
    else:
        moyenne_traversee = 0.0
        texte_traversee = "—"

    # Niveau d'alerte global du goulot
    if taux_saturation >= 85 or moyenne_traversee >= 7.0:
        etat = "SATURÉ"
        couleur_bordure = "#e74c3c"
    elif taux_saturation >= 65 or moyenne_traversee >= 5.0:
        etat = "CHARGÉ"
        couleur_bordure = "#f39c12"
    else:
        etat = "FLUIDE"
        couleur_bordure = "#2ecc71"

    return {
        "etat": etat,
        "bord": couleur_bordure,
        "sat_pct": taux_saturation,
        "nb_tube": min(nb_total_tunnel, CAPACITE_MAX_TUNNEL),
        "nb_b": nb_trains_b,
        "nb_d": nb_trains_d,
        "nb_retenus": nb_trains_retenus,
        "txt_trav": texte_traversee,
    }