import datetime
import math
import re
import unicodedata
from pathlib import Path
import duckdb
import pandas as pd
import plotly.graph_objects as go

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

CAPACITE_MAX_TUNNEL = 7

# Paramètres visuels pour la carte
COULEURS_LIGNES = {"rer_a": "#E3051C", "rer_b": "#5291CE", "rer_d": "#00814F"}

NIVEAUX_RETARD = [
    ("À l'heure (< 3 min)", "#2ecc71"),
    ("Retard modéré (3–10 min)", "#f39c12"),
    ("Retard important (> 10 min)", "#e74c3c"),
]

MODES_REPLAY = {
    "Zoom tunnel : 15 min (pas 10s)": {"duree_min": 15, "pas_sec": 10, "frame_ms": 80},
    "Vue standard : 30 min (pas 30s)": {"duree_min": 30, "pas_sec": 30, "frame_ms": 200},
}


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

            points_ligne.append({"key": gare, "lat": lat, "lon": lon, "dist": dist_cumul})

        # Index rapide par nom de gare pour retrouver sa distance sur la ligne
        index_gares = {pt["key"]: pt for pt in points_ligne}
        traces[ligne] = {
            "points": points_ligne,
            "index": index_gares,
        }

    return traces

TRACE_LIGNES = construire_trace_lignes()

def categoriser_incident(titre: str):
    # Classe l'incident à partir de son titre (short_message)
    msg = str(titre).lower()
    if "colis suspect" in msg or "bagage abandonné" in msg or "bagage oublié" in msg:
        return "Colis / bagage abandonné"
    if "signalisation" in msg or "aiguillage" in msg or "panne d'installation" in msg or "passage à niveau" in msg:
        return "Panne signalisation / infra"
    if "malaise" in msg or "accident grave" in msg or "personne sur les voies" in msg or "incident affectant la voie" in msg:
        return "Incident voyageur / voies"
    if "panne de train" in msg or "train en panne" in msg or "panne matériel" in msg or "incident technique" in msg:
        return "Panne de train / technique"
    if "mouvement social" in msg or "grève" in msg:
        return "Mouvement social"
    if "stationnement" in msg or "régulation" in msg or "affluence" in msg:
        return "Régulation / stationnement"
    return "Autre perturbation"


def assurer_donnees_locales():
    """Télécharge et prépare les Parquet depuis S3 si le dépôt vient d'être cloné."""
    prets = (PROCESSED_DIR / "clean_incidents.parquet").exists() and all(
        (RAW_DIR / f"{l}.parquet").exists() for l in ("rer_a", "rer_b", "rer_d")
    )
    if not prets:
        try:
            from src.nettoyage import charger_donnees_propres
        except ImportError:
            from nettoyage import charger_donnees_propres
        charger_donnees_propres()


def charger_incidents_perturbations():
    assurer_donnees_locales()
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
    df_filtre = df_filtre.sort_values("t_debut", ascending=False).reset_index(drop=True)
    df_filtre["categorie"] = df_filtre["short_message"].apply(categoriser_incident)

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

def extraire_dates_disponibles(df_incidents: pd.DataFrame):
    # Récupère les dates triées pour le mode exploration libre
    if not df_incidents.empty:
        return sorted(df_incidents["t_debut"].dt.date.unique().tolist(), reverse=True)
    return [datetime.date.today()]

def charger_journee_corridor(date_str: str):
    assurer_donnees_locales()
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
        df_ligne["aimed_time"] = pd.to_datetime(df_ligne["aimed_time"]).dt.tz_localize(
            "Europe/Paris", ambiguous="NaT", nonexistent="shift_forward"
        )
        df_ligne["expected_time"] = pd.to_datetime(df_ligne["expected_time"]).dt.tz_localize(
            "Europe/Paris", ambiguous="NaT", nonexistent="shift_forward"
        )

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
    # Place le train le long des gares intermédiaires (evite de couper tout droit dans les virages)
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

    # Taux d'occupation physique borné à 100 %
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

def construire_annotation(etat_tunnel: dict):
    # Encadré d'état du tunnel placé en haut à gauche (zone libre sous la légende)
    texte = (
        f"<b>TUNNEL CHÂTELET ↔ GARE DU NORD</b><br>"
        f"État : <b>{etat_tunnel['etat']}</b> — Occupation : <b>{etat_tunnel['sat_pct']} %</b><br>"
        f"Dans le tube : <b>{etat_tunnel['nb_tube']}/{CAPACITE_MAX_TUNNEL} trains</b> "
        f"({etat_tunnel['nb_b']} B · {etat_tunnel['nb_d']} D)<br>"
        f"Retenus aux entrées (>3m) : <b>{etat_tunnel['nb_retenus']} train(s)</b><br>"
        f"Traversée moy. : <b>{etat_tunnel['txt_trav']}</b> (nominal ~4 min)"
    )
    return dict(
        text=texte,
        x=0.01, y=0.985, xref="paper", yref="paper",
        xanchor="left", yanchor="top", align="left",
        showarrow=False,
        bgcolor="rgba(255, 255, 255, 0.94)",
        bordercolor=etat_tunnel["bord"],
        borderwidth=2,
        borderpad=8,
        font=dict(size=12, color="#111111"),
    )

