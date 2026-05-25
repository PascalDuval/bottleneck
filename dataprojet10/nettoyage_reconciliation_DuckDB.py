from pathlib import Path
import pandas as pd
import duckdb


# ============================================================
# PARAMÈTRES GLOBAUX
# ============================================================
DATA_DIR = Path("data")

ERP_FILE = DATA_DIR / "Fichier_erp.xlsx"
WEB_FILE = DATA_DIR / "Fichier_web.xlsx"
LIAISON_FILE = DATA_DIR / "fichier_liaison.xlsx"

DUCKDB_FILE = DATA_DIR / "projet_consolidation_duckdb.duckdb"

CONSOLIDATION_FILE = DATA_DIR / "consolidation_duckdb.xlsx"
CA_FILE = DATA_DIR / "ca_par_produit_duckdb.xlsx"
PREMIUM_FILE = DATA_DIR / "vins_premium_duckdb.csv"
ORDINARY_FILE = DATA_DIR / "vins_ordinaires_duckdb.csv"


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================
def print_sep(title: str):
    """Affiche un séparateur avec un titre pour structurer la sortie console."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def sql_scalar(con, query: str):
    """Exécute une requête SQL et retourne la première valeur scalaire."""
    return con.execute(query).fetchone()[0]


def sql_df(con, query: str):
    """Exécute une requête SQL et retourne un DataFrame Pandas."""
    return con.execute(query).df()


# ============================================================
# FONCTIONS DE VALIDATION ET TESTS
# ============================================================
"""
Tests intégrés :
- Exécutés à l'exécution du script (via `assert`).
- Il ne s'agit pas de tests unitaires `pytest`, mais de contrôles qualité inline.
"""
def test_erp_quality(con):
    """Tests de qualité pour les données ERP nettoyées."""
    print("  → Tests de qualité ERP...")

    # Test : Aucun doublon sur product_id
    dup_count = sql_scalar(con, "SELECT COUNT(*) FROM (SELECT product_id FROM erp_clean GROUP BY product_id HAVING COUNT(*) > 1) t")
    assert dup_count == 0, f"Erreur : {dup_count} doublons sur product_id dans ERP"

    # Test : Pas de valeurs nulles critiques
    null_price = sql_scalar(con, "SELECT COUNT(*) FROM erp_clean WHERE price IS NULL")
    assert null_price == 0, f"Erreur : {null_price} prix NULL dans ERP"

    # Test : Prix positifs
    neg_price = sql_scalar(con, "SELECT COUNT(*) FROM erp_clean WHERE price < 0")
    if neg_price > 0:
        print(f"  ⚠️  Avertissement : {neg_price} prix négatifs détectés (accepté pour analyse)")

    print("  ✅ Tests ERP passés")


def test_web_quality(con):
    """Tests de qualité pour les données WEB nettoyées."""
    print("  → Tests de qualité WEB...")

    # Test : Aucun doublon sur sku
    dup_count = sql_scalar(con, "SELECT COUNT(*) FROM (SELECT sku FROM web_clean GROUP BY sku HAVING COUNT(*) > 1) t")
    assert dup_count == 0, f"Erreur : {dup_count} doublons sur sku dans WEB"

    # Test : Seulement des produits
    non_product = sql_scalar(con, "SELECT COUNT(*) FROM web_clean WHERE post_type != 'product'")
    assert non_product == 0, f"Erreur : {non_product} lignes non-produit dans WEB"

    # Test : SKU non null
    null_sku = sql_scalar(con, "SELECT COUNT(*) FROM web_clean WHERE sku IS NULL OR sku = ''")
    assert null_sku == 0, f"Erreur : {null_sku} SKU NULL ou vides dans WEB"

    print("  ✅ Tests WEB passés")


def test_liaison_quality(con):
    """Tests de qualité pour les données LIAISON nettoyées."""
    print("  → Tests de qualité LIAISON...")

    # Test : Aucun doublon sur product_id
    dup_count = sql_scalar(con, "SELECT COUNT(*) FROM (SELECT product_id FROM liaison_clean GROUP BY product_id HAVING COUNT(*) > 1) t")
    assert dup_count == 0, f"Erreur : {dup_count} doublons sur product_id dans LIAISON"

    # Test : Pas de valeurs nulles
    null_count = sql_scalar(con, "SELECT COUNT(*) FROM liaison_clean WHERE product_id IS NULL OR id_web IS NULL OR id_web = ''")
    assert null_count == 0, f"Erreur : {null_count} valeurs NULL dans LIAISON"

    print("  ✅ Tests LIAISON passés")


def test_fusion_quality(con):
    """Tests de qualité pour la fusion des données."""
    print("  → Tests de qualité de fusion...")

    # Test : Toutes les liaisons ont une correspondance ERP
    bad_erp = sql_scalar(con, "SELECT COUNT(*) FROM liaison_valid l LEFT JOIN erp_clean e ON l.product_id = e.product_id WHERE e.product_id IS NULL")
    assert bad_erp == 0, f"Erreur : {bad_erp} liaisons sans correspondance ERP"

    # Test : Toutes les liaisons ont une correspondance WEB
    bad_web = sql_scalar(con, "SELECT COUNT(*) FROM liaison_valid l LEFT JOIN web_clean w ON l.id_web = w.sku WHERE w.sku IS NULL")
    assert bad_web == 0, f"Erreur : {bad_web} liaisons sans correspondance WEB"

    # Test : Nombre de lignes consolidées = nombre de liaisons valides
    nb_consol = sql_scalar(con, "SELECT COUNT(*) FROM produits_consolides")
    nb_valid = sql_scalar(con, "SELECT COUNT(*) FROM liaison_valid")
    assert nb_consol == nb_valid, f"Erreur : {nb_consol} consolidées vs {nb_valid} liaisons valides"

    print("  ✅ Tests de fusion passés")


def test_scores_quality(con):
    """Tests de qualité pour les scores et segmentation."""
    print("  → Tests de qualité des scores...")

    # Test : CA positif
    neg_ca = sql_scalar(con, "SELECT COUNT(*) FROM ca_par_produit WHERE chiffre_affaires < 0")
    assert neg_ca == 0, f"Erreur : {neg_ca} CA négatifs"

    # Test : Segmentation complète (premium + ordinaires = total)
    nb_premium = sql_scalar(con, "SELECT COUNT(*) FROM vins_premium")
    nb_ordinaires = sql_scalar(con, "SELECT COUNT(*) FROM vins_ordinaires")
    nb_total = sql_scalar(con, "SELECT COUNT(*) FROM ca_par_produit")
    assert nb_premium + nb_ordinaires == nb_total, f"Erreur : {nb_premium} + {nb_ordinaires} != {nb_total}"

    # Test : Premium ont bien z_score > 2 et prix > borne_haute_iqr
    invalid_premium = sql_scalar(con, "SELECT COUNT(*) FROM vins_premium WHERE NOT (z_score_prix > 2 AND prix_unitaire > borne_haute_iqr)")
    assert invalid_premium == 0, f"Erreur : {invalid_premium} vins premium invalides"

    print("  ✅ Tests des scores passés")


# ============================================================
# PHASE 1 : INGESTION DES DONNÉES
# ============================================================
def phase_ingestion():
    """
    PHASE 1 : INGESTION DES DONNÉES
    - Vérification des fichiers d'entrée
    - Chargement des Excel en Pandas
    - Initialisation de DuckDB
    - Chargement des tables de staging
    """
    print_sep("PHASE 1 : INGESTION DES DONNÉES")

    # 1.1 Vérification des fichiers d'entrée
    check_input_files()

    # 1.2 Chargement des Excel en Pandas
    print_sep("CHARGEMENT DES FICHIERS EXCEL")
    global erp_df, web_df, liaison_df
    erp_df = pd.read_excel(ERP_FILE)
    web_df = pd.read_excel(WEB_FILE)
    liaison_df = pd.read_excel(LIAISON_FILE)

    print(f"ERP chargé : {erp_df.shape[0]} lignes, {erp_df.shape[1]} colonnes")
    print(f"WEB chargé : {web_df.shape[0]} lignes, {web_df.shape[1]} colonnes")
    print(f"LIAISON chargée : {liaison_df.shape[0]} lignes, {liaison_df.shape[1]} colonnes")

    # 1.3 Initialisation de DuckDB
    print_sep("INITIALISATION DE DUCKDB")
    global con
    con = duckdb.connect(str(DUCKDB_FILE))
    print(f"Base DuckDB utilisée : {DUCKDB_FILE}")

    # Nettoyage des objets si le script est relancé
    drop_sql = """
    DROP TABLE IF EXISTS stg_erp;
    DROP TABLE IF EXISTS stg_web;
    DROP TABLE IF EXISTS stg_liaison;

    DROP TABLE IF EXISTS erp_clean;
    DROP TABLE IF EXISTS web_clean;
    DROP TABLE IF EXISTS web_clean_before_dedup;
    DROP TABLE IF EXISTS liaison_clean;
    DROP TABLE IF EXISTS liaison_valid;
    DROP TABLE IF EXISTS produits_consolides;
    DROP TABLE IF EXISTS ca_par_produit;
    DROP TABLE IF EXISTS ca_global;
    DROP TABLE IF EXISTS stats_prix;
    DROP TABLE IF EXISTS vins_scores;
    DROP TABLE IF EXISTS vins_premium;
    DROP TABLE IF EXISTS vins_ordinaires;
    """
    con.execute(drop_sql)
    print("Anciennes tables supprimées si elles existaient.")

    # 1.4 Chargement des tables de staging
    print_sep("CHARGEMENT DES TABLES DE STAGING")
    con.register("erp_df_view", erp_df)
    con.register("web_df_view", web_df)
    con.register("liaison_df_view", liaison_df)

    con.execute("CREATE TABLE stg_erp AS SELECT * FROM erp_df_view")
    con.execute("CREATE TABLE stg_web AS SELECT * FROM web_df_view")
    con.execute("CREATE TABLE stg_liaison AS SELECT * FROM liaison_df_view")

    print(f"stg_erp créée : {sql_scalar(con, 'SELECT COUNT(*) FROM stg_erp')} lignes")
    print(f"stg_web créée : {sql_scalar(con, 'SELECT COUNT(*) FROM stg_web')} lignes")
    print(f"stg_liaison créée : {sql_scalar(con, 'SELECT COUNT(*) FROM stg_liaison')} lignes")


def check_input_files():
    """Vérifie que tous les fichiers d'entrée existent."""
    print_sep("VÉRIFICATION DES FICHIERS D'ENTRÉE")

    missing = []
    for file_path in [ERP_FILE, WEB_FILE, LIAISON_FILE]:
        if not file_path.exists():
            missing.append(str(file_path))

    if missing:
        print("Fichiers manquants :")
        for m in missing:
            print(f"- {m}")
        raise FileNotFoundError("Un ou plusieurs fichiers d'entrée sont absents.")

    print("Tous les fichiers d'entrée sont présents.")
    print(f"- ERP : {ERP_FILE}")
    print(f"- WEB : {WEB_FILE}")
    print(f"- LIAISON : {LIAISON_FILE}")


