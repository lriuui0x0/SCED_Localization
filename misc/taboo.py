import urllib.request
import requests
import json
import polib
import os

langs = [
    'es',
    'de',
    'it',
    'fr',
    'ko',
    'uk',
    'pl',
    'ru',
    'zh',
]
translations = {lang: [] for lang in langs}
pofile = 'tmp.po'

print(f'Downloading taboo data...')
taboos = json.loads(requests.get(f'https://arkhamdb.com/api/public/taboos/').json()[0]['cards'])

for lang in langs:
    print(f'Downloading data for {lang}...')
    api = f'https://{lang}.arkhamdb.com/api/public/cards/'
    cards = requests.get(api).json()
    data = {}
    for card in cards:
        data[card['code']] = card

    print(f'Downloading taboo translation for {lang}...')
    urllib.request.urlretrieve(f'https://raw.githubusercontent.com/zzorba/arkham-cards-data/master/i18n/{lang}/taboos.po', pofile)
    po = polib.pofile(pofile)

    for taboo in taboos:
        card = data[taboo['code']]
        card['code'] = f'{card["code"]}-t'
        if 'text' in taboo:
            taboo_text = taboo['text'].replace('\n', ' ')
            for entry in po:
                taboo_text_variant = taboo_text.replace('“', '"').replace('”', '"')
                if entry.msgid in [taboo_text, taboo_text_variant]:
                    taboo_text = entry.msgstr
                    break
            card['taboo_text'] = taboo_text
        if 'xp' in taboo:
            card['taboo_xp'] = taboo['xp']
        card['WARNING'] = 'NOT UPDATED'
        translations[lang].append(card)

    with open(f'translations/{lang}/taboo.json', 'w', encoding='utf-8') as file:
        file.write(json.dumps(translations[lang], indent=2, ensure_ascii=False))

try:
    os.remove(pofile)
except:
    pass

