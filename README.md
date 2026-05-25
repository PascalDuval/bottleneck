# Projet Bottleneck - Consolidation

## Perimetre du projet

Ce projet couvre le perimetre Bottleneck : reconciliation des donnees ERP, web et liaison, puis production des artefacts de consolidation et de segmentation pour l'analyse metier.

Ce projet contient des scripts Python qui consolident des données ERP, liaison et web, puis exportent le résultat dans des fichiers Excel et CSV.

## Démarrage rapide

Si tu veux faire tourner le projet de bout en bout, voici l'ordre recommandé.

1. Cloner le dépôt.
2. Ouvrir un terminal PowerShell à la racine du projet.
3. Créer l'environnement virtuel avec `py -3 -m venv .venv`.
4. Activer l'environnement avec :
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
5. Installer les dépendances avec `pip install -r requirements.txt`.
6. Placer les fichiers d'entrée dans [data](data) ou dans [Kestra/incoming](Kestra/incoming) selon le mode d'exécution choisi.
7. Lancer le script adapté au besoin.

Ordre conseillé des scripts à exécuter :

1. [run_build.ps1](run_build.ps1) pour un lancement simple sous Windows.
2. [nettoyage_reconciliation.py](nettoyage_reconciliation.py) pour la version Pandas.
3. [nettoyage_reconciliation_DuckDB.py](nettoyage_reconciliation_DuckDB.py) pour la version DuckDB, recommandée.
4. Le workflow Kestra [Kestra/flows/orchestration_vins_duckdb.yaml](Kestra/flows/orchestration_vins_duckdb.yaml) si tu veux l'orchestration complète et visible.

En pratique, la version DuckDB est celle que je recommande pour vérifier le projet, car elle est plus lisible pour l'orchestration, plus robuste sur les gros volumes et plus proche d'un pipeline de production.

Il existe deux versions :
- **`nettoyage_reconciliation.py`** : version classique avec Pandas
- **`nettoyage_reconciliation_DuckDB.py`** : version avec DuckDB (recommandée pour les gros volumes)

## Architecture du Workflow

Le script `nettoyage_reconciliation_DuckDB.py` suit une architecture modulaire en **6 phases** :

### 🏗️ **PHASE 1 : INGESTION DES DONNÉES**
- Vérification de l'existence des fichiers d'entrée (ERP, WEB, LIAISON)
- Chargement des fichiers Excel en mémoire Pandas
- Initialisation de la base DuckDB
- Création des tables de staging brutes

### 🔧 **PHASE 2 : TRAITEMENT DES DONNÉES INDIVIDUELLES**
- **Contrôle des doublons globaux** sur les clés primaires
- **Sous-phase ERP** : Nettoyage, dédoublonnage, tests qualité
- **Sous-phase WEB** : Nettoyage (filtrage produits), dédoublonnage, tests qualité
- **Sous-phase LIAISON** : Nettoyage, dédoublonnage, tests qualité

### 🔗 **PHASE 3 : FUSION ET JONCTURE**
- Contrôle de cohérence des jointures (liaisons valides)
- Création de la table des liaisons valides
- Fusion finale ERP + LIAISON + WEB
- Tests de qualité de fusion

### 📊 **PHASE 4 : SCORES ET SEGMENTATION**
- Calcul du chiffre d'affaires par produit
- Calcul des statistiques de prix (moyenne, écart-type, quartiles)
- Attribution des z-scores et détection des outliers
- Segmentation : vins premium vs ordinaires
- Tests de qualité des scores

### 📋 **PHASE 5 : GÉNÉRATION DU RÉSUMÉ**
- Compilation de toutes les métriques finales
- Affichage du résumé complet du workflow

### 💾 **PHASE 6 : EXPORT DES FICHIERS EXTERNES**
- Export de la consolidation en Excel
- Export du CA par produit en Excel
- Export des vins premium en CSV
- Export des vins ordinaires en CSV

## Tests et Qualité des Données

Le script inclut des **tests automatiques** à chaque phase critique.
Ils sont exécutés **pendant l'exécution du script** via des `assert` Python.
Il ne s'agit **pas** d'une suite de tests `pytest` séparée : si une assertion échoue, le script s'arrête avec une erreur explicite.