# ============================================================
# PHASE 2 : TRAITEMENT DES DONNÉES INDIVIDUELLES
# ============================================================
def phase_traitement():
    """
    PHASE 2 : TRAITEMENT DES DONNÉES INDIVIDUELLES
    - Dédoublonnage et nettoyage pour chaque fichier
    - Tests de qualité pour chaque source
    """
    print_sep("PHASE 2 : TRAITEMENT DES DONNÉES INDIVIDUELLES")

    # 2.1 Contrôle des doublons globaux
    print_sep("CONTRÔLE DES DOUBLONS")
    traitement_doublons_globaux()

    # 2.2 Traitement ERP
    print_sep("TRAITEMENT ERP")
    traitement_erp()
    test_erp_quality(con)

    # 2.3 Traitement WEB
    print_sep("TRAITEMENT WEB")
    traitement_web()
    test_web_quality(con)

    # 2.4 Traitement LIAISON
    print_sep("TRAITEMENT LIAISON")
    traitement_liaison()
    test_liaison_quality(con)


def traitement_doublons_globaux():
    """Contrôle des doublons sur les clés principales."""
    dup_erp = sql_scalar(con, """
    SELECT COUNT(*)
    FROM (
        SELECT product_id
        FROM stg_erp
        GROUP BY product_id
        HAVING COUNT(*) > 1
    ) t
    """)

    dup_web = sql_scalar(con, """
    SELECT COUNT(*)
    FROM (
        SELECT sku
        FROM stg_web
        WHERE post_type = 'product'
        GROUP BY sku
        HAVING COUNT(*) > 1
    ) t
    """)

    dup_liaison = sql_scalar(con, """
    SELECT COUNT(*)
    FROM (
        SELECT product_id
        FROM stg_liaison
        GROUP BY product_id
        HAVING COUNT(*) > 1
    ) t
    """)

    print(f"Nombre de clés ERP dupliquées sur product_id : {dup_erp}")
    print(f"Nombre de SKU WEB dupliqués sur les produits : {dup_web}")
    print(f"Nombre de product_id dupliqués dans la liaison : {dup_liaison}")


