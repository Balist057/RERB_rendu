####################################################################################################################################
# AXE 1 : les retards du RER B et du RER D (qui partagent le tunnel Châtelet - Gare du Nord)
# sont-ils plus élevés que ceux du RER A (référence : très fréquenté, mais sans voies partagées) ?
# Dans cette partie, nous réalisons un simple constat naïf avec des calculs et graphiques simples qui donnent une idée du résultat.
# Données : un arrêt d'un train dans une gare du tronçon central (à partir du 02/10/2026).
# tableau récapitulatif + graphiques dans docs/figures/
######################################################################################################################################

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
FIGURES = Path(__file__).resolve().parent.parent / "docs" / "figures"
LIGNES = {"rer_a": "RER A", "rer_b": "RER B", "rer_d": "RER D"}
COULEURS = {"rer_a": "#E3051C", "rer_b": "#3F7DD0", "rer_d": "#00A88F"} #Les couleurs choises pour la représentation sont proches des originales
TRANCHES = ["Pointe matin", "Heures creuses", "Pointe soir", "Soirée", "Week-end"] #On étudie l'impact des tranches horraires sur le retard des RER


def charger():
    """Tous les arrêts, et les arrêts non supprimés. On ne prend pas en compte les arrêts supprimés, puisqu'ils se voient accorder un retard de 0 dans les données."""
    fichiers = [DATA / f"clean_rer_{l}.parquet" for l in "abd"]
    if all(f.exists() for f in fichiers):
        df = pd.concat([pd.read_parquet(f) for f in fichiers], ignore_index=True)
    else:  # fichiers absents : on les régénère
        try:
            from src.nettoyage import charger_donnees_propres
        except ImportError:
            from nettoyage import charger_donnees_propres
        df = pd.concat(charger_donnees_propres()[:3], ignore_index=True)
    return df, df[~df["est_supprime"]]


def graphique(tableau, titre, unite, fichier):
    """Un petit graphique par colonne du tableau, une barre par ligne de RER, même échelle partout."""
    fig, axes = plt.subplots(1, tableau.shape[1], figsize=(max(6, 2.8 * tableau.shape[1]), 4.5), sharey=True)
    for ax, (nom, valeurs) in zip(axes, tableau.items()):
        barres = ax.bar([LIGNES[l] for l in valeurs.index], valeurs, color=[COULEURS[l] for l in valeurs.index])
        ax.bar_label(barres, fmt="%.1f", padding=3)
        ax.set_title(nom)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.margins(y=0.15)
    axes[0].set_ylabel(unite)
    fig.suptitle(titre, fontweight="bold")
    fig.tight_layout()
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{fichier}.png", dpi=150)


