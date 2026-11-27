import streamlit as st

st.set_page_config(page_title="Projet RER — Tunnel B / D", layout="wide")

st.title("L'effet domino dans le tunnel RER B / RER D")
st.write("Projet Python pour la data science — ENSAE 2A")

st.divider()

st.header("Problématique")
st.write(
    "Entre `Châtelet-Les Halles` et `Gare du Nord`, le `RER B` et le `RER D` partagent les mêmes voies au cœur "
    "de l'un des tronçons ferroviaires les plus fréquentés d'Europe. En raison des contraintes de signalisation, "
    "ce tunnel ne peut accueillir que `6 à 7 trains` simultanément. Ce goulot d'étranglement est bien connu des usagers "
    "pour créer un **effet domino** : dès qu'un incident ou un ralentissement survient sur l'une des deux lignes, "
    "les trains sont retenus en amont, le tube sature et la perturbation se propage à l'autre ligne, rendant la "
    "régulation difficile et le retour à la normale beaucoup plus long."
)
st.write(
    "Le projet consiste donc à **vérifier cet effet domino à partir des données et surtout à le quantifier** : "
    "quel est le surcroît de retard réellement généré dans le tunnel ? Dans quelle mesure et avec quel décalage "
    "un incident sur une ligne affecte-t-il l'autre ? Combien de temps supplémentaire faut-il pour résorber "
    "une perturbation ?"
)
st.write(
    "Pour isoler ce qui relève spécifiquement du partage des voies, toute notre analyse s'appuie sur une comparaison "
    "avec le `RER A`. Cette ligne constitue un point de référence fiable : elle supporte une fréquentation et une "
    "cadence tout aussi élevées et dessert également `Châtelet-Les Halles`, mais dispose de ses propres voies "
    "indépendantes. Comparer le `RER B` et le `RER D` au `RER A` permet ainsi de chiffrer l'impact propre du tunnel "
    "(par exemple un temps de reprise après incident nettement plus lent en heure de pointe que sur une ligne indépendante)."
)

st.divider()

st.header("Données et périmètre")
st.write(
    "Les données proviennent de l'API temps réel `PRIM` d'Île-de-France Mobilités, collectée toutes les `2 minutes` "
    "entre le `02/10/2026` et le `26/11/2026`, croisée avec les messages d'incidents RATP (`1 565` alertes)."
)
st.write(
    "L'analyse porte sur les gares du tronçon central et de la petite couronne autour du tunnel "
    "(`12` gares sur le `RER B`, `5` sur le `RER D` et `5` sur le `RER A`), en comparant les horaires théoriques "
    "aux horaires estimés en temps réel ainsi que les suppressions de trains."
)

st.divider()

st.header("Démarche et axes d'analyse")
st.write("L'étude s'articule autour de trois axes :")
st.write(
    "- **Axe 1 — Constat :** comparer les niveaux de retard globaux et extrêmes (`P90`, `P95`) des `RER B` et `RER D` "
    "à ceux du `RER A`, isoler le retard pris spécifiquement à l'entrée et à la sortie du tunnel, et mesurer "
    "le poids des heures de pointe ainsi que des suppressions et limitations de parcours."
)
st.write(
    "- **Axe 2 — Contagion :** tester si les retards du `RER B` et du `RER D` à `Châtelet-Les Halles` évoluent de manière "
    "synchronisée (corrélation brute et hors effet d'heure), mesurer le décalage temporel entre les deux lignes, "
    "et évaluer leur temps de retour à la normale après un pic de perturbation face au `RER A`."
)
st.write(
    "- **Axe 3 — Incidents :** détecter automatiquement les principaux épisodes de crise dans le tunnel "
    "(chute de débit, pics de retard, suppressions), les croiser avec les alertes trafic officielles, "
    "et observer la rétention des trains à l'aide de diagrammes espace-temps (`Marey`)."
)

st.divider()

st.header("Navigation")
st.write("- `Dashboard` : graphiques et tableaux récapitulatifs des trois axes d'analyse.")
st.write("- `Visualisations` : replay interactif sur carte pour suivre la circulation des trains et la saturation du tunnel avant et pendant un incident.")