def traitement_erp():
    """Nettoyage et dédoublonnage des données ERP."""
    con.execute("""
    CREATE OR REPLACE TABLE erp_clean AS
    WITH typed AS (
        SELECT
            TRY_CAST(product_id AS BIGINT) AS product_id,
            TRY_CAST(onsale_web AS BIGINT) AS onsale_web,
            TRY_CAST(price AS DOUBLE) AS price,
            TRY_CAST(stock_quantity AS BIGINT) AS stock_quantity,
            TRIM(CAST(stock_status AS VARCHAR)) AS stock_status
        FROM stg_erp
    ),
    filtered AS (
        SELECT *
        FROM typed
        WHERE product_id IS NOT NULL
          AND onsale_web IS NOT NULL
          AND price IS NOT NULL
          AND stock_quantity IS NOT NULL
          AND stock_status IS NOT NULL
          AND stock_status <> ''
    ),
    ranked AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY product_id
                   ORDER BY product_id
               ) AS rn
        FROM filtered
    )
    SELECT
        product_id,
        onsale_web,
        price,
        stock_quantity,
        stock_status
    FROM ranked
    WHERE rn = 1
    """)

    nb_lines = sql_scalar(con, 'SELECT COUNT(*) FROM erp_clean')
    neg_price = sql_scalar(con, 'SELECT COUNT(*) FROM erp_clean WHERE price < 0')
    neg_stock = sql_scalar(con, 'SELECT COUNT(*) FROM erp_clean WHERE stock_quantity < 0')

    print(f"Nombre de lignes ERP après nettoyage : {nb_lines}")
    print(f"Prix négatifs dans ERP nettoyé : {neg_price}")
    print(f"Stocks négatifs dans ERP nettoyé : {neg_stock}")