def construire_carte_replay(
    df_jour: pd.DataFrame,
    segs_affichage: pd.DataFrame,
    segs_bd: pd.DataFrame,
    lignes_actives: list,
    t_start: pd.Timestamp,
    mode_config: dict,
    t_annonce: pd.Timestamp = None,
):
    # Génère la figure Plotly complète avec tracés, gares, trains animés et slider
    duree_min = mode_config["duree_min"]
    pas_sec = mode_config["pas_sec"]
    vitesse_ms = mode_config["frame_ms"]

    fig_map = go.Figure()

    # 1. Tracés géographiques des voies
    coords_gares = df_jour.drop_duplicates("key").set_index("key")[["lat", "lon"]].to_dict("index")
    for ligne in lignes_actives:
        cles_valides = [k for k in PERIMETRE_LIGNES[ligne] if k in coords_gares]
        fig_map.add_trace(go.Scattermap(
            lat=[coords_gares[k]["lat"] for k in cles_valides],
            lon=[coords_gares[k]["lon"] for k in cles_valides],
            mode="lines",
            line=dict(width=4, color=COULEURS_LIGNES[ligne]),
            opacity=0.5,
            name=ligne.upper().replace("_", " "),
            hoverinfo="skip",
        ))

    # 2. Gares du corridor
    gares_df = df_jour[["stop_name", "lat", "lon"]].drop_duplicates()
    fig_map.add_trace(go.Scattermap(
        lat=gares_df["lat"], lon=gares_df["lon"],
        mode="markers+text",
        marker=dict(size=6, color="#222222"),
        text=gares_df["stop_name"],
        textposition="top right",
        textfont=dict(size=9, color="#111111"),
        hoverinfo="text",
        name="Gares",
    ))

    # 3. Trains en circulation séparés en 3 traces (une par couleur de retard)
    nb_traces_fixes = len(lignes_actives) + 1
    indices_trains = [nb_traces_fixes + i for i in range(len(NIVEAUX_RETARD))]

    pos_0 = interpoler_positions(segs_affichage, t_start)
    for label_retard, couleur_hex in NIVEAUX_RETARD:
        sous_pos = pos_0[pos_0["color"] == couleur_hex]
        fig_map.add_trace(go.Scattermap(
            lat=sous_pos["lat_now"],
            lon=sous_pos["lon_now"],
            mode="markers",
            marker=dict(size=12, color=couleur_hex),
            text=sous_pos["hover"],
            hoverinfo="text",
            name=label_retard,
        ))

    # 4. Précalcul des pas de temps
    nb_etapes = int((duree_min * 60) // pas_sec) + 1
    frames, slider_steps = [], []

    for step in range(nb_etapes):
        ecoule_sec = step * pas_sec
        t_m = t_start + pd.Timedelta(seconds=ecoule_sec)
        pos_m = interpoler_positions(segs_affichage, t_m)
        ann_m = construire_annotation(calculer_etat_tunnel(segs_bd, t_m))

        # Afficher le décalage par rapport à l'annonce si on rejoue un incident
        if t_annonce is not None:
            delta_annonce = int((t_m - t_annonce).total_seconds() // 60)
            signe = "+" if delta_annonce >= 0 else ""
            label_m = f"{t_m.strftime('%H:%M:%S')} ({signe}{delta_annonce}m)"
        else:
            label_m = t_m.strftime("%H:%M:%S") if pas_sec < 60 else t_m.strftime("%H:%M")

        data_step = []
        for _, couleur_hex in NIVEAUX_RETARD:
            sous_pos = pos_m[pos_m["color"] == couleur_hex]
            data_step.append(go.Scattermap(
                lat=sous_pos["lat_now"],
                lon=sous_pos["lon_now"],
                marker=dict(size=12, color=couleur_hex),
                text=sous_pos["hover"],
            ))

        frames.append(go.Frame(
            name=f"step_{step}",
            traces=indices_trains,
            data=data_step,
            layout=go.Layout(annotations=[ann_m]),
        ))
        slider_steps.append(dict(
            method="animate",
            args=[[f"step_{step}"], {"frame": {"duration": 0, "redraw": True}, "mode": "immediate"}],
            label=label_m,
        ))
    fig_map.frames = frames
    fig_map.update_layout(
        map=dict(style="carto-positron", center=dict(lat=48.865, lon=2.365), zoom=10.4),
        paper_bgcolor="white",
        margin=dict(l=0, r=0, t=42, b=95),
        height=690,
        font=dict(color="#111111"),
        annotations=[construire_annotation(calculer_etat_tunnel(segs_bd, t_start))],
        legend=dict(
            orientation="h",
            y=1.01, yanchor="bottom",
            x=0.0, xanchor="left",
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="#CCCCCC",
            borderwidth=1,
            font=dict(size=11, color="#111111"),
        ),
        updatemenus=[dict(
            type="buttons",
            direction="right",
            showactive=False,
            x=0.01, y=-0.03, xanchor="left", yanchor="top",
            bgcolor="#F8F9FA",
            bordercolor="#CCCCCC",
            borderwidth=1,
            font=dict(size=20, color="#111111"),
            buttons=[
                dict(
                    label="Animer",
                    method="animate",
                    args=[None, {"frame": {"duration": vitesse_ms, "redraw": True}, "fromcurrent": True, "transition": {"duration": 0}}],
                ),
                dict(
                    label="Pause",
                    method="animate",
                    args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}],
                ),
            ],
        )],
        sliders=[dict(
            active=0,
            x=0.25, len=0.74, y=-0.02, yanchor="top",
            bgcolor="rgba(255,255,255,0.94)",
            bordercolor="#CCCCCC",
            borderwidth=1,
            pad={"t": 4, "b": 4, "l": 8, "r": 8},
            font=dict(size=10, color="#111111"),
            currentvalue={
                "prefix": "Heure : ",
                "visible": True,
                "xanchor": "right",
                "font": {"size": 12, "color": "#111111"},
            },
            steps=slider_steps,
        )],
    )
    return fig_map