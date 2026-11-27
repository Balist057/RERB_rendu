####################################################################################################################################
# RÉGRESSION LINÉAIRE : estimation économétrique de l'effet tunnel et de la contagion B <-> D
# Modèle 1 (séries 15 min à Châtelet, MCO + Newey-West HAC) : transmission dynamique B <-> D vs placebo A, avec contrôle d'inertie.
# Modèle 2 (arrêts hors 1er arrêt, Diff-in-Diff + HC3) : surcoût causal du tunnel sur le retard ajouté (delay_added_sec).
# tableau récapitulatif + graphiques dans docs/figures/ (fichiers reg_*)
####################################################################################################################################

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

try:
    from src.Axe1_constat_naif import COULEURS, FIGURES, charger
    from src.axe2_contagion import finir, grille_15min
except ImportError:
    from Axe1_constat_naif import COULEURS, FIGURES, charger
    from axe2_contagion import finir, grille_15min


def estimer_contagion(df):
    """Estimer la contagion dynamique à Châtelet (fenêtres 15 min) avec erreurs-types HAC."""
    chat = grille_15min(df[df["stop_name"] == "Châtelet-Les Halles"])
    reg = pd.DataFrame({
        "D": chat["rer_d"],
        "B": chat["rer_b"],
        "A": chat["rer_a"],
        "B_lag1": chat["rer_b"].shift(1),
        "B_lag2": chat["rer_b"].shift(2),
        "D_lag1": chat["rer_d"].shift(1),
        "D_lag2": chat["rer_d"].shift(2),
        "A_lag1": chat["rer_a"].shift(1),
        "heure": chat.index.hour,
        "weekend": (chat.index.day_of_week >= 5).astype(int),
    }).dropna()

    hac = {"cov_type": "HAC", "cov_kwds": {"maxlags": 4}}
    return {
        "B -> D (DL)": smf.ols("D ~ B + B_lag1 + B_lag2 + C(heure) + weekend", data=reg).fit(**hac),
        "B -> D (+D_lag1)": smf.ols("D ~ B + B_lag1 + D_lag1 + C(heure) + weekend", data=reg).fit(**hac),
        "B -> A (placebo)": smf.ols("A ~ B + B_lag1 + B_lag2 + C(heure) + weekend", data=reg).fit(**hac),
        "B -> A (+A_lag1)": smf.ols("A ~ B + B_lag1 + A_lag1 + C(heure) + weekend", data=reg).fit(**hac),
        "D -> B (DL)": smf.ols("B ~ D + D_lag1 + D_lag2 + C(heure) + weekend", data=reg).fit(**hac),
        "D -> B (+B_lag1)": smf.ols("B ~ D + D_lag1 + B_lag1 + C(heure) + weekend", data=reg).fit(**hac),
    }


def estimer_did_tunnel(df):
    """Estimer l'effet propre du tunnel sur le retard ajouté (Diff-in-Diff, erreurs-types HC3)."""
    df2 = df[df["stop_order"] > 1].copy()
    df2["tunnel"] = df2["zone_tunnel"].astype(int)
    df2["is_b"] = (df2["line"] == "rer_b").astype(int)
    df2["is_d"] = (df2["line"] == "rer_d").astype(int)
    return smf.ols("delay_added_sec ~ tunnel * is_b + tunnel * is_d + C(tranche_horaire)", data=df2).fit(cov_type="HC3")


def format_pval(p):
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


