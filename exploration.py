import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_parquet("data/rer_b_2026-10-16.parquet")
df["total_delay_sec"].plot.hist(bins=100, edgecolor='black', log=True)
plt.title("Distribution des retards cumulés (Échelle Log)")
plt.xlabel("Retard total (secondes)")
plt.ylabel("Fréquence (log)")
plt.show()