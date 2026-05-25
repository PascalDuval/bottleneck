from pathlib import Path
import numpy as np
import pandas as pd


# ============================================================
# PARAMÈTRES
# ============================================================
BASE_DIR = Path("data")

ERP_FILE = BASE_DIR / "Fichier_erp.xlsx"
LIAISON_FILE = BASE_DIR / "fichier_liaison.xlsx"
WEB_FILE = BASE_DIR / "Fichier_web.xlsx"
OUTPUT_FILE = BASE_DIR / "consolidation.xlsx"


# ============================================================
# OUTILS
# ============================================================
def safe_str(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    if value == "" or value.lower() == "nan":
        return None
    return value


def classify_match_status(row):
    if pd.isna(row["id_web"]) or row["id_web"] == "":
        return "NO_WEB_LINK"
    if row["web_row_count"] == 0:
        return "WEB_SKU_NOT_FOUND"
    if row["web_has_non_product_match"]:
        return "WEB_NOT_PRODUCT"
    if row["web_row_count"] > 1:
        return "DUPLICATE_WEB_SKU"
    return "OK"


def build_anomaly_flags(row):
    flags = []

    if row["match_status"] != "OK":
        flags.append(row["match_status"])

    if pd.notna(row["price"]) and row["price"] < 0:
        flags.append("NEGATIVE_PRICE")

    if pd.notna(row["stock_quantity"]) and row["stock_quantity"] < 0:
        flags.append("NEGATIVE_STOCK")

    if row["stock_status"] == "instock" and pd.notna(row["stock_quantity"]) and row["stock_quantity"] <= 0:
        flags.append("INCONSISTENT_STOCK_STATUS")

    if row["stock_status"] == "outofstock" and pd.notna(row["stock_quantity"]) and row["stock_quantity"] > 0:
        flags.append("INCONSISTENT_STOCK_STATUS")

    if pd.isna(row["total_sales"]):
        flags.append("MISSING_TOTAL_SALES")
    elif row["total_sales"] < 0:
        flags.append("NEGATIVE_TOTAL_SALES")

    if pd.isna(row["sku"]):
        flags.append("MISSING_SKU")

    if row["post_type"] not in [None, np.nan, "product"]:
        flags.append("NON_PRODUCT_WEB_ROW")

    return " | ".join(sorted(set(flags))) if flags else "OK"


def compute_quality_status(anomaly_flags):
    if anomaly_flags == "OK":
        return "OK"

    critical_keywords = {
        "NO_WEB_LINK",
        "WEB_SKU_NOT_FOUND",
        "DUPLICATE_WEB_SKU",
        "NEGATIVE_PRICE",
        "NEGATIVE_TOTAL_SALES",
    }

    warning_keywords = {
        "NEGATIVE_STOCK",
        "INCONSISTENT_STOCK_STATUS",
        "MISSING_TOTAL_SALES",
        "MISSING_SKU",
        "NON_PRODUCT_WEB_ROW",
        "WEB_NOT_PRODUCT",
    }

    flag_set = set(part.strip() for part in anomaly_flags.split("|"))

    if any(flag in critical_keywords for flag in flag_set):
        return "CRITICAL"
    if any(flag in warning_keywords for flag in flag_set):
        return "WARNING"
    return "WARNING"


# ============================================================
# CHARGEMENT
# ============================================================
erp = pd.read_excel(ERP_FILE)
liaison = pd.read_excel(LIAISON_FILE)
web = pd.read_excel(WEB_FILE)

# Normalisation minimale des clés
erp["product_id"] = pd.to_numeric(erp["product_id"], errors="coerce").astype("Int64")
liaison["product_id"] = pd.to_numeric(liaison["product_id"], errors="coerce").astype("Int64")

liaison["id_web"] = liaison["id_web"].apply(safe_str)
web["sku"] = web["sku"].apply(safe_str)

# Conversion de quelques colonnes web utiles
for col in ["total_sales", "average_rating", "rating_count"]:
    if col in web.columns:
        web[col] = pd.to_numeric(web[col], errors="coerce")

for col in ["post_date", "post_modified"]:
    if col in web.columns:
        web[col] = pd.to_datetime(web[col], errors="coerce")


# ============================================================
# PRÉPARATION WEB
# ============================================================
# 1. Compter toutes les lignes web par SKU
web_sku_counts = (
    web.groupby("sku", dropna=False)
       .size()
       .reset_index(name="web_row_count")
)

# 2. Repérer s’il existe des lignes non-product pour un SKU
web_non_product = (
    web.assign(is_non_product=web["post_type"].fillna("MISSING").ne("product"))
       .groupby("sku", dropna=False)["is_non_product"]
       .max()
       .reset_index(name="web_has_non_product_match")
)

# 3. Garder uniquement les produits pour la réconciliation métier
web_products = web[web["post_type"] == "product"].copy()

# 4. Déduplication : on préfère les produits publiés, puis les plus vendus
web_products["publish_rank"] = np.where(web_products["post_status"] == "publish", 1, 0)
web_products["sales_rank"] = web_products["total_sales"].fillna(-1)

web_products = (
    web_products.sort_values(
        by=["sku", "publish_rank", "sales_rank"],
        ascending=[True, False, False]
    )
    .drop_duplicates(subset=["sku"], keep="first")
)

# 5. Colonnes CMS retenues
web_keep_cols = [
    "sku",
    "post_title",
    "post_status",
    "post_type",
    "total_sales",
    "average_rating",
    "rating_count",
    "tax_status",
    "tax_class",
    "post_date",
    "post_modified",
    "post_name",
]

web_products = web_products[web_keep_cols]


# ============================================================
# CONSOLIDATION
# ============================================================
consolidation = erp.merge(liaison, on="product_id", how="left")

consolidation = consolidation.merge(
    web_sku_counts,
    left_on="id_web",
    right_on="sku",
    how="left"
)

consolidation = consolidation.merge(
    web_non_product,
    left_on="id_web",
    right_on="sku",
    how="left",
    suffixes=("", "_nonprod")
)

consolidation = consolidation.merge(
    web_products,
    left_on="id_web",
    right_on="sku",
    how="left",
    suffixes=("", "_web")
)

# Nettoyage des colonnes techniques issues des merges
if "sku_nonprod" in consolidation.columns:
    consolidation.drop(columns=["sku_nonprod"], inplace=True)

consolidation["web_row_count"] = consolidation["web_row_count"].fillna(0).astype(int)
consolidation["web_has_non_product_match"] = consolidation["web_has_non_product_match"].fillna(False)

# ============================================================
# STATUT DE RAPPROCHEMENT
# ============================================================
consolidation["match_status"] = consolidation.apply(classify_match_status, axis=1)

# ============================================================
# FLAGS QUALITÉ
# ============================================================
consolidation["anomaly_flags"] = consolidation.apply(build_anomaly_flags, axis=1)

consolidation["price_valid"] = consolidation["price"].notna() & (consolidation["price"] >= 0)
consolidation["stock_valid"] = consolidation["stock_quantity"].notna()
consolidation["sales_valid"] = consolidation["total_sales"].notna() & (consolidation["total_sales"] >= 0)

consolidation["is_published_product"] = (
    consolidation["post_type"].eq("product") &
    consolidation["post_status"].eq("publish")
)

consolidation["stock_consistency"] = np.select(
    [
        consolidation["stock_status"].eq("instock") & consolidation["stock_quantity"].fillna(0).le(0),
        consolidation["stock_status"].eq("outofstock") & consolidation["stock_quantity"].fillna(0).gt(0),
    ],
    [
        "INCONSISTENT",
        "INCONSISTENT",
    ],
    default="CONSISTENT"
)

consolidation["data_quality_status"] = consolidation["anomaly_flags"].apply(compute_quality_status)

# ============================================================
# INDICATEURS BUSINESS
# ============================================================
consolidation["unit_price_used"] = np.where(
    consolidation["price_valid"],
    consolidation["price"],
    np.nan
)

consolidation["quantity_sold"] = np.where(
    consolidation["sales_valid"],
    consolidation["total_sales"],
    np.nan
)

consolidation["is_active_for_revenue"] = (
    consolidation["match_status"].eq("OK") &
    consolidation["price_valid"] &
    consolidation["sales_valid"]
)

consolidation["revenue_product"] = np.where(
    consolidation["is_active_for_revenue"],
    consolidation["unit_price_used"] * consolidation["quantity_sold"],
    np.nan
)

# ============================================================
# PREMIUM : Z-SCORE ET IQR SUR LE PRIX
# ============================================================
price_series = consolidation.loc[
    consolidation["price_valid"] & consolidation["price"].gt(0),
    "price"
].dropna()

if len(price_series) >= 2:
    mean_price = price_series.mean()
    std_price = price_series.std(ddof=0)

    q1 = price_series.quantile(0.25)
    q3 = price_series.quantile(0.75)
    iqr = q3 - q1
    iqr_lower = q1 - 1.5 * iqr
    iqr_upper = q3 + 1.5 * iqr

    consolidation["price_zscore"] = np.where(
        consolidation["price_valid"] & (std_price > 0),
        (consolidation["price"] - mean_price) / std_price,
        np.nan
    )
else:
    mean_price = np.nan
    std_price = np.nan
    q1 = np.nan
    q3 = np.nan
    iqr = np.nan
    iqr_lower = np.nan
    iqr_upper = np.nan
    consolidation["price_zscore"] = np.nan

consolidation["iqr_q1"] = q1
consolidation["iqr_q3"] = q3
consolidation["iqr_lower_bound"] = iqr_lower
consolidation["iqr_upper_bound"] = iqr_upper

# Règles premium
# Tu peux ajuster le seuil z-score si besoin.
consolidation["is_premium_zscore"] = consolidation["price_zscore"] > 2
consolidation["is_premium_iqr"] = consolidation["price"] > consolidation["iqr_upper_bound"]

def premium_flag(row):
    z = bool(row["is_premium_zscore"]) if pd.notna(row["is_premium_zscore"]) else False
    i = bool(row["is_premium_iqr"]) if pd.notna(row["is_premium_iqr"]) else False

    if z and i:
        return "PREMIUM_BOTH"
    if z and not i:
        return "PREMIUM_ZSCORE_ONLY"
    if i and not z:
        return "PREMIUM_IQR_ONLY"
    return "STANDARD"

consolidation["premium_flag"] = consolidation.apply(premium_flag, axis=1)

# ============================================================
# ORDONNER LES COLONNES FINALES
# ============================================================
final_columns = [
    # Clés
    "product_id",
    "id_web",
    "sku",
    "match_status",
    "anomaly_flags",

    # ERP
    "onsale_web",
    "price",
    "stock_quantity",
    "stock_status",

    # Web
    "post_title",
    "post_status",
    "post_type",
    "total_sales",
    "average_rating",
    "rating_count",
    "tax_status",
    "tax_class",
    "post_date",
    "post_modified",
    "post_name",

    # Qualité
    "price_valid",
    "stock_valid",
    "sales_valid",
    "is_published_product",
    "stock_consistency",
    "data_quality_status",

    # Business
    "unit_price_used",
    "quantity_sold",
    "is_active_for_revenue",
    "revenue_product",

    # Premium
    "price_zscore",
    "iqr_q1",
    "iqr_q3",
    "iqr_lower_bound",
    "iqr_upper_bound",
    "is_premium_zscore",
    "is_premium_iqr",
    "premium_flag",
]

consolidation = consolidation[final_columns].copy()

# ============================================================
# FEUILLES COMPLÉMENTAIRES
# ============================================================
summary = pd.DataFrame({
    "metric": [
        "nb_total_products",
        "nb_reconciled_ok",
        "nb_critical_quality",
        "nb_warning_quality",
        "revenue_total",
        "nb_premium_both",
        "nb_premium_zscore_only",
        "nb_premium_iqr_only",
        "price_mean",
        "price_std",
        "price_q1",
        "price_q3",
        "iqr_upper_bound",
    ],
    "value": [
        len(consolidation),
        int((consolidation["match_status"] == "OK").sum()),
        int((consolidation["data_quality_status"] == "CRITICAL").sum()),
        int((consolidation["data_quality_status"] == "WARNING").sum()),
        float(consolidation["revenue_product"].sum(skipna=True)),
        int((consolidation["premium_flag"] == "PREMIUM_BOTH").sum()),
        int((consolidation["premium_flag"] == "PREMIUM_ZSCORE_ONLY").sum()),
        int((consolidation["premium_flag"] == "PREMIUM_IQR_ONLY").sum()),
        mean_price,
        std_price,
        q1,
        q3,
        iqr_upper,
    ]
})

anomalies = consolidation[consolidation["anomaly_flags"] != "OK"].copy()

premium_products = consolidation[
    consolidation["premium_flag"] != "STANDARD"
].copy()

# ============================================================
# EXPORT EXCEL
# ============================================================
with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
    consolidation.to_excel(writer, sheet_name="consolidation", index=False)
    summary.to_excel(writer, sheet_name="synthese", index=False)
    anomalies.to_excel(writer, sheet_name="anomalies", index=False)
    premium_products.to_excel(writer, sheet_name="premium", index=False)

print(f"Fichier créé : {OUTPUT_FILE}")
print("Feuilles créées : consolidation, synthese, anomalies, premium")