if __name__ == "__main__":
    _, df = charger()
    FIGURES.mkdir(parents=True, exist_ok=True)

    modeles = estimer_contagion(df)
    m_did = estimer_did_tunnel(df)

    # 1. Coefficients dynamiques de contagion (t, t-15 min, t-30 min) avec IC 95 % HAC
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    horizons = np.arange(3)
    specs = [
        ("B -> D (DL)", ["B", "B_lag1", "B_lag2"], COULEURS["rer_d"], -0.15, "B → D (tunnel)"),
        ("D -> B (DL)", ["D", "D_lag1", "D_lag2"], COULEURS["rer_b"], 0.0, "D → B (tunnel)"),
        ("B -> A (placebo)", ["B", "B_lag1", "B_lag2"], COULEURS["rer_a"], 0.15, "B → A (placebo)"),
    ]
    for nom, cols, couleur, decal, label in specs:
        m = modeles[nom]
        coefs = [m.params[c] for c in cols]
        errs = [1.96 * m.bse[c] for c in cols]
        ax.errorbar(horizons + decal, coefs, yerr=errs, fmt="o", color=couleur, capsize=4, lw=2, label=label)

    ax.axhline(0, color="grey", ls="--", lw=0.9)
    ax.set_xticks(horizons, ["Instantané (t)", "Décalé (t - 15 min)", "Décalé (t - 30 min)"])
    ax.set(ylabel="Coefficient OLS (min de retard / min)", ylim=(-0.06, 0.30))
    ax.legend(frameon=False)
    finir(ax, "Transmission dynamique des retards à Châtelet (MCO + contrôle heure/week-end)", "reg_1_contagion")

    # 2. Diff-in-Diff sur le retard ajouté à chaque arrêt (IC 95 % HC3)
    termes = ["tunnel", "tunnel:is_b", "tunnel:is_d"]
    noms_did = ["Effet Châtelet\nsur RER A (réf.)", "Surcoût net tunnel\nRER B (tunnel × B)", "Surcoût net tunnel\nRER D (tunnel × D)"]
    vals = [m_did.params[t] for t in termes]
    errs = [1.96 * m_did.bse[t] for t in termes]
    couleurs_did = [COULEURS["rer_a"], COULEURS["rer_b"], COULEURS["rer_d"]]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    barres = ax.bar(noms_did, vals, yerr=errs, capsize=5, color=couleurs_did, width=0.55)
    for b, v, e in zip(barres, vals, errs):
        y_txt = v + e + 2 if v >= 0 else v - e - 5
        ax.text(b.get_x() + b.get_width() / 2, y_txt, f"{v:+.1f} s", ha="center", va="center", fontweight="bold")
    ax.axhline(0, color="black", lw=0.8)
    ax.set(ylabel="Retard ajouté par arrêt (secondes)", ylim=(-28, 66))
    finir(ax, "Différence-en-Différences : surcoût causal du tunnel partagé", "reg_2_did_tunnel")

    # 3. Tableau récapitulatif économétrique
    lignes_recap = [
        ("B → D (retard B à t)", modeles["B -> D (DL)"], "B", "Effet immédiat significatif (+0,16 min/min)"),
        ("B → D (retard B à t-15 min)", modeles["B -> D (DL)"], "B_lag1", "La contagion se prolonge 15 min après"),
        ("B → D (+ contrôle D_lag1)", modeles["B -> D (+D_lag1)"], "B_lag1", "Reste significatif même à inertie de D fixée"),
        ("B → A placebo (retard B à t)", modeles["B -> A (placebo)"], "B", "Effet nul sur le RER A (test placebo validé)"),
        ("D → B (retard D à t-15 min)", modeles["D -> B (DL)"], "D_lag1", "Contagion réciproque significative vers le B"),
        ("DiD tunnel sur RER B (s)", m_did, "tunnel:is_b", "Surcoût net du tunnel par rapport au A"),
        ("DiD tunnel sur RER D (s)", m_did, "tunnel:is_d", "Surcoût net maximal pour le RER D"),
    ]
    rows = []
    for lib, mod, var, concl in lignes_recap:
        b, se, p = mod.params[var], mod.bse[var], mod.pvalues[var]
        rows.append({
            "Spécification": lib,
            "Coef": f"{b:+.3f}" if "DiD" not in lib else f"{b:+.1f} s",
            "IC 95 %": f"[{b - 1.96 * se:+.3f}, {b + 1.96 * se:+.3f}]" if "DiD" not in lib else f"[{b - 1.96 * se:+.1f}, {b + 1.96 * se:+.1f}]",
            "p-value": format_pval(p),
            "R²": f"{mod.rsquared:.3f}",
            "Conclusion": concl,
        })
    recap = pd.DataFrame(rows)
    print(recap.to_string(index=False))

    fig, ax = plt.subplots(figsize=(14, 3.8))
    ax.axis("off")
    table = ax.table(cellText=recap.values, colLabels=recap.columns, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.55)
    table.auto_set_column_width(range(recap.shape[1]))
    ax.set_title("Régressions linéaires : contagion (HAC) et effet tunnel (Diff-in-Diff HC3)", fontweight="bold")
    fig.savefig(FIGURES / "reg_3_recap.png", dpi=150, bbox_inches="tight")
    plt.show()
