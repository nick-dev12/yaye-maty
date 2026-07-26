import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from lxml import html as lh

UA = (
    'YayematyMarketBot/1.0 (+https://yayematy.local/contact; '
    'market-intelligence; respectful)'
)
BASE = 'https://jiji.sn'
OUT = Path('scripts/_jiji_probe')


def parse_cards(html: str) -> list[dict]:
    tree = lh.fromstring(html)
    cards = []
    for art in tree.xpath('//*[contains(@class,"qa-advert-list-item")]'):
        links = art.xpath('.//a[@href]')
        href = ''
        for a in links:
            h = a.get('href') or ''
            if '.html' in h:
                href = h
                break
        title_el = art.xpath('.//*[contains(@class,"qa-advert-title")]')
        price_el = art.xpath('.//*[contains(@class,"qa-advert-price")]')
        loc_el = art.xpath('.//*[contains(@class,"location")]')
        title = (title_el[0].text_content() if title_el else '').strip()
        price = (price_el[0].text_content() if price_el else '').strip()
        loc = (loc_el[0].text_content() if loc_el else '').strip()
        if href and title:
            cards.append({
                'url': urljoin(BASE, href.split('?')[0]),
                'title': title[:200],
                'price': price,
                'location': ' '.join(loc.split())[:160],
            })
    return cards


def main() -> None:
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept-Language': 'fr-FR,fr;q=0.9'})

    # Category listing without query (preferred)
    for path in [
        '/agriculture-and-foodstuff',
        '/farm-machinery-equipment',
        '/solar-energy-products',
        '/power-equipments',
    ]:
        r = s.get(BASE + path, timeout=30)
        print(path, r.status_code, r.url[:90], len(r.text))
        cards = parse_cards(r.text)
        print('  cards', len(cards), cards[:2])
        (OUT / f'cat_{path.strip("/").replace("/", "_")}.html').write_text(r.text, encoding='utf-8')

    # Search fallback
    r = s.get(BASE + '/search?query=motopompe', timeout=30)
    cards = parse_cards(r.text)
    print('search motopompe', len(cards))
    for c in cards[:5]:
        print(' ', c)

    if not cards:
        return
    ad_url = cards[0]['url']
    r = s.get(ad_url, timeout=30)
    print('AD', r.status_code, ad_url, len(r.text))
    (OUT / 'ad_detail.html').write_text(r.text, encoding='utf-8')
    tree = lh.fromstring(r.text)
    # interesting text markers
    blob = tree.text_content()
    for needle in ['Négociable', 'Negotiable', 'Vues', 'Occasion', 'Neuf', 'Vendeur', 'Afficher', 'Contact', 'Premium', 'Vérifié']:
        print(needle, needle.lower() in blob.lower())
    # classes
    for cls in ['qa-advert-price', 'b-advert-title', 'b-advert-info', 'seller', 'views', 'condition']:
        els = tree.xpath(f'//*[contains(@class,"{cls}")]')
        print('cls', cls, len(els), (els[0].text_content()[:80].strip() if els else ''))
    # ld+json
    for m in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', r.text, re.I | re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        print('LD', json.dumps(data, ensure_ascii=False)[:600])


if __name__ == '__main__':
    main()
