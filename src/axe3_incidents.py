####################################################################################################################################
# AXE 3 : détection automatique des principaux incidents passés
# Repère les épisodes où le débit dans le tunnel chute et/ou le retard explose sur B et D,
# puis croise ces épisodes avec les messages officiels (clean_incidents) et trace un diagramme de Marey.
# tableau récapitulatif + graphiques dans docs/figures/ (fichiers axe3_*)
####################################################################################################################################

import re
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from src.Axe1_constat_naif import COULEURS, DATA, FIGURES, LIGNES, charger
    from src.axe2_contagion import finir
    from src.nettoyage import GARES_CENTRALES, charger_donnees_propres
except ImportError:
    from Axe1_constat_naif import COULEURS, DATA, FIGURES, LIGNES, charger
    from axe2_contagion import finir
    from nettoyage import GARES_CENTRALES, charger_donnees_propres


def charger_incidents():
    """Lire clean_incidents.parquet et convertir l'horodatage en Europe/Paris."""
    chemin = DATA / "clean_incidents.parquet"
    df_inc = pd.read_parquet(chemin) if chemin.exists() else charger_donnees_propres()[3]
    df_inc = df_inc.copy()
    df_inc["first_seen_paris"] = pd.to_datetime(
        df_inc["first_seen"], format="ISO8601", utc=True, errors="coerce"
    ).dt.tz_convert("Europe/Paris")
    return df_inc


def series_tunnel(df_all):
    """Séries par tranches de 15 min à Châtelet : fréquence, retard moyen, suppressions et débit de référence B+D."""
    chat = df_all[df_all["stop_name"] == "Châtelet-Les Halles"].copy()
    chat["fenetre"] = chat["aimed_time"].dt.floor("15min")
    valide = chat[~chat["est_supprime"]]

    freq = valide.groupby(["fenetre", "line"])["journey_id"].nunique().unstack().asfreq("15min").fillna(0)
    retard = valide.groupby(["fenetre", "line"])["retard_min"].mean().unstack().asfreq("15min")
    suppr = chat.groupby(["fenetre", "line"])["est_supprime"].mean().unstack().asfreq("15min")

    creneau = [freq.index.day_of_week < 5, freq.index.time]
    freq_ref_bd = (freq["rer_b"] + freq["rer_d"]).groupby(creneau).transform("median").replace(0, np.nan)
    return freq, retard, suppr, freq_ref_bd


def extraire_cause(df_inc, debut, fin, pic_b, pic_d):
    """Identifier la cause officielle la plus probable sur le créneau de l'incident."""
    m = df_inc[
        (df_inc["line"] == "rer_b")
        & (df_inc["first_seen_paris"] >= debut - pd.Timedelta("45min"))
        & (df_inc["first_seen_paris"] <= fin + pd.Timedelta("30min"))
    ]
    m = m[~m["short_message"].fillna("").str.contains(r"travaux|Jusqu'au|à partir de|accès.*ferm", case=False, regex=True)]
    m_prio = m[m["short_message"].fillna("").str.contains(
        r"perturbé|interrompu|stationne|panne|alarme|accident|incident|sécurité|colis|malaise|arbre",
        case=False, regex=True,
    )]
    msgs = m_prio if not m_prio.empty else m
    for txt in msgs["short_message"].dropna():
        match = re.search(r"\(([^)]+)\)", txt)
        if match:
            cause = match.group(1).strip()
            return cause[:36] + "..." if len(cause) > 39 else cause
    if pic_d >= 15 and pic_b < 10:
        return "Incident RER D (flux SNCF)"
    return "Non renseigné"