if __name__ == "__main__":
    df_all, df = charger()
    print(f"Période : du {df['date'].min():%d/%m/%Y} au {df['date'].max():%d/%m/%Y}")
    print(df.groupby("line").agg(gares=("stop_name", "nunique"), arrets=("stop_name", "size")), "\n")

    # 1. Distribution des retards (min) : les centiles montrent les perturbations graves
    r = df.groupby("line")["retard_min"]
    retards = pd.DataFrame({"Moyenne": r.mean(), "Médiane": r.median(),
                            "P90": r.quantile(0.9), "P95": r.quantile(0.95)})
    graphique(retards, "Retards sur le tronçon central", "Retard (min)", "1_retards")
    # Contrôle à Châtelet, seule gare commune aux 3 lignes
    chatelet = df[df["stop_name"] == "Châtelet-Les Halles"].groupby("line")["retard_min"].mean()

    # 2. Retard ajouté à chaque arrêt (s), dans le tunnel ou ailleurs
    tunnel = df.groupby(["line", "zone_tunnel"])["delay_added_sec"].mean().unstack()
    tunnel.columns = ["Hors tunnel", "Dans le tunnel"]
    graphique(tunnel, "Retard ajouté par arrêt", "Secondes", "2_tunnel")

    # Dans le tunnel : vers le Nord on sort à Gare du Nord, vers le Sud à Châtelet (B et D seulement)
    bd = df[df["zone_tunnel"] & (df["stop_order"] > 1) & df["direction"].isin(["Nord", "Sud"])]
    sortie = ((bd["direction"] == "Nord") & (bd["stop_name"] == "Gare du Nord")) | \
             ((bd["direction"] == "Sud") & (bd["stop_name"] == "Châtelet-Les Halles"))
    sens = bd.groupby(["line", sortie.map({False: "Entrée", True: "Sortie"})])["delay_added_sec"].mean().unstack()
    graphique(sens, "Retard ajouté à l'entrée et à la sortie du tunnel", "Secondes", "5_sens_tunnel")

    # 3. Retard moyen (min) selon le moment de la journée, et hausse en pointe (semaine)
    tranches = df.groupby(["line", "tranche_horaire"])["retard_min"].mean().unstack()[TRANCHES]
    graphique(tranches, "Retard moyen selon le moment de la journée", "Retard (min)", "3_tranches")
    hausse_pointe = df[df["heure_pointe"]].groupby("line")["retard_min"].mean() - tranches["Heures creuses"]

    # 4. Trains (%) dont tous les arrêts sont annulés (supprimés) ou une partie (limités)
    annule = df_all.groupby(["line", "date", "journey_id"])["est_supprime"].mean()
    suppr = pd.DataFrame({"Supprimés": (annule == 1).groupby("line").mean() * 100,
                          "Limités": ((annule > 0) & (annule < 1)).groupby("line").mean() * 100})
    graphique(suppr, "Trains supprimés ou limités", "% des trains", "4_suppressions")

    # 5. Retard moyen par jour : l'écart vient-il de quelques journées exceptionnelles ?
    par_jour = df.groupby(["date", "line"])["retard_min"].mean().unstack()
    ax = par_jour.rename(columns=LIGNES).rename_axis(columns=None).plot(figsize=(10, 4.5), color=list(COULEURS.values()),
                                              title="Retard moyen par jour", ylabel="Retard (min)", xlabel="")
    ax.axhline(5, color="grey", linestyle="--")  # seuil choisi des "mauvais jours"
    plt.savefig(FIGURES / "6_retard_par_jour.png", dpi=150)

    recap = pd.DataFrame({
        "Retard moyen (min)": retards["Moyenne"],
        "Retard P95 (min)": retards["P95"],
        "Retard moyen à Châtelet (min)": chatelet,
        "Retard moyen d'une journée type (min)": par_jour.median(),
        "Jours à plus de 5 min de retard moyen": (par_jour > 5).sum(),
        "Retard ajouté dans le tunnel (s/arrêt)": tunnel["Dans le tunnel"],
        "Retard ajouté en sortie de tunnel (s/arrêt)": sens["Sortie"],
        "Hausse en heure de pointe (min)": hausse_pointe,
        "Trains supprimés (%)": suppr["Supprimés"],
        "Trains limités en parcours (%)": suppr["Limités"],
    }).T.rename(columns=LIGNES).rename_axis(columns=None).round(1).fillna("-")
    recap["Conclusion"] = [
        "B et D sont en moyenne bien plus en retard que A",
        "Les gros retards sont près de 2 fois plus forts sur B et D",
        "Même constat dans la gare commune aux 3 lignes",
        "Même un jour ordinaire, B et D sont 2 à 3 fois plus en retard que A",
        "Aucune journée noire sur A, plusieurs sur B et D (à étudier dans l'axe 3)",
        "A rattrape du retard dans Paris, B et D en prennent",
        "Le retard se prend à la sortie du tunnel (A non concerné)",
        "L'heure de pointe pèse environ 2 fois plus sur B et D",
        "Plus de suppressions sur D",
        "B et D sont bien plus souvent retournés avant le tunnel",
    ]
    print(recap.to_string())

    # Tableau récapitulatif disponible dans docs/figures/7_recap
    fig, ax = plt.subplots(figsize=(14, 4.5))
    ax.axis("off")
    table = ax.table(cellText=recap.values, rowLabels=recap.index, colLabels=recap.columns,
                     loc="center", cellLoc="center", rowLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)                                          
    table.auto_set_column_width(range(-1, recap.shape[1]))       
    ax.set_title("Axe 1 : tableau récapitulatif", fontweight="bold")
    fig.savefig(FIGURES / "7_recap.png", dpi=150, bbox_inches="tight")
    plt.show()