def traitement_web():
    """Nettoyage et dédoublonnage des données WEB."""
    # Étape 1 : Nettoyage avant dédoublonnage
    con.execute("""
    CREATE OR REPLACE TABLE web_clean_before_dedup AS
    WITH typed AS (
        SELECT
            TRIM(CAST(sku AS VARCHAR)) AS sku,
            TRIM(CAST(post_title AS VARCHAR)) AS post_title,
            TRIM(CAST(post_status AS VARCHAR)) AS post_status,
            TRIM(CAST(post_type AS VARCHAR)) AS post_type,
            TRY_CAST(total_sales AS BIGINT) AS total_sales,
            TRY_CAST(average_rating AS DOUBLE) AS average_rating,
            TRY_CAST(rating_count AS BIGINT) AS rating_count,
            tax_status,
            tax_class,
            post_date,
            post_modified,
            post_name
        FROM stg_web
    ),
    filtered AS (
        SELECT *
        FROM typed
        WHERE post_type = 'product'
          AND sku IS NOT NULL
          AND sku <> ''
          AND post_title IS NOT NULL
          AND post_title <> ''
          AND total_sales IS NOT NULL
    )
    SELECT *
    FROM filtered
    """)

    nb_before = sql_scalar(con, "SELECT COUNT(*) FROM web_clean_before_dedup")
    print(f"Après nettoyage du fichier web : {nb_before} lignes")

    # Étape 2 : Dédoublonnage
    con.execute("""
    CREATE OR REPLACE TABLE web_clean AS
    WITH ranked AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY sku
                   ORDER BY
                       CASE WHEN post_status = 'publish' THEN 1 ELSE 2 END,
                       total_sales DESC
               ) AS rn
        FROM web_clean_before_dedup
    )
    SELECT
        sku,
        post_title,
        post_status,
        post_type,
        total_sales,
        average_rating,
        rating_count,
        tax_status,
        tax_class,
        post_date,
        post_modified,
        post_name
    FROM ranked
    WHERE rn = 1
    """)

    nb_after = sql_scalar(con, "SELECT COUNT(*) FROM web_clean")
    neg_sales = sql_scalar(con, "SELECT COUNT(*) FROM web_clean WHERE total_sales < 0")

    print(f"Après dédoublonnage du fichier web : {nb_after} lignes")
    print(f"Total_sales négatifs dans WEB nettoyé : {neg_sales}")


