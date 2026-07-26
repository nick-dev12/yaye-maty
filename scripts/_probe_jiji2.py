import re
from pathlib import Path

from lxml import html as lh

p = Path('scripts/_jiji_probe/search_pompe.html')
text = p.read_text(encoding='utf-8')

m = re.search(r'window\.__NUXT__\s*=\s*(.*?);\s*</script>', text, re.S)
if not m:
    m = re.search(r'__NUXT__\s*=\s*(.*?)</script>', text, re.S)
print('nuxt match', bool(m), 'len', len(m.group(1)) if m else 0)
if m:
    raw = m.group(1).strip()
    Path('scripts/_jiji_probe/nuxt_raw.js').write_text(raw[:80000], encoding='utf-8')
    print(raw[:800])
    print('---TAIL---')
    print(raw[-400:])

for pat in ['qa-advert', 'advert-title', 'b-list-advert', 'price', 'negotiable', 'data-id', 'h-advert']:
    print(pat, text.lower().count(pat.lower()))

classes = set(re.findall(r'class=["\']([^"\']*advert[^"\']*)["\']', text, re.I))
print('advert classes', list(classes)[:30])

hrefs = lh.fromstring(text).xpath('//a/@href')
print('href sample', [h for h in hrefs if h and h.startswith('/')][:40])

# categories on home
home = Path('scripts/_jiji_probe/home.html').read_text(encoding='utf-8')
hrefs_h = lh.fromstring(home).xpath('//a/@href')
cats = [h for h in hrefs_h if h and h.startswith('/') and 2 < len(h) < 60]
print('home cats', list(dict.fromkeys(cats))[:40])
