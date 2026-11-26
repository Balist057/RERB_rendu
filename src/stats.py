"On veut comparer le retard des lignes B et D avec celui de la ligne A"
"On cherche à vérifier l'hypothèse suivante : un incident sur le RER B ou D se propage rapidement à l'autre ligne en raison du tronçon commun, rendant la régulation plus complexe et les retards plus persistants"

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
FIGURES = Path(__file__).resolve().parent.parent / "docs" / "figures"
LIGNES = {"rer_a": "RER A", "rer_b": "RER B", "rer_d": "RER D"}

# Couleurs officielles des différents RER
COULEURS = {"rer_a": "#E3051C", "rer_b": "#3F7DD0", "rer_d": "#00A88F"}

#On regarde l'influence de la tranche horraire sur les retards
TRANCHES = ["Pointe matin", "Heures creuses", "Pointe soir", "Soirée", "Week-end"]


def charger(date=None):
    "Renvoie tous les arrêts et les arrêts non supprimés, il y a un retard de 0 sur les arrêts supprimés donc nous ne les prenons pas en compte"
    if date is not None:
        df = pd.concat([pd.read_parquet(DATA / f"clean_rer_{l}_{date}.parquet") for l in "abd"])
    else:
        fichiers = [sorted(DATA.glob(f"clean_rer_{l}_*.parquet")) for l in "abd"]
        if all(fichiers):
            df = pd.concat([pd.read_parquet(f[-1]) for f in fichiers])
        else:
            try:
                from src.nettoyage import charger_donnees_propres
            except ImportError:
                from nettoyage import charger_donnees_propres
            df_a, df_b, df_d, _ = charger_donnees_propres()
            df = pd.concat([df_a, df_b, df_d])
    return df, df[~df["est_supprime"]]


def graphique(tableau, titre, unite, fichier):
    """Un petit graphique par colonne du tableau, avec une barre par ligne de RER.
    Tous les graphiques partagent la même échelle pour être comparables."""
    fig, axes = plt.subplots(1, tableau.shape[1], figsize=(max(6, 2.8 * tableau.shape[1]), 4.5), sharey=True)
    for ax, (nom, valeurs) in zip(axes, tableau.items()):
        barres = ax.bar([LIGNES[l] for l in valeurs.index], valeurs,
                        color=[COULEURS[l] for l in valeurs.index], width=0.65)
        ax.bar_label(barres, fmt="%.1f", padding=3)          # valeur au bout de chaque barre
        ax.set_title(nom)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(left=False)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
        ax.margins(y=0.15)                                   # place pour les étiquettes
    axes[0].set_ylabel(unite)
    fig.suptitle(titre, fontweight="bold")
    fig.tight_layout()
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{fichier}.png", dpi=150)


if __name__ == "__main__":
    df_all, df = charger()
    par_ligne = df.groupby("line")

    # 1. Distribution des retards (minutes) : les centiles montrent les perturbations graves
    retards = pd.DataFrame({
        "Moyenne": par_ligne["retard_min"].mean(),
        "Médiane": par_ligne["retard_min"].median(),
        "P90": par_ligne["retard_min"].quantile(0.90),
        "P95": par_ligne["retard_min"].quantile(0.95),
    })
    graphique(retards, "Retards sur le tronçon central : B et D loin devant A", "Retard (minutes)", "1_retards")

    # Retard moyen à Châtelet-Les Halles, seule gare commune aux 3 lignes (pas de biais de longueur de tronçon)
    chatelet = df[df["stop_name"] == "Châtelet-Les Halles"].groupby("line")["retard_min"].mean()

    # 2. Retard ajouté à chaque arrêt (secondes), dans le tunnel (Châtelet, Gare du Nord) ou ailleurs
    tunnel = df.groupby(["line", "zone_tunnel"])["delay_added_sec"].mean().unstack()
    tunnel.columns = ["Hors tunnel", "Dans le tunnel"]
    graphique(tunnel, "Le tunnel fait perdre du temps à B et D, pas à A", "Retard ajouté par arrêt (s)", "2_tunnel")

    # 3. Retard moyen (minutes) selon le moment de la journée
    tranches = df.groupby(["line", "tranche_horaire"])["retard_min"].mean().unstack()[TRANCHES]
    graphique(tranches, "Retard moyen selon le moment de la journée", "Retard moyen (minutes)", "3_tranches")

    # Hausse du retard moyen en heure de pointe par rapport aux heures creuses (semaine)
    pointe = df[df["heure_pointe"]].groupby("line")["retard_min"].mean()
    hausse_pointe = pointe - tranches["Heures creuses"]

    # 4. Trains supprimés ou limités (%) : on regarde, pour chaque train, la part de ses arrêts annulés
    part_annulee = df_all.groupby(["line", "date", "journey_id"])["est_supprime"].mean()
    suppr = pd.DataFrame({
        "Supprimés": (part_annulee == 1).groupby("line").mean() * 100,          # tous les arrêts annulés
        "Limités en parcours": part_annulee.between(0, 1, inclusive="neither").groupby("line").mean() * 100,
    })
    graphique(suppr, "Trains supprimés ou retournés avant la fin du tronçon", "Part des trains (%)", "4_suppressions")

    # Tableau récapitulatif : une ligne par indicateur, une colonne par RER, puis la conclusion
    recap = pd.DataFrame({
        "Retard moyen (min)": retards["Moyenne"],
        "Retard P95 (min)": retards["P95"],
        "Retard moyen à Châtelet (min)": chatelet,
        "Retard ajouté dans le tunnel (s/arrêt)": tunnel["Dans le tunnel"],
        "Hausse en heure de pointe (min)": hausse_pointe,
        "Trains supprimés (%)": suppr["Supprimés"],
        "Trains limités en parcours (%)": suppr["Limités en parcours"],
    }).T.rename(columns=LIGNES).round(1)
    recap.columns.name = None

    recap["Conclusion"] = [
        "B et D sont en moyenne bien plus en retard que A",
        "Les gros retards sont près de 2 fois plus forts sur B et D",
        "Même constat dans la gare commune aux 3 lignes",
        "A rattrape du retard dans Paris, B et D en prennent",
        "L'heure de pointe pèse environ 2 fois plus sur B et D",
        "Plus de suppressions sur D",
        "B et D sont bien plus souvent retournés avant le tunnel",
    ]

    print(recap.to_string())
    plt.show()