def traitement_liaison():
    """Nettoyage et dédoublonnage des données LIAISON."""
    con.execute("""
    CREATE OR REPLACE TABLE liaison_clean AS
    WITH typed AS (
        SELECT
            TRY_CAST(product_id AS BIGINT) AS product_id,
            TRIM(CAST(id_web AS VARCHAR)) AS id_web
        FROM stg_liaison
    ),
    filtered AS (
        SELECT *
        FROM typed
        WHERE product_id IS NOT NULL
          AND id_web IS NOT NULL
          AND id_web <> ''
    ),
    ranked AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY product_id
                   ORDER BY product_id
               ) AS rn
        FROM filtered
    )
    SELECT
        product_id,
        id_web
    FROM ranked
    WHERE rn = 1
    """)

    nb_lines = sql_scalar(con, 'SELECT COUNT(*) FROM liaison_clean')
    print(f"Nombre de lignes LIAISON après nettoyage : {nb_lines}")


# ============================================================
# PHASE 3 : FUSION ET JONCTURE
# ============================================================
def phase_fusion():
    """
    PHASE 3 : FUSION ET JONCTURE
    - Contrôle de cohérence des jointures
    - Fusion finale des données
    - Tests de fusion
    """
    print_sep("PHASE 3 : FUSION ET JONCTURE")

    # 3.1 Contrôle de cohérence des jointures
    print_sep("CONTRÔLE DE COHÉRENCE DES JOINTURES")

    bad_join_erp = sql_scalar(con, """
    SELECT COUNT(*)
    FROM liaison_clean l
    LEFT JOIN erp_clean e
        ON l.product_id = e.product_id
    WHERE e.product_id IS NULL
    """)

    bad_join_web = sql_scalar(con, """
    SELECT COUNT(*)
    FROM liaison_clean l
    LEFT JOIN web_clean w
        ON l.id_web = w.sku
    WHERE w.sku IS NULL
    """)

    print(f"Lignes de liaison sans correspondance ERP : {bad_join_erp}")
    print(f"Lignes de liaison sans correspondance WEB : {bad_join_web}")

    # 3.2 Création des liaisons valides
    con.execute("""
    CREATE OR REPLACE TABLE liaison_valid AS
    SELECT
        l.product_id,
        l.id_web
    FROM liaison_clean l
    INNER JOIN erp_clean e
        ON l.product_id = e.product_id
    INNER JOIN web_clean w
        ON l.id_web = w.sku
    """)

    nb_valid = sql_scalar(con, "SELECT COUNT(*) FROM liaison_valid")
    print(f"Nombre de lignes de liaison valides : {nb_valid}")

    # 3.3 Fusion finale
    print_sep("FUSION FINALE")
    con.execute("""
    CREATE OR REPLACE TABLE produits_consolides AS
    SELECT
        e.product_id,
        l.id_web,
        w.sku,
        e.onsale_web,
        e.price,
        e.stock_quantity,
        e.stock_status,
        w.post_title,
        w.post_status,
        w.post_type,
        w.total_sales,
        w.average_rating,
        w.rating_count,
        w.tax_status,
        w.tax_class,
        w.post_date,
        w.post_modified,
        w.post_name
    FROM erp_clean e
    INNER JOIN liaison_valid l
        ON e.product_id = l.product_id
    INNER JOIN web_clean w
        ON l.id_web = w.sku
    """)

    nb_consol = sql_scalar(con, "SELECT COUNT(*) FROM produits_consolides")
    print(f"Nombre total de lignes dans produits_consolides : {nb_consol}")

    # 3.4 Tests de fusion
    test_fusion_quality(con)


