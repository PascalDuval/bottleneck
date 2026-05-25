from pathlib import Path
import pandas as pd
import numpy as np


# ============================================================
# PARAMÈTRES
# ============================================================
DATA_DIR = Path("data")

ERP_FILE = DATA_DIR / "Fichier_erp.xlsx"
WEB_FILE = DATA_DIR / "Fichier_web.xlsx"
LIAISON_FILE = DATA_DIR / "fichier_liaison.xlsx"

CONSOLIDATION_FILE = DATA_DIR / "consolidation.xlsx"
CA_FILE = DATA_DIR / "ca_par_produit.xlsx"
PREMIUM_FILE = DATA_DIR / "vins_premium.csv"
ORDINARY_FILE = DATA_DIR / "vins_ordinaires.csv"


# ============================================================
# OUTILS
# ============================================================
def print_sep(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def safe_str(x):
    if pd.isna(x):
        return np.nan
    x = str(x).strip()
    if x == "" or x.lower() == "nan":
        return np.nan
    return x


def report_missing_values(df: pd.DataFrame, name: str):
    print(f"\nAnalyse des valeurs manquantes pour {name} :")
    missing = df.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    if missing.empty:
        print("Aucune valeur manquante détectée.")
    else:
        print("Colonnes contenant des valeurs manquantes :")
        print(missing.to_string())


def report_duplicates(df: pd.DataFrame, name: str, subset=None):
    print(f"\nAnalyse des doublons pour {name} :")
    dup_count = df.duplicated(subset=subset).sum()
    if subset is None:
        print(f"Nombre de lignes totalement dupliquées : {dup_count}")
    else:
        print(f"Nombre de doublons sur {subset} : {dup_count}")


def coerce_numeric_and_report(df: pd.DataFrame, col: str, name: str):
    """
    Convertit une colonne en numérique et signale les mauvaises valeurs.
    """
    original_non_null = df[col].notna().sum()
    converted = pd.to_numeric(df[col], errors="coerce")
    bad_values = df[col].notna() & converted.isna()
    bad_count = bad_values.sum()

    print(f"\nContrôle de la colonne numérique '{col}' dans {name} :")
    print(f"Nombre de valeurs non nulles initiales : {original_non_null}")
    print(f"Nombre de mauvaises valeurs détectées : {bad_count}")

    if bad_count > 0:
        print("Exemples de mauvaises valeurs :")
        print(df.loc[bad_values, col].head(10).to_string(index=False))

    df[col] = converted
    return df


def coerce_datetime_and_report(df: pd.DataFrame, col: str, name: str):
    original_non_null = df[col].notna().sum()
    converted = pd.to_datetime(df[col], errors="coerce")
    bad_values = df[col].notna() & converted.isna()
    bad_count = bad_values.sum()

    print(f"\nContrôle de la colonne date '{col}' dans {name} :")
    print(f"Nombre de valeurs non nulles initiales : {original_non_null}")
    print(f"Nombre de mauvaises valeurs détectées : {bad_count}")

    if bad_count > 0:
        print("Exemples de mauvaises dates :")
        print(df.loc[bad_values, col].head(10).to_string(index=False))

    df[col] = converted
    return df


def iqr_bounds(series: pd.Series):
    s = series.dropna()
    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return q1, q3, lower, upper


# ============================================================
# 1) CHARGEMENT
# ============================================================
print_sep("CHARGEMENT DES FICHIERS")

erp = pd.read_excel(ERP_FILE)
web = pd.read_excel(WEB_FILE)
liaison = pd.read_excel(LIAISON_FILE)

print(f"ERP chargé : {erp.shape[0]} lignes, {erp.shape[1]} colonnes")
print(f"WEB chargé : {web.shape[0]} lignes, {web.shape[1]} colonnes")
print(f"LIAISON chargée : {liaison.shape[0]} lignes, {liaison.shape[1]} colonnes")


# ============================================================
# 2) NETTOYAGE ERP
# ============================================================
print_sep("NETTOYAGE DU FICHIER ERP")

print("Nombre de lignes initial dans ERP :", len(erp))

report_duplicates(erp, "ERP")
report_duplicates(erp, "ERP", subset=["product_id"])

report_missing_values(erp, "ERP")

# Normalisation / typage
erp["product_id"] = pd.to_numeric(erp["product_id"], errors="coerce")
erp["onsale_web"] = pd.to_numeric(erp["onsale_web"], errors="coerce")
erp["price"] = pd.to_numeric(erp["price"], errors="coerce")
erp["stock_quantity"] = pd.to_numeric(erp["stock_quantity"], errors="coerce")
erp["stock_status"] = erp["stock_status"].apply(safe_str)

print("\nContrôle des mauvaises valeurs ERP :")
print("- product_id, onsale_web, price, stock_quantity doivent être numériques")
print("- stock_status doit être renseigné")

# Détection mauvaises valeurs
erp_bad = (
    erp["product_id"].isna()
    | erp["onsale_web"].isna()
    | erp["price"].isna()
    | erp["stock_quantity"].isna()
    | erp["stock_status"].isna()
)

print(f"Nombre de lignes ERP contenant au moins une valeur manquante ou mauvaise : {erp_bad.sum()}")

# Dédoublonnage
erp_dedup = erp.drop_duplicates()
print(f"Après dédoublonnage complet du fichier ERP : {len(erp_dedup)} lignes")

erp_dedup = erp_dedup.drop_duplicates(subset=["product_id"], keep="first")
print(f"Après dédoublonnage sur product_id : {len(erp_dedup)} lignes")

# Suppression lignes mauvaises
erp_clean = erp_dedup.loc[~(
    erp_dedup["product_id"].isna()
    | erp_dedup["onsale_web"].isna()
    | erp_dedup["price"].isna()
    | erp_dedup["stock_quantity"].isna()
    | erp_dedup["stock_status"].isna()
)].copy()

print(f"Nombre de lignes ERP après nettoyage : {len(erp_clean)}")

# Contrôles métier simples
print("\nContrôles métier ERP complémentaires :")
neg_price = (erp_clean["price"] < 0).sum()
neg_stock = (erp_clean["stock_quantity"] < 0).sum()
print(f"- Prix négatifs : {neg_price}")
print(f"- Stocks négatifs : {neg_stock}")


# ============================================================
# 3) NETTOYAGE WEB
# ============================================================
print_sep("NETTOYAGE DU FICHIER WEB")

print("Nombre de lignes initial dans WEB :", len(web))

# On garde les produits uniquement pour la réconciliation
print("\nLe fichier web contient plusieurs types de lignes.")
print("Pour la réconciliation produit, on ne conserve que post_type = 'product'.")

report_duplicates(web, "WEB brut")
report_missing_values(web, "WEB brut")

web["sku"] = web["sku"].apply(safe_str)
web["post_type"] = web["post_type"].apply(safe_str)
web["post_status"] = web["post_status"].apply(safe_str)
web["post_title"] = web["post_title"].apply(safe_str)
web["post_name"] = web["post_name"].apply(safe_str)

for col in ["total_sales", "average_rating", "rating_count"]:
    web[col] = pd.to_numeric(web[col], errors="coerce")

for col in ["post_date", "post_modified"]:
    web[col] = pd.to_datetime(web[col], errors="coerce")

web_products = web.loc[web["post_type"] == "product"].copy()
print(f"\nNombre de lignes WEB après filtrage post_type='product' : {len(web_products)}")

report_duplicates(web_products, "WEB produits", subset=["sku"])
report_missing_values(web_products, "WEB produits")

web_bad = (
    web_products["sku"].isna()
    | web_products["post_title"].isna()
    | web_products["total_sales"].isna()
)

print(f"\nNombre de lignes WEB produits contenant au moins une valeur manquante ou mauvaise : {web_bad.sum()}")

# Dédoublonnage
web_dedup = web_products.drop_duplicates()
print(f"Après dédoublonnage complet du fichier WEB produits : {len(web_dedup)} lignes")

web_dedup = web_dedup.drop_duplicates(subset=["sku"], keep="first")
print(f"Après dédoublonnage sur sku : {len(web_dedup)} lignes")

# Suppression lignes mauvaises
web_clean = web_dedup.loc[~(
    web_dedup["sku"].isna()
    | web_dedup["post_title"].isna()
    | web_dedup["total_sales"].isna()
)].copy()

print(f"Nombre de lignes WEB après nettoyage : {len(web_clean)}")

# Contrôles métier simples
print("\nContrôles métier WEB complémentaires :")
neg_sales = (web_clean["total_sales"] < 0).sum()
print(f"- Total_sales négatifs : {neg_sales}")


# ============================================================
# 4) NETTOYAGE LIAISON
# ============================================================
print_sep("NETTOYAGE DU FICHIER DE JONCTION")

print("Nombre de lignes initial dans LIAISON :", len(liaison))

report_duplicates(liaison, "LIAISON")
report_duplicates(liaison, "LIAISON", subset=["product_id"])
report_missing_values(liaison, "LIAISON")

liaison["product_id"] = pd.to_numeric(liaison["product_id"], errors="coerce")
liaison["id_web"] = liaison["id_web"].apply(safe_str)

liaison_bad = liaison["product_id"].isna() | liaison["id_web"].isna()
print(f"\nNombre de lignes LIAISON contenant au moins une valeur manquante ou mauvaise : {liaison_bad.sum()}")

liaison_dedup = liaison.drop_duplicates()
print(f"Après dédoublonnage complet du fichier de jonction : {len(liaison_dedup)} lignes")

liaison_dedup = liaison_dedup.drop_duplicates(subset=["product_id"], keep="first")
print(f"Après dédoublonnage sur product_id : {len(liaison_dedup)} lignes")

liaison_clean = liaison_dedup.loc[~(
    liaison_dedup["product_id"].isna() | liaison_dedup["id_web"].isna()
)].copy()

print(f"Nombre de lignes LIAISON après premier nettoyage : {len(liaison_clean)}")


# ============================================================
# 5) TESTS DE COHÉRENCE DES JOINTURES
# ============================================================
print_sep("TESTS DE COHERENCE DES JOINTURES")

erp_ids = set(erp_clean["product_id"].dropna().astype(int))
web_skus = set(web_clean["sku"].dropna().astype(str))

liaison_clean["product_id_int"] = liaison_clean["product_id"].astype(int)
liaison_clean["id_web_str"] = liaison_clean["id_web"].astype(str)

bad_join_erp = ~liaison_clean["product_id_int"].isin(erp_ids)
bad_join_web = ~liaison_clean["id_web_str"].isin(web_skus)

print(f"Lignes de liaison sans correspondance ERP : {bad_join_erp.sum()}")
print(f"Lignes de liaison sans correspondance WEB : {bad_join_web.sum()}")

liaison_good = liaison_clean.loc[~(bad_join_erp | bad_join_web)].copy()
print(f"Nombre de lignes de liaison après suppression des mauvaises jointures : {len(liaison_good)}")


# ============================================================
# 6) FUSION FINALE
# ============================================================
print_sep("FUSION DES FICHIERS AVEC LES BONNES JOINTURES")

consolidation = (
    erp_clean.merge(
        liaison_good[["product_id", "id_web"]],
        on="product_id",
        how="inner"
    )
    .merge(
        web_clean,
        left_on="id_web",
        right_on="sku",
        how="inner"
    )
)

print(f"Nombre total de lignes dans le fichier fusionné final : {len(consolidation)}")

# Colonnes utiles business
business_cols = [
    "product_id",
    "id_web",
    "sku",
    "post_title",
    "post_status",
    "onsale_web",
    "price",
    "stock_quantity",
    "stock_status",
    "total_sales",
    "average_rating",
    "rating_count",
    "post_date",
    "post_modified",
]
business_cols = [c for c in business_cols if c in consolidation.columns]

consolidation = consolidation[business_cols].copy()

# ============================================================
# 7) TEST DE COHÉRENCE DU CHIFFRE D'AFFAIRES
# ============================================================
print_sep("TEST DE COHERENCE DU CHIFFRE D'AFFAIRES")

consolidation["price"] = pd.to_numeric(consolidation["price"], errors="coerce")
consolidation["total_sales"] = pd.to_numeric(consolidation["total_sales"], errors="coerce")

consolidation["ca_produit"] = consolidation["price"] * consolidation["total_sales"]

bad_ca = (
    consolidation["price"].isna()
    | consolidation["total_sales"].isna()
    | (consolidation["price"] < 0)
    | (consolidation["total_sales"] < 0)
)

print(f"Nombre de lignes incohérentes pour le calcul du chiffre d'affaires : {bad_ca.sum()}")

consolidation_valid_ca = consolidation.loc[~bad_ca].copy()
ca_total = consolidation_valid_ca["ca_produit"].sum()

print(f"Nombre de lignes conservées pour le calcul du chiffre d'affaires : {len(consolidation_valid_ca)}")
print(f"Chiffre d'affaires total calculé : {ca_total:.2f}")


# ============================================================
# 8) TEST Z-SCORE SUR LE PRIX DES VINS
# ============================================================
print_sep("TEST DU Z-SCORE SUR LE PRIX DES VINS")

price_series = consolidation_valid_ca["price"].dropna()

mean_price = price_series.mean()
std_price = price_series.std(ddof=0)

if std_price == 0 or pd.isna(std_price):
    consolidation_valid_ca["z_score_price"] = np.nan
    consolidation_valid_ca["premium_zscore"] = False
    print("Ecart-type nul ou non calculable : impossible d'utiliser le z-score.")
else:
    consolidation_valid_ca["z_score_price"] = (consolidation_valid_ca["price"] - mean_price) / std_price
    consolidation_valid_ca["premium_zscore"] = consolidation_valid_ca["z_score_price"] > 2

premium_count_z = consolidation_valid_ca["premium_zscore"].sum()
print(f"Nombre de vins premium détectés par z-score (> 2) : {premium_count_z}")

# IQR pour renforcer la détection
q1, q3, lower_iqr, upper_iqr = iqr_bounds(consolidation_valid_ca["price"])
consolidation_valid_ca["premium_iqr"] = consolidation_valid_ca["price"] > upper_iqr

premium_count_iqr = consolidation_valid_ca["premium_iqr"].sum()
print(f"Nombre de vins premium détectés par IQR : {premium_count_iqr}")

consolidation_valid_ca["premium_flag"] = np.where(
    consolidation_valid_ca["premium_zscore"] & consolidation_valid_ca["premium_iqr"],
    "PREMIUM",
    "ORDINAIRE"
)

premium_count_final = (consolidation_valid_ca["premium_flag"] == "PREMIUM").sum()
ordinary_count_final = (consolidation_valid_ca["premium_flag"] == "ORDINAIRE").sum()

print(f"Nombre final de vins classés PREMIUM : {premium_count_final}")
print(f"Nombre final de vins classés ORDINAIRES : {ordinary_count_final}")


# ============================================================
# 9) EXTRACTIONS
# ============================================================
print_sep("PRODUCTION DES FICHIERS DE SORTIE")

# Fichier consolidé principal
with pd.ExcelWriter(CONSOLIDATION_FILE, engine="openpyxl") as writer:
    consolidation_valid_ca.to_excel(writer, sheet_name="consolidation", index=False)

print(f"Fichier de consolidation créé : {CONSOLIDATION_FILE}")

# Fichier CA par produit
ca_par_produit = (
    consolidation_valid_ca.groupby(
        ["product_id", "post_title"], as_index=False
    )
    .agg(
        prix_unitaire=("price", "first"),
        quantite_vendue=("total_sales", "sum"),
        chiffre_affaires=("ca_produit", "sum")
    )
    .sort_values("chiffre_affaires", ascending=False)
)

with pd.ExcelWriter(CA_FILE, engine="openpyxl") as writer:
    ca_par_produit.to_excel(writer, sheet_name="ca_par_produit", index=False)

print(f"Extraction chiffre d'affaires par produit créée : {CA_FILE}")
print(f"Nombre de lignes dans l'extraction CA par produit : {len(ca_par_produit)}")

# Premium
vins_premium = consolidation_valid_ca.loc[
    consolidation_valid_ca["premium_flag"] == "PREMIUM"
].copy()

vins_premium.to_csv(PREMIUM_FILE, index=False, encoding="utf-8-sig")
print(f"Extraction des vins premium créée : {PREMIUM_FILE}")
print(f"Nombre de lignes dans les vins premium : {len(vins_premium)}")

# Ordinaires
vins_ordinaires = consolidation_valid_ca.loc[
    consolidation_valid_ca["premium_flag"] == "ORDINAIRE"
].copy()

vins_ordinaires.to_csv(ORDINARY_FILE, index=False, encoding="utf-8-sig")
print(f"Extraction des vins ordinaires créée : {ORDINARY_FILE}")
print(f"Nombre de lignes dans les vins ordinaires : {len(vins_ordinaires)}")


# ============================================================
# 10) RÉSUMÉ FINAL
# ============================================================
print_sep("RÉSUMÉ FINAL")

print("Nettoyage ERP terminé.")
print(f"Nombre de lignes ERP après nettoyage : {len(erp_clean)}")

print("\nNettoyage WEB terminé.")
print(f"Nombre de lignes WEB après nettoyage : {len(web_clean)}")

print("\nNettoyage LIAISON terminé.")
print(f"Nombre de lignes LIAISON après nettoyage et contrôle de jointure : {len(liaison_good)}")

print("\nFusion terminée.")
print(f"Nombre de lignes dans la consolidation finale : {len(consolidation_valid_ca)}")

print("\nRésultats business :")
print(f"- Chiffre d'affaires total : {ca_total:.2f}")
print(f"- Nombre de vins premium : {len(vins_premium)}")
print(f"- Nombre de vins ordinaires : {len(vins_ordinaires)}")

print("\nTous les fichiers de sortie ont été générés dans le dossier data.")