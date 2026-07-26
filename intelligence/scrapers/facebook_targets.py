"""
Cibles Facebook marché agricole Sénégal — groupes, fil et recherches.

Remplacez GROUP_URL par l'URL exacte de vos groupes rejoints (admin ou add_facebook_group).
"""

from __future__ import annotations

from urllib.parse import quote

# Fil agrégé des groupes rejoints (nécessite session connectée)
FACEBOOK_GROUPS_FEED_URL = 'https://www.facebook.com/groups/feed/'

FACEBOOK_DEFAULT_TARGETS: list[dict] = [
    {
        'label': 'Facebook — Fil de vos groupes',
        'url': FACEBOOK_GROUPS_FEED_URL,
        'max_posts': 15,
        'is_active': True,
        'scrape_comments': False,
    },
    {
        'label': 'Facebook recherche posts « agriculture senegal »',
        'url': f'https://www.facebook.com/search/posts?q={quote("agriculture senegal")}',
        'max_posts': 12,
        'is_active': True,
        'scrape_comments': False,
    },
    {
        'label': 'Facebook recherche posts « materiel agricole dakar »',
        'url': f'https://www.facebook.com/search/posts?q={quote("materiel agricole dakar")}',
        'max_posts': 12,
        'is_active': True,
        'scrape_comments': False,
    },
    {
        'label': 'Facebook recherche posts « motopompe senegal »',
        'url': f'https://www.facebook.com/search/posts?q={quote("motopompe senegal")}',
        'max_posts': 10,
        'is_active': False,
        'scrape_comments': False,
    },
]

# Modèle — ajoutez vos groupes via : python manage.py add_facebook_group
FACEBOOK_GROUP_TEMPLATE = {
    'label': 'Facebook groupe — {name}',
    'url': '',  # ex. https://www.facebook.com/groups/123456789/
    'max_posts': 15,
    'is_active': True,
    'scrape_comments': False,
}
