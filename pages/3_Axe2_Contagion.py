import pandas as pd
import plotly.express as px
import streamlit as st

from src.Axe1_constat_naif import COULEURS
from src.axe2_contagion import grille_15min, temps_de_retour
from src.dashboard_utils import filtres_sidebar, mise_en_page, tracer_barres

st.title("Axe 2 : Contagion")
st.write(
    "Mesure du lien entre les retards du `RER B` et du `RER D` à `Châtelet-Les Halles` par fenêtres de `15 minutes` "
    "(corrélation brute, corrélation hors effet d'heure et temps médian pour repasser sous `3 min` après un pic `> 10 min`). "
    "Les deux graphiques analysent le décalage temporel entre lignes et le retard moyen subi selon l'état de la ligne déclencheuse."
)
_, df, _ = filtres_sidebar()

chat = grille_15min(df[df["stop_name"] == "Châtelet-Les Halles"])
if not {"rer_a", "rer_b", "rer_d"}.issubset(chat.columns) or len(chat) < 10:
    st.info("Pas assez de passages simultanés sur A, B et D à Châtelet.")
    st.stop()


def fmt_min(v):
    return "-" if pd.isna(v) else f"{v:.0f} min"


corr = chat.corr()
corr_res = (chat - chat.groupby(chat.index.hour).transform("mean")).corr()
ret = {l: temps_de_retour(chat[l]).median() for l in ["rer_a", "rer_b", "rer_d"]}

m1, m2, m3 = st.columns(3)
m1.metric("Corrélation B / D", f"{corr.loc['rer_b', 'rer_d']:.2f}", f"Placebo B / A : {corr.loc['rer_b', 'rer_a']:.2f}", delta_color="off")
m2.metric("Corrélation hors heure", f"{corr_res.loc['rer_b', 'rer_d']:.2f}", f"Placebo B / A : {corr_res.loc['rer_b', 'rer_a']:.2f}", delta_color="off")
m3.metric("Retour médian (> 10 min)", f"B {fmt_min(ret['rer_b'])} / D {fmt_min(ret['rer_d'])}", f"RER A : {fmt_min(ret['rer_a'])}", delta_color="off")

decals = list(range(-4, 5))
df_dec = pd.DataFrame({
    "B(t) -> D(t + Δ)": [chat["rer_b"].corr(chat["rer_d"].shift(-d)) for d in decals],
    "B(t) -> A(t + Δ)": [chat["rer_b"].corr(chat["rer_a"].shift(-d)) for d in decals],
}, index=[d * 15 for d in decals])
fig_dec = px.line(
    df_dec, markers=True, title="Corrélation décalée à Châtelet (15 min)",
    color_discrete_map={"B(t) -> D(t + Δ)": COULEURS["rer_d"], "B(t) -> A(t + Δ)": COULEURS["rer_a"]},
)
fig_dec.add_vline(x=0, line_dash="dash", line_color="grey")
mise_en_page(fig_dec, "Corrélation")
fig_dec.update_xaxes(title_text="Décalage (min)", tickvals=[d * 15 for d in decals])

_, col_sel = st.columns(2)
decl = col_sel.radio("Ligne déclencheuse", ["RER B", "RER D"], horizontal=True)
src = "rer_b" if decl == "RER B" else "rer_d"
tgt = "rer_d" if decl == "RER B" else "rer_b"
etats = pd.cut(chat[src], [-999, 3, 10, 999], labels=["Fluide (< 3 min)", "Ralenti (3-10 min)", "Perturbé (> 10 min)"])
dom = chat.groupby(etats, observed=False)[[tgt, "rer_a"]].mean().T

c1, c2 = st.columns(2)
c1.plotly_chart(fig_dec, width="stretch")
c2.plotly_chart(tracer_barres(dom, f"Retard selon l'état du {decl}", "Retard moyen (min)"), width="stretch")

st.divider()
st.markdown(
    """
**À retenir** (données du 02/10 au 26/11/2026) :

- Les retards de B et D **évoluent ensemble** (corrélation 0,26 contre 0,08 avec A), même sans l'effet commun de l'heure de pointe (0,22 contre 0,02).
- Le retard de B se retrouve sur D **15 minutes plus tard**, et l'effet joue dans les deux sens.
- Quand B est perturbé, le retard de D passe de 2,3 à **7,4 min** ; A reste vers 1 min.
- B est le plus lent à se remettre : **150 min** en médiane après un pic, contre environ 70 pour A et D.
"""
)
