"""Taxonomie NLP métier — équipement agricole Sénégal."""

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    'irrigation': (
        'irrigation', 'pompe', 'arrosage', 'goutte', 'eau', 'forage', 'puit',
    ),
    'solaire_pompage': (
        'solaire', 'photovoltaique', 'panneau', 'energie', 'batterie',
    ),
    'tracteurs_machinisme': (
        'tracteur', 'charrue', 'moissonneuse', 'semoir', 'machine', 'engin',
    ),
    'semences_engrais': (
        'semence', 'engrais', 'fertilisa', 'npk', 'uree', 'phyto', 'herbicide',
    ),
    'elevage_alimentation': (
        'elevage', 'volaille', 'poulet', 'betail', 'vache', 'mouton', 'aliment',
        'provende', 'cage', 'poulailler',
    ),
    'marche_prix': (
        'prix', 'marche', 'vente', 'achat', 'commercial', 'fournisseur', 'commande',
    ),
    'formation_conseil': (
        'formation', 'conseil', 'technique', 'agronome', 'cooperative', 'saed',
    ),
}

# Catalogue produits agricoles — extraction + Top 10 recommandations
PRODUCT_CATALOG: dict[str, dict] = {
    'motopompe': {
        'label': 'Motopompe / Pompe irrigation',
        'category': 'irrigation',
        'keywords': ('motopompe', 'pompe', 'pompage', 'forage', 'irrigation'),
    },
    'goutte_a_goutte': {
        'label': "Système goutte-à-goutte",
        'category': 'irrigation',
        'keywords': ('goutte', 'goutte a goutte', 'goutte-a-goutte', 'drip', 'arrosage'),
    },
    'pompe_solaire': {
        'label': 'Pompe solaire / Kit solaire',
        'category': 'solaire_pompage',
        'keywords': ('pompe solaire', 'solaire', 'photovoltaique', 'panneau solaire', 'kit solaire'),
    },
    'mini_tracteur': {
        'label': 'Mini tracteur',
        'category': 'tracteurs_machinisme',
        'keywords': ('mini tracteur', 'minitracteur', 'tracteur compact', 'micro tracteur'),
    },
    'tracteur': {
        'label': 'Tracteur agricole',
        'category': 'tracteurs_machinisme',
        'keywords': ('tracteur', 'charrue', 'moissonneuse', 'semoir'),
    },
    'charrue': {
        'label': 'Charrue / Outil labour',
        'category': 'tracteurs_machinisme',
        'keywords': ('charrue', 'labour', 'herse', 'cultivateur'),
    },
    'semences': {
        'label': 'Semences / Graines',
        'category': 'semences_engrais',
        'keywords': ('semence', 'graine', 'semis', 'npk'),
    },
    'engrais': {
        'label': 'Engrais / Fertilisant',
        'category': 'semences_engrais',
        'keywords': ('engrais', 'fertilisa', 'uree', 'uree', 'npk', 'herbicide', 'phyto'),
    },
    'couveuse': {
        'label': 'Couveuse / Incubateur',
        'category': 'elevage_alimentation',
        'keywords': ('couveuse', 'incubateur', 'incubation', 'oeuf', 'oeufs'),
    },
    'poulailler': {
        'label': 'Poulailler / Élevage volaille',
        'category': 'elevage_alimentation',
        'keywords': ('poulailler', 'volaille', 'poulet', 'poule', 'cage', 'aliment volaille'),
    },
    'provende': {
        'label': 'Provende / Aliment bétail',
        'category': 'elevage_alimentation',
        'keywords': ('provende', 'aliment betail', 'bovin', 'mouton', 'vache', 'elevage'),
    },
    'moto_pompe_diesel': {
        'label': 'Groupe motopompe diesel',
        'category': 'irrigation',
        'keywords': ('groupe electrogene', 'diesel', 'motopompe diesel', 'generator'),
    },
}
