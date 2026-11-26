"""
Axe 1 : comparaison globale des retards RER B / D (tunnel partagé) vs RER A (référence)

Une ligne des fichiers clean_* = un arrêt d'un train dans une gare du tronçon central.
Lancer depuis la racine du dépôt :  python analyse/stats.py
Les tableaux s'affichent dans le terminal, les graphiques sont enregistrés dans analyse/figures/.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

DOSSIER_DATA = Path(__file__).resolve().parent.parent / "data"
DOSSIER_FIGURES = Path(__file__).resolve().parent / "figures"

# Couleurs officielles des lignes, utilisées dans tous les graphiques
COULEURS = {"rer_a": "#E3051C", "rer_b": "#5291CE", "rer_d": "#00A88F"}
TRANCHES = ["Pointe matin", "Heures creuses", "Pointe soir", "Soirée", "Week-end"]


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

def charger_donnees(date="2026-11-25"):
    """Charger et empiler les 3 lignes nettoyées.

    Renvoie df_all (tous les arrêts) et df_valide (sans les arrêts supprimés,
    car IDFM leur laisse souvent un retard de 0, ce qui fausserait les moyennes).
    """
    fichiers = [DOSSIER_DATA / f"clean_rer_{l}_{date}.parquet" for l in ("a", "b", "d")]
    df_all = pd.concat([pd.read_parquet(f) for f in fichiers], ignore_index=True)
    df_valide = df_all[~df_all["est_supprime"]]
    return df_all, df_valide


def resume(df, colonne, groupes="line"):
    """Moyenne, médiane, P90 et P95 d'une colonne, par groupe."""
    return df.groupby(groupes)[colonne].agg(
        moyenne="mean",
        mediane="median",
        p90=lambda s: s.quantile(0.90),
        p95=lambda s: s.quantile(0.95),
    ).round(2)


def barres(tableau, titre, ylabel, nom_fichier):
    """Diagramme en barres groupées (une couleur par ligne de RER), enregistré en PNG.

    `tableau` doit avoir les lignes de RER en colonnes.
    """
    couleurs = [COULEURS[l] for l in tableau.columns]
    tableau = tableau.rename(columns=lambda l: "RER " + l[-1].upper())  # "rer_b" -> "RER B" pour la légende

    fig, ax = plt.subplots(figsize=(9, 5))
    tableau.plot.bar(ax=ax, color=couleurs, rot=0)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(titre)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    ax.legend(title="")
    fig.tight_layout()
    DOSSIER_FIGURES.mkdir(exist_ok=True)
    fig.savefig(DOSSIER_FIGURES / f"{nom_fichier}.png", dpi=150)
    return fig