### Tests ERP
- ✅ Aucun doublon sur `product_id`
- ✅ Pas de valeurs NULL critiques (`price`, `product_id`)
- ⚠️ Avertissement sur prix négatifs (acceptés pour analyse)

### Tests WEB
- ✅ Aucun doublon sur `sku`
- ✅ Seulement des produits (`post_type = 'product'`)
- ✅ SKU non NULL et non vides

### Tests LIAISON
- ✅ Aucun doublon sur `product_id`
- ✅ Pas de valeurs NULL (`product_id`, `id_web`)

### Tests de Fusion
- ✅ Toutes les liaisons ont une correspondance ERP
- ✅ Toutes les liaisons ont une correspondance WEB
- ✅ Nombre consolidé = nombre de liaisons valides

### Tests des Scores
- ✅ CA toujours positif
- ✅ Segmentation complète (premium + ordinaires = total)
- ✅ Vins premium respectent les critères (z-score > 2 ET prix > borne IQR)

## Structure du projet

- `nettoyage_reconciliation.py` : script principal (version Pandas)
- `nettoyage_reconciliation_DuckDB.py` : script utilisant DuckDB
- `data/` : dossier contenant les fichiers d'entrée Excel et les fichiers de sortie
  - attendus : `Fichier_erp.xlsx`, `Fichier_web.xlsx`, `fichier_liaison.xlsx`