# ============================================================
# PHASE 4 : SCORES ET SEGMENTATION
# ============================================================
def phase_scores_segmentation():
    """
    PHASE 4 : SCORES ET SEGMENTATION
    - Calcul du chiffre d'affaires
    - Détection des vins premium
    - Extraction des métriques
    - Tests sur les scores
    """
    print_sep("PHASE 4 : SCORES ET SEGMENTATION")

    # 4.1 Calcul du chiffre d'affaires
    print_sep("CALCUL DU CHIFFRE D'AFFAIRES")
    con.execute("""
    CREATE OR REPLACE TABLE ca_par_produit AS
    SELECT
        product_id,
        sku,
        post_title,
        price AS prix_unitaire,
        total_sales AS quantite_vendue,
        price * total_sales AS chiffre_affaires
    FROM produits_consolides
    WHERE price IS NOT NULL
      AND total_sales IS NOT NULL
      AND price >= 0
      AND total_sales >= 0
    """)

    con.execute("""
    CREATE OR REPLACE TABLE ca_global AS
    SELECT
        SUM(chiffre_affaires) AS chiffre_affaires_total
    FROM ca_par_produit
    """)

    nb_ca = sql_scalar(con, "SELECT COUNT(*) FROM ca_par_produit")
    ca_total = sql_scalar(con, "SELECT chiffre_affaires_total FROM ca_global")
    ca_total = float(ca_total) if ca_total is not None else 0.0

    print(f"Nombre de lignes dans ca_par_produit : {nb_ca}")
    print(f"Chiffre d'affaires global : {ca_total:.2f}")

    # 4.2 Détection des vins premium
    print_sep("DÉTECTION DES VINS PREMIUM")
    con.execute("""
    CREATE OR REPLACE TABLE stats_prix AS
    SELECT
        AVG(prix_unitaire) AS moyenne_prix,
        STDDEV_POP(prix_unitaire) AS ecart_type_prix,
        QUANTILE_CONT(prix_unitaire, 0.25) AS q1,
        QUANTILE_CONT(prix_unitaire, 0.75) AS q3
    FROM ca_par_produit
    WHERE prix_unitaire IS NOT NULL
      AND prix_unitaire > 0
    """)

    con.execute("""
    CREATE OR REPLACE TABLE vins_scores AS
    SELECT
        c.*,
        s.moyenne_prix,
        s.ecart_type_prix,
        s.q1,
        s.q3,
        (s.q3 - s.q1) AS iqr,
        CASE
            WHEN s.ecart_type_prix IS NULL OR s.ecart_type_prix = 0 THEN NULL
            ELSE (c.prix_unitaire - s.moyenne_prix) / s.ecart_type_prix
        END AS z_score_prix,
        s.q3 + 1.5 * (s.q3 - s.q1) AS borne_haute_iqr
    FROM ca_par_produit c
    CROSS JOIN stats_prix s
    """)

    con.execute("""
    CREATE OR REPLACE TABLE vins_premium AS
    SELECT *,
           'PREMIUM' AS categorie_vin
    FROM vins_scores
    WHERE z_score_prix > 2
      AND prix_unitaire > borne_haute_iqr
    """)

    con.execute("""
    CREATE OR REPLACE TABLE vins_ordinaires AS
    SELECT *,
           'ORDINAIRE' AS categorie_vin
    FROM vins_scores
    WHERE NOT (z_score_prix > 2 AND prix_unitaire > borne_haute_iqr)
    """)

    nb_premium = sql_scalar(con, "SELECT COUNT(*) FROM vins_premium")
    nb_ordinaires = sql_scalar(con, "SELECT COUNT(*) FROM vins_ordinaires")

    print(f"Nombre de vins premium : {nb_premium}")
    print(f"Nombre de vins ordinaires : {nb_ordinaires}")

    # 4.3 Tests sur les scores
    test_scores_quality(con)


