"""Probe Jiji.sn structure for scraper design."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from lxml import html as lh

UA = (
    'YayematyMarketBot/1.0 (+https://yayematy.local/contact; '
    'market-intelligence; respectful)'
)
OUT = Path(__file__).resolve().parent / '_jiji_probe'


def main() -> None:
    OUT.mkdir(exist_ok=True)
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept-Language': 'fr-FR,fr;q=0.9'})

    for label, url in [
        ('home', 'https://jiji.sn/'),
        ('search_pompe', 'https://jiji.sn/search?query=pompe+solaire'),
        ('search_tracteur', 'https://jiji.sn/search?query=tracteur'),
        ('farm', 'https://jiji.sn/farm-machines-and-equipment'),
        ('agriculture', 'https://jiji.sn/agriculture'),
        ('animaux', 'https://jiji.sn/animaux-et-produits-agricoles'),
    ]:
        try:
            r = s.get(url, timeout=30, allow_redirects=True)
        except Exception as exc:
            print(label, 'ERR', exc)
            continue
        print(label, r.status_code, r.url[:100], 'len', len(r.text))
        (OUT / f'{label}.html').write_text(r.text, encoding='utf-8')
        tree = lh.fromstring(r.text)
        hrefs = [h for h in tree.xpath('//a/@href') if h]
        ad_like = [
            h for h in hrefs
            if re.search(r'-\d{6,}(\.html)?$', h) or '/ad/' in h or '/annonce' in h
        ]
        uniq = list(dict.fromkeys(ad_like))[:12]
        print('  ads', uniq[:8])
        for key in ('__NEXT_DATA__', '__NUXT__', 'window.__INITIAL', 'application/ld+json'):
            if key in r.text:
                print('  marker', key)
        # try extract next data
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r.text,
            re.I | re.S,
        )
        if m:
            data = json.loads(m.group(1))
            (OUT / f'{label}_next.json').write_text(
                json.dumps(data, ensure_ascii=False, indent=2)[:200000],
                encoding='utf-8',
            )
            print('  next keys', list(data.keys())[:10])

    # open first ad if any from search
    search = (OUT / 'search_pompe.html').read_text(encoding='utf-8')
    tree = lh.fromstring(search)
    hrefs = list(dict.fromkeys(tree.xpath('//a/@href')))
    candidates = [
        h for h in hrefs
        if re.search(r'-\d{6,}', h or '') and 'jiji' not in (h or '').split('/')[-1][:4]
    ]
    # broader
    candidates = [
        h for h in hrefs
        if h and re.search(r'\d{7,}', h) and not h.startswith('javascript')
    ]
    print('candidates', candidates[:10])
    if candidates:
        href = candidates[0]
        if href.startswith('/'):
            href = 'https://jiji.sn' + href
        r = s.get(href, timeout=30)
        print('AD', r.status_code, r.url, len(r.text))
        (OUT / 'ad_sample.html').write_text(r.text, encoding='utf-8')
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r.text,
            re.I | re.S,
        )
        if m:
            data = json.loads(m.group(1))
            (OUT / 'ad_next.json').write_text(
                json.dumps(data, ensure_ascii=False, indent=2)[:300000],
                encoding='utf-8',
            )
            print('ad next keys', list(data.keys()))
            props = data.get('props', {}).get('pageProps', {})
            print('pageProps keys', list(props.keys())[:30])


if __name__ == '__main__':
    main()
