"""
Cibles TikTok orientées marché sénégalais — YAYEMATY MARKET.

Stratégie de ciblage (pas de filtre pays natif sur TikTok) :
1. Sémantique : hashtags et recherches locales (FR + géographie SN).
2. Réseau : à terme, profils d'influenceurs agricoles sénégalais.
3. IP : proxy résidentiel Dakar via SOCIAL_SCRAPER['PROXY_SERVER'].
"""

from __future__ import annotations

from urllib.parse import quote

# Hashtags locaux — levier sémantique principal
SENEGAL_HASHTAG_TARGETS: list[dict] = [
    {
        'label': 'TikTok #AgricultureSenegal',
        'url': 'https://www.tiktok.com/tag/agriculturesenegal',
        'max_posts': 15,
    },
    {
        'label': 'TikTok #ElevageSenegal',
        'url': 'https://www.tiktok.com/tag/elevagesenegal',
        'max_posts': 15,
    },
    {
        'label': 'TikTok #AgriSN',
        'url': 'https://www.tiktok.com/tag/agrisn',
        'max_posts': 15,
    },
    {
        'label': 'TikTok #SenegalAgriculture',
        'url': 'https://www.tiktok.com/tag/senegalagriculture',
        'max_posts': 15,
    },
    {
        'label': 'TikTok #AgriculteurSenegal',
        'url': 'https://www.tiktok.com/tag/agriculteursenegal',
        'max_posts': 15,
    },
]

# Recherches TikTok — termes géographiques couplés au besoin
SENEGAL_SEARCH_TARGETS: list[dict] = [
    {
        'label': 'TikTok recherche « agriculture senegal »',
        'url': f'https://www.tiktok.com/search?q={quote("agriculture senegal")}',
        'max_posts': 12,
    },
    {
        'label': 'TikTok recherche « tracteur dakar »',
        'url': f'https://www.tiktok.com/search?q={quote("tracteur dakar")}',
        'max_posts': 12,
    },
    {
        'label': 'TikTok recherche « materiel agricole senegal »',
        'url': f'https://www.tiktok.com/search?q={quote("materiel agricole senegal")}',
        'max_posts': 12,
    },
    {
        'label': 'TikTok recherche « pompe solaire senegal »',
        'url': f'https://www.tiktok.com/search?q={quote("pompe solaire senegal")}',
        'max_posts': 12,
    },
    {
        'label': 'TikTok recherche « elevage senegal »',
        'url': f'https://www.tiktok.com/search?q={quote("elevage senegal")}',
        'max_posts': 12,
    },
    {
        'label': 'TikTok recherche « touba agriculture »',
        'url': f'https://www.tiktok.com/search?q={quote("touba agriculture")}',
        'max_posts': 10,
    },
]

# Anciennes cibles génériques à désactiver (hors marché SN)
LEGACY_GENERIC_URLS: tuple[str, ...] = (
    'https://www.tiktok.com/tag/agriculteur',
    'https://www.tiktok.com/tag/agriculture',
    'https://www.tiktok.com/tag/elevage',
)


def get_all_senegal_targets() -> list[dict]:
    """Retourne toutes les cibles Sénégal prêtes pour SocialScrapeTarget."""
    targets = []
    for item in SENEGAL_HASHTAG_TARGETS + SENEGAL_SEARCH_TARGETS:
        targets.append({
            'label': item['label'],
            'platform': 'tiktok',
            'url': item['url'],
            'max_posts': item['max_posts'],
            'region': 'SN',
            'scrape_comments': True,
            'max_comments': 20,
            'is_active': True,
        })
    return targets
