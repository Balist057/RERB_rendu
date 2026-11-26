####################################################################################################################################
# AXE 2 : la contagion dans le tunnel
# Quand le RER B prend du retard, le RER D (qui partage les mêmes voies entre Châtelet et Gare du Nord) en prend-il aussi ?
# Le RER A sert de placebo : il passe aussi à Châtelet, mais sur ses propres voies.
# Méthode : retard moyen par fenêtres de 15 min, corrélations, décalage temporel (.shift()) et temps de retour à la normale.
# tableau récapitulatif + graphiques dans docs/figures/ (fichiers axe2_*)
####################################################################################################################################

import matplotlib.pyplot as plt
import pandas as pd

# import qui marche depuis la racine du dépôt (notebook, Streamlit) comme depuis src/ (python src/axe2_contagion.py)
try:
    from src.Axe1_constat_naif import COULEURS, FIGURES, LIGNES, charger
except ImportError:
    from Axe1_constat_naif import COULEURS, FIGURES, LIGNES, charger


def grille_15min(df):
    """Retard moyen par fenêtre de 15 min, une colonne par ligne (les fenêtres sans train restent vides)."""
    fenetre = df["aimed_time"].dt.floor("15min")   # heure prévue arrondie au quart d'heure inférieur (8h07 -> 8h00)
    # moyenne par (fenêtre, ligne), unstack -> une colonne par ligne,
    # asfreq ajoute les fenêtres sans train (vides) pour garder un pas régulier de 15 min, indispensable pour .shift()
    return df.groupby([fenetre, "line"])["retard_min"].mean().unstack().asfreq("15min")


def temps_de_retour(serie, pic=10, retour=3):
    """Durées (min) pour repasser sous 3 min de retard après un pic au-dessus de 10 min.
    Un épisode est abandonné s'il y a plus de 30 min sans train (nuit)."""
    durees = []
    debut = None   # indice de la fenêtre où le pic a commencé
    vides = 0      # nombre de fenêtres vides d'affilée
    for i, retard in enumerate(serie):
        if debut is None:            # pas d'épisode en cours : un pic commence-t-il ?
            if retard > pic:
                debut, vides = i, 0
        elif pd.isna(retard):        # fenêtre sans train
            vides += 1
            if vides > 2:            # plus de 30 min sans train : c'est la nuit, on abandonne l'épisode
                debut = None
        else:                        # fenêtre avec des trains
            vides = 0
            if retard < retour:      # retour à la normale : durée = nombre de fenêtres écoulées x 15 min
                durees.append((i - debut) * 15)
                debut = None
    return pd.Series(durees, dtype=float)


