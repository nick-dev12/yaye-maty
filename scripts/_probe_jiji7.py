import re
from pathlib import Path
from lxml import html as lh

text = Path('scripts/_jiji_probe/ad_detail.html').read_text(encoding='utf-8')
tree = lh.fromstring(text)

# all class names containing advert/seller/attr/price
classes = set(re.findall(r'class=["\']([^"\']+)["\']', text))
interesting = sorted(
    c for c in classes
    if any(k in c.lower() for k in ('advert', 'seller', 'attr', 'price', 'contact', 'badge', 'owner', 'stat'))
)
for c in interesting[:80]:
    print(c)

print('---ATTRS---')
for el in tree.xpath('//*[contains(@class,"b-advert-attribute") or contains(@class,"attr-name") or contains(@class,"qa-advert-attribute")]')[:30]:
    print(repr(el.get('class')), '=>', ' '.join(el.text_content().split())[:120])

print('---SELLER BLOCKS---')
for el in tree.xpath('//*[contains(@class,"b-seller") or contains(@class,"seller-info") or contains(@class,"owner")]')[:20]:
    print(repr(el.get('class')), '=>', ' '.join(el.text_content().split())[:160])

# regex views
m = re.search(r'(\d+)\s*vus', text, re.I)
print('views re', m.group(0) if m else None)
m = re.search(r'Prix\s*(fixe|négociable|negociable)', text, re.I)
print('price type', m.group(0) if m else None)
