from pathlib import Path
from lxml import html as lh
from urllib.parse import urljoin

BASE = 'https://jiji.sn'
text = Path('scripts/_jiji_probe/cat_farm-machinery-equipment.html').read_text(encoding='utf-8')
tree = lh.fromstring(text)
art = tree.xpath('//*[contains(@class,"qa-advert-list-item")]')[0]
print('tag', art.tag, 'class', art.get('class'))
print('parent', art.getparent().tag, art.getparent().get('class'))
print('ancestors a', art.xpath('./ancestor::a[@href]/@href'))
print('desc a', art.xpath('.//a[@href]/@href')[:5])
print('self a', art.xpath('self::a/@href'))
# sibling
prev = art.getprevious()
print('prev', prev.tag if prev is not None else None, getattr(prev, 'get', lambda x: None)('href') if prev is not None else None)
# outer HTML snippet
print(lh.tostring(art, encoding='unicode')[:500])
# try parent chain
p = art
for i in range(5):
    p = p.getparent()
    if p is None:
        break
    print('up', i, p.tag, (p.get('class') or '')[:60], p.get('href'))
