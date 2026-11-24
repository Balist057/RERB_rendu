# bot_collect

Collecteur temps réel des passages et incidents sur les RER A, B et D via l'API PRIM (Île-de-France Mobilités), avec écriture en Parquet partitionné par jour sur S3 (MinIO SSP Cloud) ou en local.

## Utilisation en local

```bash
pip install -r bot_collect/requirements.txt
python bot_collect/src/collector.py --once
```

Options :
- `--line {rer_a,rer_b,rer_d}` : collecter une seule ligne (par défaut : toutes)
- `--interval 120` : intervalle en secondes entre deux requêtes (défaut : `120`)
- `--once` : exécuter un seul cycle puis quitter

Variables d'environnement :
- `PRIM_API_KEY` (obligatoire) et `PRIM_API_KEY_2` (optionnelle, utilisée pour RER A et D).
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` (optionnelles ; sans elles, sauvegarde dans `bot_collect/data/`).
- `AWS_S3_ENDPOINT` (défaut : `minio.lab.sspcloud.fr`) et `S3_BUCKET` (défaut : `gpichonlegroux`).

## Déploiement SSP Cloud

L'image `ghcr.io/balist057/rerbcollect:latest` est construite par `.github/workflows/docker.yml` (via `bot_collect/deploy/Dockerfile`) et déployée avec `bot_collect/deploy/k8s-sspcloud.yaml`.
