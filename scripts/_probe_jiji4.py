from pathlib import Path
import re
from lxml import html as lh

for name in ['cat_farm-machinery-equipment.html', 'search_pompe.html', 'cat_agriculture-and-foodstuff.html']:
    p = Path('scripts/_jiji_probe') / name
    if not p.exists():
        print('missing', name)
        continue
    text = p.read_text(encoding='utf-8')
    print('===', name, len(text))
    print('qa-advert-list-item', text.count('qa-advert-list-item'))
    print('b-list-advert-base', text.count('b-list-advert-base'))
    tree = lh.fromstring(text)
    items = tree.xpath('//*[contains(@class,"qa-advert-list-item")]')
    print('xpath items', len(items))
    # maybe items are in noscript or comment?
    # try find advert html fragments
    m = re.search(r'qa-advert-list-item.{0,200}', text)
    print('snippet', m.group(0)[:180] if m else None)
    hrefs = [h for h in tree.xpath('//a/@href') if h and '.html' in h and 'jiji-pages' not in h][:8]
    print('html hrefs', hrefs)
