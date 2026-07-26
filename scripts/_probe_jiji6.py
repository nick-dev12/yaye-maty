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
s = requests.Session()
s.headers.update({'User-Agent': UA, 'Accept-Language': 'fr-FR,fr;q=0.9'})

r = s.get(BASE + '/farm-machinery-equipment', timeout=30)
tree = lh.fromstring(r.text)
cards = []
for art in tree.xpath('//a[contains(@class,"qa-advert-list-item")]'):
    href = art.get('href') or ''
    title_el = art.xpath('.//*[contains(@class,"qa-advert-title")]')
    price_el = art.xpath('.//*[contains(@class,"qa-advert-price")]')
    loc_el = art.xpath('.//*[contains(@class,"b-list-advert-base__location") or contains(@class,"b-list-advert__region")]')
    title = (title_el[0].text_content() if title_el else '').strip()
    price = (price_el[0].text_content() if price_el else '').strip()
    loc = (loc_el[0].text_content() if loc_el else '').strip()
    if href and title:
        cards.append({'url': urljoin(BASE, href.split('?')[0]), 'title': title, 'price': price, 'loc': ' '.join(loc.split())})
print('cards', len(cards))
for c in cards[:5]:
    print(c)

ad = cards[0]['url']
r = s.get(ad, timeout=30)
print('AD', r.status_code, ad, len(r.text))
(OUT / 'ad_detail.html').write_text(r.text, encoding='utf-8')
tree = lh.fromstring(r.text)
blob = ' '.join(tree.text_content().split())
print('blob sample', blob[:400])
for needle in ['Négociable', 'Negotiable', 'vues', 'Vues', 'Occasion', 'Neuf', 'Afficher le contact', 'Vendeur', 'Premium', 'vérifié', 'Verified']:
    print(needle, needle.lower() in blob.lower())

# useful selectors
for xp in [
    '//*[contains(@class,"qa-advert-price")]',
    '//*[contains(@class,"b-advert-title")]',
    '//*[contains(@class,"b-advert-seller")]',
    '//*[contains(@class,"seller")]',
    '//*[contains(@class,"views")]',
    '//*[contains(@class,"negotiable")]',
    '//*[contains(@class,"condition")]',
    '//button[contains(.,"contact") or contains(.,"Contact") or contains(.,"Afficher")]',
]:
    els = tree.xpath(xp)
    print(xp, len(els), repr((els[0].text_content()[:100] if els else '')))

for m in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', r.text, re.I | re.S):
    try:
        data = json.loads(m.group(1))
        print('LD', json.dumps(data, ensure_ascii=False)[:800])
    except Exception as e:
        print('LD err', e)