def finir(ax, titre, fichier):
    """Titre, style commun et enregistrement d'un graphique."""
    ax.set_title(titre, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.figure.tight_layout()
    ax.figure.savefig(FIGURES / f"{fichier}.png", dpi=150)


if __name__ == "__main__":
    _, df = charger()
    FIGURES.mkdir(parents=True, exist_ok=True)
    chatelet = grille_15min(df[df["stop_name"] == "Châtelet-Les Halles"])

    # 1. Corrélation des retards à Châtelet entre chaque paire de lignes (carte de chaleur)
    corr = chatelet.corr().rename(index=LIGNES, columns=LIGNES)   # matrice 3 x 3 des corrélations entre A, B et D
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    image = ax.imshow(corr, cmap="Blues", vmin=0, vmax=0.5)       # une case colorée par valeur, échelle de 0 à 0,5
    ax.set_xticks(range(3), corr.columns)
    ax.set_yticks(range(3), corr.index)
    for i in range(3):                                            # écrit la valeur dans chaque case
        for j in range(3):
            valeur = corr.iloc[i, j]
            ax.text(j, i, f"{valeur:.2f}", ha="center", va="center", color="white" if valeur > 0.3 else "black")
    fig.colorbar(image, ax=ax, shrink=0.8, label="Corrélation (fenêtres de 15 min)")
    finir(ax, "Les retards de B et D évoluent ensemble", "axe2_1_correlation")

    # Contrôle hors saisonnalité horaire (semaine/week-end + créneau de 15 min) et par sens
    creneau = [chatelet.index.day_of_week < 5, chatelet.index.time]
    residus = chatelet - chatelet.groupby(creneau).transform("mean")
    corr_res = residus.corr()

    df_ch = df[df["stop_name"] == "Châtelet-Les Halles"]
    corr_nord = grille_15min(df_ch[df_ch["direction"] == "Nord"])[["rer_b", "rer_d"]].corr().iloc[0, 1]
    corr_sud = grille_15min(df_ch[df_ch["direction"] == "Sud"])[["rer_b", "rer_d"]].corr().iloc[0, 1]

    # 2. Décalage : retard de B à l'instant t comparé au retard de D (ou A) à t + décalage
    decalages = range(-60, 75, 15)
    lags = pd.DataFrame(index=decalages)
    # shift(-1) avance la série de D d'une fenêtre : on compare B à l'instant t avec D à t + 15 min
    # (k // 15 = nombre de fenêtres de 15 min dans le décalage k)
    lags["B → D (tunnel)"] = [chatelet["rer_b"].corr(chatelet["rer_d"].shift(-k // 15)) for k in decalages]
    lags["B → A (placebo)"] = [chatelet["rer_b"].corr(chatelet["rer_a"].shift(-k // 15)) for k in decalages]
    meilleur = lags["B → D (tunnel)"].idxmax()   # décalage où le lien B → D est le plus fort

    fig, ax = plt.subplots(figsize=(8, 4.5))
    lags.plot(ax=ax, marker="o", color=[COULEURS["rer_d"], COULEURS["rer_a"]], linewidth=2)
    ax.axvline(0, color="grey", linewidth=0.8)
    ax.annotate(f"maximum : {meilleur:+d} min", (meilleur, lags.loc[meilleur].iloc[0]),
                textcoords="offset points", xytext=(10, -20))
    ax.set(xlabel="Décalage (min) : B en avance sur l'autre ligne si > 0", ylabel="Corrélation", xticks=list(decalages))
    ax.legend(frameon=False)
    finir(ax, "Le retard de B se retrouve sur D, pas sur A", "axe2_2_decalage")

    # 3. Contagion réciproque à Châtelet : état de B -> D vs A, et état de D -> B vs A
    bins = [-15, 3, 10, 180]
    etat_b = pd.cut(chatelet["rer_b"], bins=bins,
                    labels=["B fluide\n(< 3 min)", "B ralenti\n(3-10 min)", "B perturbé\n(> 10 min)"])
    etat_d = pd.cut(chatelet["rer_d"], bins=bins,
                    labels=["D fluide\n(< 3 min)", "D ralenti\n(3-10 min)", "D perturbé\n(> 10 min)"])
    selon_b = chatelet.groupby(etat_b, observed=False)[["rer_d", "rer_a"]].mean()
    selon_d = chatelet.groupby(etat_d, observed=False)[["rer_b", "rer_a"]].mean()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    selon_b.rename(columns=LIGNES).plot.bar(ax=ax1, color=[COULEURS["rer_d"], COULEURS["rer_a"]], rot=0)
    selon_d.rename(columns=LIGNES).plot.bar(ax=ax2, color=[COULEURS["rer_b"], COULEURS["rer_a"]], rot=0)
    for ax in (ax1, ax2):
        for barres in ax.containers:
            ax.bar_label(barres, fmt="%.1f", padding=3)
        ax.set(xlabel="", ylabel="Retard moyen à Châtelet (min)")
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False)
    ax1.set_title("Selon l'état du RER B")
    ax2.set_title("Selon l'état du RER D")
    fig.suptitle("Effet domino réciproque entre B et D (A reste stable)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIGURES / "axe2_3_etat_de_B.png", dpi=150)

    # 4. Exemple : la journée la plus perturbée à la fois sur B et sur D
    par_jour = chatelet.groupby(chatelet.index.date).mean()            # retard moyen de chaque journée
    # pour chaque jour on garde le plus petit retard entre B et D, puis le jour où ce minimum est le plus haut :
    # c'est la journée où B ET D sont tous les deux très perturbés
    jour_choisi = par_jour[["rer_b", "rer_d"]].min(axis=1).idxmax()
    jour = chatelet[chatelet.index.date == jour_choisi].dropna(how="all")   # fenêtres de ce jour, sans la nuit

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(jour.index, jour["rer_a"], color="lightgrey", label="RER A")
    ax.plot(jour.index, jour["rer_b"], color=COULEURS["rer_b"], linewidth=2, label="RER B")
    ax.plot(jour.index, jour["rer_d"], color=COULEURS["rer_d"], linewidth=2, label="RER D")
    ax.set(ylabel="Retard à Châtelet (min)")
    ax.legend(frameon=False)
    fig.autofmt_xdate()                                   # incline les heures pour qu'elles restent lisibles
    finir(ax, f"Le {jour_choisi:%d/%m/%Y}, journée la plus perturbée sur B et D", "axe2_4_journee")

    # 5. Résilience : part des pics (> 10 min) revenus sous 3 min après x minutes, sur tout le tronçon central
    troncon = grille_15min(df)
    retours = {ligne: temps_de_retour(troncon[ligne]) for ligne in LIGNES}   # durées de retour de chaque ligne

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for ligne, durees in retours.items():
        # durées triées : après le k-ième pic résorbé, la courbe vaut k / nombre de pics x 100 %
        durees = durees.sort_values().reset_index(drop=True)
        ax.step(durees, (durees.index + 1) / len(durees) * 100, where="post", linewidth=2,
                color=COULEURS[ligne], label=f"{LIGNES[ligne]} ({len(durees)} pics)")
    ax.axhline(50, color="grey", linestyle="--", linewidth=0.8)   # lecture de la médiane
    ax.set(xlabel="Temps depuis le début du pic (min)", ylabel="Pics résorbés (%)", xlim=(0, 600))
    ax.legend(frameon=False)
    finir(ax, "Retour sous 3 min de retard après un pic > 10 min", "axe2_5_resilience")

    # Tableau récapitulatif : B et D comparés au A
    recap = pd.DataFrame(index=["Tunnel (B et D)", "Référence (A)"])
    recap["Corrélation des retards à Châtelet"] = [corr.loc["RER B", "RER D"], corr.loc["RER B", "RER A"]]
    recap["Corrélation hors effet d'heure (résidus)"] = [corr_res.loc["rer_b", "rer_d"], corr_res.loc["rer_b", "rer_a"]]
    recap["Corrélation maximale (décalage ≤ 1 h)"] = [lags.iloc[:, 0].max(), lags.iloc[:, 1].max()]
    recap["Retard de l'autre ligne quand B est fluide (min)"] = [selon_b.iloc[0]["rer_d"], selon_b.iloc[0]["rer_a"]]
    recap["Retard de l'autre ligne quand B est perturbé (min)"] = [selon_b.iloc[2]["rer_d"], selon_b.iloc[2]["rer_a"]]
    recap["Retard de B (vs A) quand D est perturbé (min)"] = [selon_d.iloc[2]["rer_b"], selon_d.iloc[2]["rer_a"]]
    recap = recap.round(2)
    # colonnes en texte ajoutées après l'arrondi, car elles regroupent B et D dans une même case
    recap["Corrélation B / D par sens à Châtelet"] = [f"Sud {corr_sud:.2f} / Nord {corr_nord:.2f}", "-"]
    recap["Temps de retour médian après un pic (min)"] = [
        f"B {retours['rer_b'].median():.0f} / D {retours['rer_d'].median():.0f}", f"{retours['rer_a'].median():.0f}"]
    recap["Nombre de pics > 10 min"] = [f"B {len(retours['rer_b'])} / D {len(retours['rer_d'])}", len(retours["rer_a"])]
    recap = recap.T                    # transposée : une ligne par indicateur
    recap["Conclusion"] = [
        "Les retards de B et D évoluent ensemble, bien plus qu'avec A",
        "Sans la pointe commune, le lien avec A disparaît (pas entre B et D)",
        f"Le lien B → D est maximal avec {meilleur} min de décalage",
        "Point de comparaison : retard habituel de chaque ligne",
        "D décroche quand B est perturbé, A reste stable",
        "La contagion est réciproque : D perturbé entraîne aussi B",
        "Contagion plus de 2 fois plus forte en sens Sud",
        "B met 2 fois plus de temps que A à revenir à la normale, D un peu plus",
        "Les pics sont 3 à 4 fois plus fréquents sur B et D",
    ]
    print(recap.to_string())

    fig, ax = plt.subplots(figsize=(14, 4.5))
    ax.axis("off")                    
    table = ax.table(cellText=recap.values, rowLabels=recap.index, colLabels=recap.columns,
                     loc="center", cellLoc="center", rowLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)                
    table.auto_set_column_width(range(-1, recap.shape[1]))   
    ax.set_title("Axe 2 : tableau récapitulatif", fontweight="bold")
    fig.savefig(FIGURES / "axe2_6_recap.png", dpi=150, bbox_inches="tight")
    plt.show()