def detecter_incidents(df_all, df_inc, top=10):
    """Détecter et classer les principaux épisodes de crise dans le tunnel B / D."""
    freq, retard, suppr, freq_ref_bd = series_tunnel(df_all)
    heure = freq.index.hour + freq.index.minute / 60
    ratio_freq = (freq["rer_b"] + freq["rer_d"]) / freq_ref_bd
    retard_bd = retard[["rer_b", "rer_d"]].max(axis=1)
    suppr_bd = suppr[["rer_b", "rer_d"]].mean(axis=1)

    crise = (heure >= 6.5) & (heure <= 21.5) & ((retard_bd > 10) | ((ratio_freq < 0.5) & (retard_bd > 6)) | (suppr_bd > 0.25))
    idx = freq.index[crise]
    episodes = []
    if len(idx):
        deb = fin = idx[0]
        for ts in idx[1:]:
            if (ts - fin) <= pd.Timedelta("45min"):
                fin = ts
            else:
                episodes.append((deb, fin))
                deb = fin = ts
        episodes.append((deb, fin))

    rows = []
    for deb, fin in episodes:
        duree = int((fin - deb).total_seconds() / 60) + 15
        if duree < 45:
            continue
        sl = slice(deb, fin)
        pic_b, pic_d, pic_a = retard.loc[sl, "rer_b"].max(), retard.loc[sl, "rer_d"].max(), retard.loc[sl, "rer_a"].max()
        rows.append({
            "date": deb.strftime("%d/%m/%Y"),
            "debut": deb.strftime("%H:%M"),
            "fin": (fin + pd.Timedelta("15min")).strftime("%H:%M"),
            "debut_ts": deb,
            "fin_ts": fin + pd.Timedelta("15min"),
            "duree_min": duree,
            "pic_B": round(pic_b, 1),
            "pic_D": round(pic_d, 1),
            "pic_A": round(pic_a, 1),
            "freq_min_pct": round(ratio_freq.loc[sl].min() * 100),
            "suppr_max_pct": round(suppr_bd.loc[sl].max() * 100, 1),
            "contagion": bool(pic_b >= 10 and pic_d >= 10),
            "score": round(duree * (np.nan_to_num(pic_b) + np.nan_to_num(pic_d)) / 60, 1),
            "cause": extraire_cause(df_inc, deb, fin, pic_b, pic_d),
        })
    return pd.DataFrame(rows).sort_values("score", ascending=False).head(top).reset_index(drop=True)


