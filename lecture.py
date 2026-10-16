import duckdb
import pandas as pd
import datetime

"""
TYPE S3: Indique que le secret s'applique au protocole s3://
KEY_ID '' et SECRET '': Identifiant vide car l'accès est anonyme (public)
ENDPOINT 'minio.lab.sspcloud.fr': Redirige les requêtes du S3 officiel AWS vers le MinIO du SSP Cloud
URL_STYLE 'path': Force l'utilisation d'une structure d'URL par chemin (http://endpoint/bucket)
"""
duckdb.execute("CREATE OR REPLACE SECRET (TYPE S3, KEY_ID '', SECRET '', ENDPOINT 'minio.lab.sspcloud.fr', URL_STYLE 'path');")

def read_data(ligne, date):
    """Lire la table de donnees d'une ligne a une date"""
    return duckdb.sql(f"SELECT * FROM 's3://gpichonlegroux/rer-{ligne}/date={date}/part-0.parquet'").df()

def read_data_ligne(ligne):
    """Lire l'integralite des donnees d'une ligne sur toutes les dates"""
    return duckdb.sql(f"SELECT * FROM 's3://gpichonlegroux/rer-{ligne}/date=*/*.parquet' ORDER BY date DESC").df()

def save_data(ligne):
    """Sauvegarder un dataset localement avec la date du jour pour éviter de requeter le serveur a chaque fois"""
    df = read_data_ligne(ligne)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    file_path = f"data/rer_{ligne}_{today}.parquet"
    
    df.to_parquet(file_path, index=False)
    print(f"Données sauvegardées : {file_path}")