def taux_suppression(df_all):
    """% de trains supprimés ou limités en parcours sur le tronçon central, par ligne.

    Un train = une date + un journey_id.
    - supprimé : tous ses arrêts du tronçon central sont annulés ;
    - limité   : une partie seulement est annulée (ex. retourné avant le tunnel).
    """
    part_annulee = df_all.groupby(["line", "date", "journey_id"])["est_supprime"].mean()
    trains = pd.DataFrame({
        "supprimes": part_annulee == 1,
        "limites": (part_annulee > 0) & (part_annulee < 1),
    })
    return (trains.groupby("line").mean() * 100).round(2)


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pd.set_option("display.width", 200)
    df_all, df_valide = charger_donnees()

    # --- 1. Distribution des retards (minutes), tronçon central -------------
    # A : moyenne 1,28 min, P95 7,10 min ; B : 3,29 min, P95 12,75 min ; D : 3,08 min, P95 13,52 min
    # Les centiles montrent des perturbations presque 2 fois plus fortes sur B et D
    macro = resume(df_valide, "retard_min")
    print("Retards (min), tronçon central :\n", macro, "\n")
    barres(macro.T, "Retards par ligne (tronçon central)", "Retard (minutes)", "1_retards")

    # Même chose à Châtelet-Les Halles seulement : gare commune aux 3 lignes,
    # donc pas de biais lié aux longueurs de tronçon différentes. Même classement : B et D >> A
    chatelet = resume(df_valide[df_valide["stop_name"] == "Châtelet-Les Halles"], "retard_min")
    print("Retards (min), Châtelet-Les Halles :\n", chatelet, "\n")

    # --- 2. Retard ajouté dans le tunnel (secondes) --------------------------
    # Hors tunnel, les 3 lignes prennent environ +7 s par arrêt (médiane 0 s)
    # Dans le tunnel, le A rattrape du retard (-9,3 s) alors que B (+32,4 s) et D (+41,9 s) en prennent
    tunnel = resume(df_valide, "delay_added_sec", ["line", "zone_tunnel"])
    print("Retard ajouté (s), hors tunnel / tunnel :\n", tunnel, "\n")
    barres(tunnel["moyenne"].unstack("line").rename(index={False: "Hors tunnel", True: "Tunnel"}),
           "Retard ajouté en moyenne à chaque arrêt", "Retard ajouté (secondes)", "2_retard_tunnel")

    # Par sens de circulation (on exclut le 1er arrêt et les sens « Aller/Retour »).
    # Le retard se prend à la SORTIE du tunnel : Gare du Nord vers le Nord (+43 s B, +49 s D),
    # Châtelet vers le Sud (+45 s B, +82 s D). À l'entrée, il est nul ou négatif. Le A reste négatif.
    df_tunnel = df_valide[
        df_valide["zone_tunnel"]
        & (df_valide["stop_order"] > 1)
        & df_valide["direction"].isin(["Nord", "Sud", "Est", "Ouest"])
    ]
    sens = df_tunnel.groupby(["line", "direction", "stop_name"])["delay_added_sec"].agg(["mean", "median"])
    print("Retard ajouté (s) dans le tunnel, par sens :\n", sens.round(1), "\n")

    # --- 3. Effet de l'heure de pointe ---------------------------------------
    # Le A encaisse la pointe du matin (2,78 min) mais pas celle du soir (1,46 min).
    # B et D explosent en pointe du soir (5,45 et 4,30 min) et ça déborde sur la soirée.
    tranches = df_valide.groupby(["tranche_horaire", "line"])["retard_min"].mean().unstack().loc[TRANCHES]
    print("Retard moyen (min) par tranche horaire :\n", tranches.round(2), "\n")
    barres(tranches, "Retard moyen selon le moment de la journée", "Retard moyen (minutes)", "3_tranches")

    # Pointe vs heures creuses en semaine.
    # Les ratios sur la moyenne sont proches (x1,6 à x1,8) car le A part de très bas (1,18 min).
    # La différence se voit en minutes (+2,0 min B, +1,7 min D, contre +0,9 min A) et au P90.
    pointe = resume(df_valide[df_valide["heure_pointe"]], "retard_min")
    creuses = resume(df_valide[df_valide["tranche_horaire"] == "Heures creuses"], "retard_min")
    comp = pd.DataFrame({
        "ecart_moyenne_min": pointe["moyenne"] - creuses["moyenne"],
        "ratio_moyenne": pointe["moyenne"] / creuses["moyenne"],
        "ratio_p90": pointe["p90"] / creuses["p90"],
    }).round(2)
    print("Pointe vs heures creuses (semaine) :\n", comp, "\n")

    # Retard ajouté dans le tunnel (s) par tranche : même le week-end, B et D perdent
    # +12 à +29 s ; en pointe soir +58 s (B) et +68 s (D), contre -10 s pour le A.
    tunnel_tranche = df_tunnel.groupby(["tranche_horaire", "line"])["delay_added_sec"].mean().unstack().loc[TRANCHES]
    print("Retard ajouté (s) dans le tunnel par tranche :\n", tunnel_tranche.round(1), "\n")

    # --- 4. Trains supprimés ou limités en parcours --------------------------
    suppr = taux_suppression(df_all)
    print("Trains supprimés / limités (%) :\n", suppr, "\n")
    barres(suppr.T.rename(index={"supprimes": "Supprimés", "limites": "Limités en parcours"}),
           "Trains supprimés ou limités sur le tronçon central", "Part des trains (%)", "4_suppressions")

    plt.show()