if __name__ == "__main__":
    df_all, _ = charger()
    df_inc = charger_incidents()
    FIGURES.mkdir(parents=True, exist_ok=True)

    freq, retard, suppr, freq_ref_bd = series_tunnel(df_all)
    top8 = detecter_incidents(df_all, df_inc, top=8)

    # 1. Top 8 des incidents : pics de retard B et D vs A
    fig, ax = plt.subplots(figsize=(10, 5))
    y = np.arange(len(top8))
    h = 0.25
    ax.barh(y - h, top8["pic_B"], height=h, color=COULEURS["rer_b"], label="RER B")
    ax.barh(y, top8["pic_D"], height=h, color=COULEURS["rer_d"], label="RER D")
    ax.barh(y + h, top8["pic_A"], height=h, color=COULEURS["rer_a"], label="RER A")
    ax.set_yticks(y, [f"{r['date']} ({r['cause']})" for _, r in top8.iterrows()])
    ax.invert_yaxis()
    ax.set(xlabel="Pic de retard moyen sur 15 min à Châtelet (min)")
    ax.legend(frameon=False)
    finir(ax, "Principaux incidents détectés : B et D décrochent, A reste stable", "axe3_1_top_incidents")

    # 2. Zoom sur le plus gros incident de semaine avec contagion B + D : débit vs retard
    sem_bd = top8[top8["contagion"] & (top8["debut_ts"].dt.day_of_week < 5)]
    ep = sem_bd.iloc[0] if not sem_bd.empty else top8.iloc[0]
    t0, t1 = ep["debut_ts"] - pd.Timedelta("45min"), ep["fin_ts"] + pd.Timedelta("45min")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax1.plot(freq.loc[t0:t1].index, (freq["rer_b"] + freq["rer_d"]).loc[t0:t1], color="#1E293B", lw=2, label="Débit réel (B + D)")
    ax1.plot(freq.loc[t0:t1].index, freq_ref_bd.loc[t0:t1], color="grey", ls="--", label="Débit habituel")
    ax1.set(ylabel="Trains / 15 min")
    ax1.legend(frameon=False)
    ax1.spines[["top", "right"]].set_visible(False)

    ax2.plot(retard.loc[t0:t1].index, retard.loc[t0:t1, "rer_a"], color="lightgrey", label="RER A")
    ax2.plot(retard.loc[t0:t1].index, retard.loc[t0:t1, "rer_b"], color=COULEURS["rer_b"], lw=2, label="RER B")
    ax2.plot(retard.loc[t0:t1].index, retard.loc[t0:t1, "rer_d"], color=COULEURS["rer_d"], lw=2, label="RER D")
    ax2.set(ylabel="Retard moyen (min)")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=ep["debut_ts"].tzinfo))
    ax2.legend(frameon=False)
    fig.suptitle(f"Incident du {ep['date']} ({ep['cause']}) : chute de débit et retard à Châtelet", fontweight="bold")
    finir(ax2, "", "axe3_2_frequence_retard")

    # 3. Diagramme de Marey (espace-temps) sur le RER B sens Sud pendant cet incident
    gares_b = GARES_CENTRALES["b"]
    ordre_y = {g: i for i, g in enumerate(gares_b)}
    marey = df_all[
        (df_all["line"] == "rer_b") & (df_all["direction"] == "Sud")
        & df_all["expected_time"].between(ep["debut_ts"] - pd.Timedelta("30min"), ep["fin_ts"] + pd.Timedelta("30min"))
    ].sort_values(["journey_id", "stop_order"]).copy()
    marey["y"] = marey["stop_name"].map(ordre_y)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.axhspan(ordre_y["Châtelet-Les Halles"], ordre_y["Gare du Nord"], color="#FEE2E2", alpha=0.6, label="Tunnel B / D")
    for _, tr in marey.groupby("journey_id", sort=False):
        ok = tr[~tr["est_supprime"]]
        if len(ok) > 1 and ok["expected_time"].is_monotonic_increasing:
            ax.plot(ok["expected_time"], ok["y"], color=COULEURS["rer_b"], alpha=0.55, lw=1.3)
    annules = marey[marey["est_supprime"]]
    if not annules.empty:
        ax.scatter(annules["expected_time"], annules["y"], color=COULEURS["rer_a"], marker="x", s=35, zorder=5, label="Arrêt supprimé")
    ax.set_yticks(range(len(gares_b)), gares_b)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=ep["debut_ts"].tzinfo))
    ax.set(xlabel="Heure de passage (sens Nord -> Sud)")
    ax.legend(frameon=False, loc="upper left")
    finir(ax, f"Diagramme de Marey du {ep['date']} (RER B sens Sud) : trains retenus et supprimés", "axe3_3_marey")

    # 4. Tableau récapitulatif du Top 8
    recap = top8[["date", "duree_min", "pic_B", "pic_D", "pic_A", "freq_min_pct", "suppr_max_pct", "cause"]].copy()
    recap.insert(1, "Créneau", top8["debut"] + " - " + top8["fin"])
    recap.columns = ["Date", "Créneau", "Durée (min)", "Pic B (min)", "Pic D (min)", "Pic A (min)", "Débit min (%)", "Suppr. max (%)", "Cause (messages B)"]
    print(recap.to_string(index=False))

    fig, ax = plt.subplots(figsize=(14, 3.8))
    ax.axis("off")
    table = ax.table(cellText=recap.values, colLabels=recap.columns, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.55)
    table.auto_set_column_width(range(recap.shape[1]))
    ax.set_title("Axe 3 : principaux incidents détectés dans le tunnel", fontweight="bold")
    fig.savefig(FIGURES / "axe3_4_recap.png", dpi=150, bbox_inches="tight")
    plt.show()