# ============================================================
# PHASE 5 : GÉNÉRATION DU RÉSUMÉ
# ============================================================
def phase_resume():
    """
    PHASE 5 : GÉNÉRATION DU RÉSUMÉ
    - Résumé final de toutes les étapes
    """
    print_sep("PHASE 5 : GÉNÉRATION DU RÉSUMÉ")

    # Récupération des métriques finales
    nb_erp_clean = sql_scalar(con, 'SELECT COUNT(*) FROM erp_clean')
    nb_web_clean = sql_scalar(con, 'SELECT COUNT(*) FROM web_clean')
    nb_liaison_valid = sql_scalar(con, 'SELECT COUNT(*) FROM liaison_valid')
    nb_consolides = sql_scalar(con, 'SELECT COUNT(*) FROM produits_consolides')
    ca_total = sql_scalar(con, "SELECT chiffre_affaires_total FROM ca_global")
    ca_total = float(ca_total) if ca_total is not None else 0.0
    nb_premium = sql_scalar(con, "SELECT COUNT(*) FROM vins_premium")
    nb_ordinaires = sql_scalar(con, "SELECT COUNT(*) FROM vins_ordinaires")

    print_sep("RÉSUMÉ FINAL")
    print("Workflow DuckDB terminé avec succès.")
    print(f"- Lignes ERP nettoyées : {nb_erp_clean}")
    print(f"- Lignes WEB nettoyées : {nb_web_clean}")
    print(f"- Lignes LIAISON valides : {nb_liaison_valid}")
    print(f"- Lignes consolidées : {nb_consolides}")
    print(f"- Chiffre d'affaires global : {ca_total:.2f}")
    print(f"- Nombre de vins premium : {nb_premium}")
    print(f"- Nombre de vins ordinaires : {nb_ordinaires}")

    print("\nFichiers générés :")
    print(f"- {DUCKDB_FILE}")
    print(f"- {CONSOLIDATION_FILE}")
    print(f"- {CA_FILE}")
    print(f"- {PREMIUM_FILE}")
    print(f"- {ORDINARY_FILE}")


# ============================================================
# PHASE 6 : EXPORT DES FICHIERS EXTERNES
# ============================================================
def phase_export():
    """
    PHASE 6 : EXPORT DES FICHIERS EXTERNES
    - Export des fichiers Excel et CSV
    """
    print_sep("PHASE 6 : EXPORT DES FICHIERS EXTERNES")

    # Consolidation en Excel
    consolidation_df = sql_df(con, """
    SELECT *
    FROM produits_consolides
    ORDER BY product_id
    """)
    consolidation_df.to_excel(CONSOLIDATION_FILE, index=False)
    print(f"Fichier créé : {CONSOLIDATION_FILE}")

    # CA par produit en Excel
    ca_df = sql_df(con, """
    SELECT *
    FROM ca_par_produit
    ORDER BY chiffre_affaires DESC
    """)
    ca_df.to_excel(CA_FILE, index=False)
    print(f"Fichier créé : {CA_FILE}")

    # Premium en CSV
    con.execute(f"""
    COPY (
        SELECT *
        FROM vins_premium
        ORDER BY prix_unitaire DESC
    )
    TO '{PREMIUM_FILE.as_posix()}'
    WITH (HEADER, DELIMITER ',')
    """)
    print(f"Fichier créé : {PREMIUM_FILE}")

    # Ordinaires en CSV
    con.execute(f"""
    COPY (
        SELECT *
        FROM vins_ordinaires
        ORDER BY prix_unitaire DESC
    )
    TO '{ORDINARY_FILE.as_posix()}'
    WITH (HEADER, DELIMITER ',')
    """)
    print(f"Fichier créé : {ORDINARY_FILE}")

    con.close()


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================
if __name__ == "__main__":
    try:
        print("Tests intégrés : assertions Python exécutées pendant le run (pas de pytest).")

        # Phase 1 : Ingestion
        phase_ingestion()

        # Phase 2 : Traitement individuel
        phase_traitement()

        # Phase 3 : Fusion et joncture
        phase_fusion()

        # Phase 4 : Scores et segmentation
        phase_scores_segmentation()

        # Phase 5 : Résumé
        phase_resume()

        # Phase 6 : Export
        phase_export()

        print("\n🎉 TRAITEMENT TERMINÉ AVEC SUCCÈS !")

    except Exception as e:
        print(f"\n❌ ERREUR : {e}")
        raise
