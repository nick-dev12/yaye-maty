"""
Utilitaires graphiques sans dégradés — couleurs unies uniquement.
"""

DONUT_COLOR_MAP = {
    'orange': '#F25C19',
    'bleu': '#2E7DB5',
    'jaune': '#F0B429',
    'noir': '#1A1A1A',
    'gris': '#8C8C8C',
}


def build_donut_segments(items, count_key='count', stroke_key='stroke', total=None):
    """
    Construit les segments SVG pour un donut chart (couleurs unies).

    Chaque item doit avoir une clé de quantité et une couleur (hex ou nom palette).
    """
    if total is None:
        total = sum(item.get(count_key, 0) for item in items)

    if not total:
        return [{
            'stroke': DONUT_COLOR_MAP['gris'],
            'dash': 100,
            'gap': 0,
            'offset': 0,
        }]

    segments = []
    offset = 0

    for item in items:
        count = item.get(count_key, 0)
        if count <= 0:
            continue

        pct = (count / total) * 100
        stroke = item.get(stroke_key)
        if not stroke:
            color_name = item.get('color', 'gris')
            stroke = DONUT_COLOR_MAP.get(color_name, item.get('hex_color', DONUT_COLOR_MAP['gris']))

        segments.append({
            'stroke': stroke,
            'dash': round(pct, 2),
            'gap': round(100 - pct, 2),
            'offset': round(offset, 2),
        })
        offset -= pct

    return segments or [{
        'stroke': DONUT_COLOR_MAP['gris'],
        'dash': 100,
        'gap': 0,
        'offset': 0,
    }]