- `requirements.txt` : dépendances Python nécessaires
- `run_build.ps1` : script PowerShell d'installation et d'exécution automatique (vérifier qu'il appelle le bon script)

## Installation de l'environnement Python (Windows)

1. Ouvre PowerShell dans le dossier du projet :
   ```powershell
   cd "c:\Users\karap\OpenClassRooms\projet10"
   ```

2. Crée un environnement virtuel Python :
   ```powershell
   py -3 -m venv .venv
   ```

3. Active l'environnement virtuel :
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

4. Installe les dépendances du projet :
   ```powershell
   pip install -r requirements.txt
   ```

> Si `py` n'est pas reconnu, installe Python depuis https://www.python.org/downloads/ et coche l'option "Add Python to PATH" pendant l'installation.

## Pourquoi Kestra

J'ai choisi Kestra pour présenter le workflow parce que l'outil rend l'orchestration explicite et facile à suivre.

- Le graphe du workflow montre l'ordre des étapes et les branchements.
- Les tâches peuvent s'exécuter en parallèle quand c'est pertinent.
- Les contrôles qualité apparaissent directement dans l'interface.
- Le workflow peut être rejoué avec les mêmes entrées, ce qui améliore la reproductibilite.
- Le déclenchement planifié permet de montrer un vrai scénario d'automatisation.

Le fichier d'orchestration principal est [Kestra/flows/orchestration_vins_duckdb.yaml](Kestra/flows/orchestration_vins_duckdb.yaml).

## Faire tourner Kestra en local

1. Démarre les services avec :
   ```powershell
   docker compose up -d
   ```
2. Ouvre l'interface Kestra dans le navigateur à l'adresse :
   ```text
   http://localhost:8080
   ```
3. Importe le workflow contenu dans [Kestra/flows/orchestration_vins_duckdb.yaml](Kestra/flows/orchestration_vins_duckdb.yaml).
4. Fournis les trois fichiers d'entrée demandés par le flow : ERP, WEB et liaison.
5. Lance l'exécution depuis l'interface pour suivre les étapes, les tests et les sorties.

Le stack Docker utilisé par le projet est défini dans [docker-compose.yml](docker-compose.yml) et démarre deux services : PostgreSQL pour le stockage interne de Kestra, puis Kestra sur le port 8080.

## Lancement du script

Après activation de l'environnement virtuel :

### Version Pandas (classique)
```powershell
python nettoyage_reconciliation.py
```

### Version DuckDB (recommandée)
```powershell
python nettoyage_reconciliation_DuckDB.py
```

Avec le lanceur Windows :
```powershell
py nettoyage_reconciliation_DuckDB.py
```


## Exécution automatique

Tu peux aussi lancer le script PowerShell d'automatisation depuis le dossier racine :

```powershell
.\run_build.ps1
```

Vérifie que `run_build.ps1` lance bien `nettoyage_reconciliation.py` si `build_consolidation.py` n'existe plus.

## Résultat attendu

Les fichiers générés dans `data/` sont :

## Détail des fichiers générés

Cette section précise le contenu de chaque fichier produit, pour faciliter la vérification.

### Version DuckDB
- `projet_consolidation_duckdb.duckdb` : base DuckDB avec toutes les tables de travail (staging, nettoyage, fusion, scores) et les tables finales (`produits_consolides`, `ca_par_produit`, `vins_premium`, `vins_ordinaires`).
- `consolidation_duckdb.xlsx` : table finale consolidée ERP + LIAISON + WEB (1 ligne = 1 produit consolidé, avec prix, stock, ventes, infos produit web).
- `ca_par_produit_duckdb.xlsx` : chiffre d'affaires par produit (colonnes principales : `product_id`, `sku`, `post_title`, `prix_unitaire`, `quantite_vendue`, `chiffre_affaires`).
- `vins_premium_duckdb.csv` : sous-ensemble des produits classés premium (z-score prix > 2 et prix au-dessus de l'IQR).
- `vins_ordinaires_duckdb.csv` : sous-ensemble des produits non premium.

### Version Pandas
- `consolidation.xlsx` : table finale consolidée ERP + LIAISON + WEB (mêmes colonnes que la version DuckDB).
- `ca_par_produit.xlsx` : chiffre d'affaires par produit (mêmes colonnes que la version DuckDB).
- `vins_premium.csv` : sous-ensemble des produits classés premium.
- `vins_ordinaires.csv` : sous-ensemble des produits non premium.

## Exemple de sortie

Lors de l'exécution de `python nettoyage_reconciliation_DuckDB.py`, tu peux obtenir un output similaire à :

```text
================================================================================
VÉRIFICATION DES FICHIERS D'ENTRÉE
================================================================================
Tous les fichiers d'entrée sont présents.

================================================================================
CHARGEMENT DES FICHIERS EXCEL
================================================================================
ERP chargé : 825 lignes, 5 colonnes
WEB chargé : 1513 lignes, 28 colonnes
LIAISON chargée : 825 lignes, 2 colonnes

================================================================================
CONTRÔLE DES DOUBLONS
================================================================================
Nombre de clés ERP dupliquées sur product_id : 0
Nombre de SKU WEB dupliqués sur les produits : 0
Nombre de product_id dupliqués dans la liaison : 0

================================================================================
NETTOYAGE WEB DANS DUCKDB
================================================================================
Après nettoyage du fichier web : 1428 lignes
Après dédoublonnage du fichier web : 714 lignes
Total_sales négatifs dans WEB nettoyé : 0

================================================================================
FUSION FINALE DANS DUCKDB
================================================================================
Nombre total de lignes dans produits_consolides : 714

================================================================================
DÉTECTION DES VINS PREMIUM
================================================================================
Nombre de vins premium : 30
Nombre de vins ordinaires : 684

================================================================================
RÉSUMÉ FINAL
================================================================================
Workflow DuckDB terminé avec succès.
- Lignes ERP nettoyées : 825
- Lignes WEB nettoyées : 714
- Lignes LIAISON valides : 714
- Lignes consolidées : 714
- Chiffre d'affaires global : 123456.78
- Nombre de vins premium : 30
- Nombre de vins ordinaires : 684

Fichiers générés :
- data\projet_consolidation_duckdb.duckdb
- data\consolidation_duckdb.xlsx
- data\ca_par_produit_duckdb.xlsx
- data\vins_premium_duckdb.csv
- data\vins_ordinaires_duckdb.csv
```

## Notes importantes

- La version DuckDB utilise une base de données DuckDB pour manipuler les données, ce qui est plus performant sur les gros volumes
- Les deux versions (Pandas et DuckDB) produisent les mêmes résultats finaux
- Pour la version Pandas, consulte l'historique du fichier ou la branche précédente pour plus de détails
