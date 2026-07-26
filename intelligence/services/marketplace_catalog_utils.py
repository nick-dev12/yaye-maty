"""Utilitaires catalogue marketplace — slugs et chemins Jumia/Jiji (pilotés mots-clés)."""

from __future__ import annotations

from intelligence.nlp_taxonomy import PRODUCT_CATALOG

# Catégorie produit Paramètres → chemin listing Jumia (pas de ?q=)
PRODUCT_CATEGORY_JUMIA_PATHS: dict[str, str] = {
    'irrigation': '/terrasse-jardin-exterieur/',
    'solaire_pompage': '/electronique/',
    'tracteurs_machinisme': '/terrasse-jardin-exterieur/',
    'semences_engrais': '/supermarche/',
    'elevage_alimentation': '/terrasse-jardin-exterieur/',
    'marche_prix': '/telephones-tablettes/',
    'formation_conseil': '/informatique/',
    'autre': '',
    # Extensions généralistes
    'telephones': '/telephones-tablettes/',
    'electronique': '/electronique/',
    'electromenager': '/electromenager/',
    'mode': '/mode/',
    'beaute': '/sante-beaute/',
    'maison': '/maison-cuisine-jardin/',
    'informatique': '/informatique/',
    'sport': '/sport/',
    'supermarche': '/supermarche/',
}

PRODUCT_CATEGORY_JIJI_PATHS: dict[str, str] = {
    'irrigation': '/farm-machinery-equipment',
    'solaire_pompage': '/solar-energy-products',
    'tracteurs_machinisme': '/farm-machinery-equipment',
    'semences_engrais': '/agriculture-and-foodstuff',
    'elevage_alimentation': '/farm-machinery-equipment',
    'marche_prix': '/electronics',
    'formation_conseil': '/electronics',
    'autre': '',
    'telephones': '/mobile-phones-tablets',
    'electronique': '/electronics',
    'electromenager': '/home-appliances',
    'mode': '/clothing',
    'beaute': '/health-beauty',
    'maison': '/home-garden',
    'informatique': '/computer-accessories',
    'sport': '/sport-equipment',
    'supermarche': '/meals-drink',
}


def resolve_catalog_slug(
    name: str,
    keyword: str = '',
    *,
    product_category: str = '',
) -> str:
    """
    Slug catalogue pour jointure signaux / Top 10.

    Priorité : product_category Paramètres → heuristique mots-clés catalogue.
    """
    cat = (product_category or '').strip()
    if cat in PRODUCT_CATALOG:
        return cat

    blob = f'{name} {keyword}'.lower()
    best_slug = ''
    best_hits = 0
    for slug, meta in PRODUCT_CATALOG.items():
        hits = sum(1 for kw in meta.get('keywords', ()) if kw.lower() in blob)
        if hits > best_hits:
            best_hits = hits
            best_slug = slug
    return best_slug if best_hits > 0 else ''


def resolve_jumia_category_path(keyword: str, *, product_category: str = '') -> str:
    """Chemin catégorie Jumia — product_category Paramètres prioritaire, sinon mot-clé."""
    from intelligence.services.jumia_scraper import KEYWORD_CATEGORY_PATHS

    cat = (product_category or '').strip()
    if cat in PRODUCT_CATEGORY_JUMIA_PATHS:
        return PRODUCT_CATEGORY_JUMIA_PATHS[cat]

    key = ' '.join((keyword or '').strip().lower().split())
    if key in KEYWORD_CATEGORY_PATHS:
        return KEYWORD_CATEGORY_PATHS[key]
    for needle, path in KEYWORD_CATEGORY_PATHS.items():
        if needle in key or key in needle:
            return path
    # Pas de secteur par défaut — accueil + filtre mot-clé en repli
    return ''


def resolve_jiji_category_path(keyword: str, *, product_category: str = '') -> str:
    """Chemin catégorie Jiji — product_category Paramètres prioritaire."""
    from intelligence.services.jiji_scraper import KEYWORD_CATEGORY_PATHS

    cat = (product_category or '').strip()
    if cat in PRODUCT_CATEGORY_JIJI_PATHS:
        return PRODUCT_CATEGORY_JIJI_PATHS[cat]

    key = ' '.join((keyword or '').strip().lower().split())
    if key in KEYWORD_CATEGORY_PATHS:
        return KEYWORD_CATEGORY_PATHS[key]
    for needle, path in KEYWORD_CATEGORY_PATHS.items():
        if needle in key or key in needle:
            return path
    return ''
