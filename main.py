import argparse
import csv
import json
import os
import sys
import shutil
import subprocess
import re
import base64
import requests
import inspect
import importlib
import urllib.request
import time
import dropbox
import uuid
import glob
from PIL import Image

steps = ['translate', 'generate', 'pack', 'upload', 'update']
langs = ['es', 'de', 'it', 'fr', 'ko', 'uk', 'pl', 'ru', 'zh_TW', 'zh_CN']

parser = argparse.ArgumentParser()
parser.add_argument('--lang', default='zh_CN', choices=langs, help='The language to translate into')
parser.add_argument('--se-executable', default=r'C:\Program Files\StrangeEons\bin\eons.exe', help='The Strange Eons executable path')
parser.add_argument('--filter', default='True', help='A Python expression filter for what cards to process')
parser.add_argument('--cache-dir', default='cache', help='The directory to keep intermediate resources during processing')
parser.add_argument('--decks-dir', default='decks', help='The directory to keep translated deck images')
parser.add_argument('--mod-dir', default=None, help='The directory to the mod repository')
parser.add_argument('--step', default=None, choices=steps, help='The particular automation step to run')
parser.add_argument('--dropbox-token', default=None, help='The dropbox token for uploading translated deck images')
args = parser.parse_args()

def get_lang_code_region():
    parts = args.lang.split('_')
    if len(parts) > 1:
        return parts[0], parts[1]
    else:
        return parts[0], ''

def process_lang(value):
    # NOTE: Import language dependent processing functions.
    lang_code, region = get_lang_code_region()
    lang_folder = f'translations/{lang_code}'
    if lang_folder not in sys.path:
        sys.path.insert(1, lang_folder)
    module_name = 'transform'
    if region:
        module_name += f'_{region}'
    try:
        module = importlib.import_module(module_name)
    except:
        pass

    # NOTE: Get the corresponding process function from stack frame. Therefore it's important to call this function from the correct 'get_se_xxx' function.
    attr = inspect.stack()[1].function.replace('get_se_', '')
    func_name = f'transform_{attr}'
    func = getattr(module, func_name, None)
    return func(value) if func else value

# NOTE: ADB data may contain explicit null fields, that should be treated the same as missing.
def get_field(card, key, default):
    return default if card.get(key) is None else card.get(key)

def get_se_subtype(card):
    subtype_map = {
        'weakness': 'Weakness',
        'basicweakness': 'BasicWeakness',
        None: 'None',
    }
    subtype = get_field(card, 'subtype_code', None)
    return subtype_map[subtype]

def get_se_faction(card, index):
    # NOTE: Weakness assets in SE have are represented as faction types as well.
    if index == 0:
        subtype = get_se_subtype(card)
        if subtype != 'None':
            return subtype

    faction_field = ['faction_code', 'faction2_code', 'faction3_code']
    faction_map = {
        'guardian': 'Guardian',
        'seeker': 'Seeker',
        'rogue': 'Rogue',
        'mystic': 'Mystic',
        'survivor': 'Survivor',
        'neutral': 'Neutral',
        # NOTE: This is not a real SE faction type, but ADB use 'mythos' for encounter cards so add it here to avoid errors.
        'mythos': 'Mythos',
        None: 'None'
    }
    faction = get_field(card, faction_field[index], None)
    return faction_map[faction]

def get_se_cost(card):
    cost = get_field(card, 'cost', '-')
    # NOTE: ADB uses -2 to indicate variable cost.
    if cost == -2:
        cost = 'X'
    return str(cost)

def get_se_xp(card):
    rule = get_field(card, 'real_text', '')
    # NOTE: Signature cards don't have xp indicator on cards.
    if 'deck only.' in rule:
        return 'None'
    return str(get_field(card, 'xp', 0))

def get_se_willpower(card):
    return str(get_field(card, 'skill_willpower', 0))

def get_se_intellect(card):
    return str(get_field(card, 'skill_intellect', 0))

def get_se_combat(card):
    return str(get_field(card, 'skill_combat', 0))

def get_se_agility(card):
    return str(get_field(card, 'skill_agility', 0))

def get_se_skill(card, index):
    skill_list = []
    for i in range(get_field(card, 'skill_willpower', 0)):
        skill_list.append('Willpower')
    for i in range(get_field(card, 'skill_intellect', 0)):
        skill_list.append('Intellect')
    for i in range(get_field(card, 'skill_combat', 0)):
        skill_list.append('Combat')
    for i in range(get_field(card, 'skill_agility', 0)):
        skill_list.append('Agility')
    for i in range(get_field(card, 'skill_wild', 0)):
        skill_list.append('Wild')
    while len(skill_list) < 6:
        skill_list.append('None')
    return skill_list[index]

def get_se_slot(card, index):
    slot_map = {
        'Hand': '1 Hand',
        'Hand x2': '2 Hands',
        'Arcane': '1 Arcane',
        'Arcane x2': '2 Arcane',
        'Ally': 'Ally',
        'Body': 'Body',
        'Accessory': 'Accessory',
    }
    slots = get_field(card, 'real_slot', '')
    slots = [slot_map[slot.strip()] for slot in slots.split('.') if slot.strip()]
    # NOTE: Slot order in ADB and SE are reversed.
    slots.reverse()
    while len(slots) < 2:
        slots.append('None')
    return slots[index]

def get_se_health(card):
    sanity = get_field(card, 'sanity', 'None')
    return str(get_field(card, 'health', '-' if sanity != 'None' else 'None'))

def get_se_sanity(card):
    health = get_field(card, 'health', 'None')
    return str(get_field(card, 'sanity', '-' if health != 'None' else 'None'))

def get_se_enemy_damage(card):
    return str(get_field(card, 'enemy_damage', 0))

def get_se_enemy_horror(card):
    return str(get_field(card, 'enemy_horror', 0))

def get_se_enemy_fight(card):
    return str(get_field(card, 'enemy_fight', '-'))

def get_se_enemy_evade(card):
    return str(get_field(card, 'enemy_evade', '-'))

def get_se_illustrator(card):
    return get_field(card, 'illustrator', '')

def get_se_copyright(card):
    pack = get_field(card, 'pack_code', None)
    # NOTE: This list is maintained in the product id order.
    year_map = {
        'core': '2016',
        'dwl': '2016',
        'tmm': '2016',
        'tece': '2016',
        'bota': '2016',
        'uau': '2016',
        'wda': '2016',
        'litas': '2016',
        'ptc': '2017',
        'eotp': '2017',
        'tuo': '2017',
        'apot': '2017',
        'tpm': '2017',
        'bsr': '2017',
        'dca': '2017',
        'tfa': '2017',
        'tof': '2017',
        'tbb': '2017',
        'hote': '2017',
        'tcoa': '2017',
        'tdoy': '2017',
        'sha': '2017',
        'rtnotz': '2017', 
        'rtdwl': '2018',
        'tcu': '2018',
        'tsn': '2018',
        'wos': '2018',
        'fgg': '2018',
        'uad': '2018',
        'icc': '2018',
        'bbt': '2018',
        'rtptc': '2019',
        'tde': '2019',
        'sfk': '2019',
        'tsh': '2019',
        'dsm': '2019',
        'pnr': '2019',
        'wgd': '2019',
        'woc': '2019',
        'rttfa': '2020',
        'nat': '2019',
        'har': '2019',
        'win': '2019',
        'jac': '2019',
        'ste': '2019',
        'tic': '2020',
        'itd': '2020',
        'def': '2020',
        'hhg': '2020',
        'lif': '2020',
        'lod': '2020',
        'itm': '2020',
        'rcore': '2020',
        'rttcu': '2021',
        'eoep': '2021',
    }
    return f'<cop> {year_map[pack]} FFG'

def get_se_pack(card):
    pack = get_field(card, 'pack_code', None)
    pack_map = {
        'core': 'CoreSet',
        'dwl': 'TheDunwichLegacy',
        'tmm': 'TheDunwichLegacy',
        'tece': 'TheDunwichLegacy',
        'bota': 'TheDunwichLegacy',
        'uau': 'TheDunwichLegacy',
        'wda': 'TheDunwichLegacy',
        'litas': 'TheDunwichLegacy',
        'ptc': 'ThePathToCarcosa',
        'eotp': 'ThePathToCarcosa',
        'tuo': 'ThePathToCarcosa',
        'apot': 'ThePathToCarcosa',
        'tpm': 'ThePathToCarcosa',
        'bsr': 'ThePathToCarcosa',
        'dca': 'ThePathToCarcosa',
        'tfa': 'TheForgottenAge',
        'tof': 'TheForgottenAge',
        'tbb': 'TheForgottenAge',
        'hote': 'TheForgottenAge',
        'tcoa': 'TheForgottenAge',
        'tdoy': 'TheForgottenAge',
        'sha': 'TheForgottenAge',
        'rtnotz': 'ReturnToTheNightOfTheZealot', 
        'rtdwl': 'ReturnToTheDunwichLegacy',
        'tcu': 'TheCircleUndone',
        'tsn': 'TheCircleUndone',
        'wos': 'TheCircleUndone',
        'fgg': 'TheCircleUndone',
        'uad': 'TheCircleUndone',
        'icc': 'TheCircleUndone',
        'bbt': 'TheCircleUndone',
        'rtptc': 'ReturnToThePathToCarcosa',
        'tde': 'TheDreamEaters',
        'sfk': 'TheDreamEaters',
        'tsh': 'TheDreamEaters',
        'dsm': 'TheDreamEaters',
        'pnr': 'TheDreamEaters',
        'wgd': 'TheDreamEaters',
        'woc': 'TheDreamEaters',
        'rttfa': 'ReturnToTheForgottenAge',
        'nat': 'NathanielCho',
        'har': 'HarveyWalters',
        'win': 'WinifredHabbamock',
        'jac': 'JacquelineFine',
        'ste': 'StellaClark',
        'tic': 'TheInnsmouthConspiracy',
        'itd': 'TheInnsmouthConspiracy',
        'def': 'TheInnsmouthConspiracy',
        'hhg': 'TheInnsmouthConspiracy',
        'lif': 'TheInnsmouthConspiracy',
        'lod': 'TheInnsmouthConspiracy',
        'itm': 'TheInnsmouthConspiracy',
        'rcore': 'CoreSet',
        'rttcu': 'ReturnToTheCircleUndone',
        'eoep': 'EdgeOfTheEarthInv',
    }
    return pack_map[pack]

def get_se_pack_number(card):
    return str(get_field(card, 'position', 0))

def get_se_encounter(card):
    encounter = get_field(card, 'encounter_code', None)
    encounter_map = {
        'torch': 'TheGathering',
        'arkham': 'TheMidnightMasks',
        'cultists': 'CultOfUmordhoth',
        'tentacles': 'TheDevourerBelow',
        'rats': 'Rats',
        'ghouls': 'Ghouls',
        'striking_fear': 'StrikingFear',
        'ancient_evils': 'AncientEvils',
        'chilling_cold': 'ChillingCold',
        'pentagram': 'DarkCult',
        'nightgaunts': 'Nightgaunts',
        'locked_doors': 'LockedDoors',
        'agents_of_hastur': 'AgentsOfHastur',
        'agents_of_yog': 'AgentsOfYogSothoth',
        'agents_of_shub': 'AgentsOfShubNiggurath',
        'agents_of_cthulhu': 'AgentsOfCthulhu',
        'armitages_fate': 'ArmitagesFate',
        'extracurricular_activity': 'ExtracurricularActivity',
        'the_house_always_wins': 'TheHouseAlwaysWins',
        'sorcery': 'Sorcery',
        'bishops_thralls': 'BishopsThralls',
        'dunwich': 'Dunwich',
        'whippoorwills': 'Whippoorwills',
        'bad_luck': 'BadLuck',
        'beast_thralls': 'BeastThralls',
        'naomis_crew': 'NaomisCrew',
        'the_beyond': 'TheBeyond',
        'hideous_abominations': 'HideousAbominations',
        'the_miskatonic_museum': 'TheMiskatonicMuseum',
        'essex_county_express': 'TheEssexCountyExpress',
        'blood_on_the_altar': 'BloodOnTheAltar',
        'undimensioned_and_unseen': 'UndimensionedAndUnseen',
        'where_doom_awaits': 'WhereDoomAwaits',
        'lost_in_time_and_space': 'LostInTimeAndSpace',
        None: '',
    }
    return encounter_map[encounter]

def get_se_encounter_total(card):
    encounter = get_field(card, 'encounter_code', None)
    encounter_map = {
        'torch': 16,
        'arkham': 20,
        'cultists': 5,
        'tentacles': 18,
        'rats': 3,
        'ghouls': 7,
        'striking_fear': 7,
        'ancient_evils': 3,
        'chilling_cold': 4,
        'pentagram': 6,
        'nightgaunts': 4,
        'locked_doors': 2,
        'agents_of_hastur': 4,
        'agents_of_yog': 4,
        'agents_of_shub': 4,
        'agents_of_cthulhu': 4,
        'armitages_fate': 1,
        'extracurricular_activity': 21,
        'the_house_always_wins': 23,
        'sorcery': 6,
        'bishops_thralls': 6,
        'dunwich': 4,
        'whippoorwills': 5,
        'bad_luck': 6,
        'beast_thralls': 6,
        'naomis_crew': 6,
        'the_beyond': 6,
        'hideous_abominations': 3,
        'the_miskatonic_museum': 34,
        'essex_county_express': 36,
        'blood_on_the_altar': 38,
        'undimensioned_and_unseen': 38,
        'where_doom_awaits': 32,
        'lost_in_time_and_space': 36,
        None: 0,
    }
    return str(encounter_map[encounter])

def get_se_encounter_number(card):
    return str(get_field(card, 'encounter_position', 0))

def get_se_doom(card):
    return str(get_field(card, 'doom', '-'))

def get_se_clue(card):
    return str(get_field(card, 'clues', '-'))

def get_se_shroud(card):
    return str(get_field(card, 'shroud', 0))

def get_se_per_investigator(card):
    # NOTE: Location and act cards default to use per-investigator clue count, unless clue count is 0 or 'clues_fixed' is specified.
    if get_field(card, 'type_code', None) in ['location', 'act']:
        return '0' if get_field(card, 'clues', 0) == 0 or get_field(card, 'clues_fixed', False) else '1'
    else:
        return '1' if get_field(card, 'health_per_investigator', False) else '0'

def get_se_stage_number(card):
    return str(get_field(card, 'stage', 0))

def get_se_stage_letter(card):
    # TODO: Add special cases for stage letter.
    return 'a'

def get_se_unique(card):
    # NOTE: ADB doesn't specify 'is_unique' property for investigator cards but they are always unique.
    return '1' if get_field(card, 'is_unique', False) or card['type_code'] == 'investigator' else '0'

def get_se_name(name):
    return process_lang(name)

def get_se_front_name(card):
    name = get_field(card, 'name', '')
    return get_se_name(name)

def get_se_back_name(card):
    # NOTE: ADB doesn't have back names for scenario and investigator cards but SE have them. We need to use the front names instead to avoid getting blank on the back.
    if get_field(card, 'type_code', None) in ['scenario', 'investigator']:
        name = get_field(card, 'name', '')
    else:
        name = get_field(card, 'back_name', '')
    return get_se_name(name)

def get_se_subname(card):
    subname = get_field(card, 'subname', '')
    return get_se_name(subname)

def get_se_traits(card):
    traits = get_field(card, 'traits', '')
    traits = [f'{trait.strip()}.' for trait in traits.split('.') if trait.strip()]
    traits = ' '.join(traits)
    return process_lang(traits)

def get_se_markup(rule):
    markup = [
        (r'\[action\]', '<act>'),
        (r'\[reaction\]', '<rea>'),
        (r'\[free\]', '<fre>'),
        (r'\[fast\]', '<fre>'),
        (r'\[willpower\]', '<wil>'),
        (r'\[intellect\]', '<int>'),
        (r'\[combat\]', '<com>'),
        (r'\[agility\]', '<agi>'),
        (r'\[wild\]', '<wild>'),
        (r'\[guardian\]', '<gua>'),
        (r'\[seeker\]', '<see>'),
        (r'\[rogue\]', '<rog>'),
        (r'\[mystic\]', '<mys>'),
        (r'\[survivor\]', '<sur>'),
        (r'\[skull\]', '<sku>'),
        (r'\[cultist\]', '<cul>'),
        (r'\[tablet\]', '<tab>'),
        (r'\[elder_thing\]', '<mon>'),
        (r'\[elder_sign\]', '<eld>'),
        (r'\[auto_fail\]', '<ten>'),
        (r'\[bless\]', '<ble>'),
        (r'\[curse\]', '<cur>'),
        (r'\[per_investigator\]', '<per>'),
    ]
    for a, b in markup:
        rule = re.sub(a, b, rule, flags=re.I)
    return rule

def get_se_rule(rule):
    rule = get_se_markup(rule)
    # NOTE: Format traits.
    rule = re.sub(r'\[\[([^\]]*)\]\]', r'<size 90%><t>\1</t></size><size 30%> </size>', rule)
    # NOTE: Get rid of the errata text, e.g. Wendy's Amulet.
    rule = re.sub(r'<i>\(Erratum[^<]*</i>', '', rule)
    # NOTE: Get rid of the FAQ text, e.g. Rex Murphy.
    rule = re.sub(r'<i>\(FAQ[^<]*</i>', '', rule)
    # NOTE: Format bold action keywords.
    rule = re.sub(r'<b>([^<]*)</b>', r'<hdr><size 95%>\1</size></hdr>', rule)
    # NOTE: Format bullet icon at the start of the line.
    rule = '\n'.join([re.sub(r'^\- ', '<bul> ', line.strip()) for line in rule.split('\n')])
    # NOTE: We intentionally add a space at the end to hack around a problem with SE scenario card layout. If we don't add this space,
    # the text on scenario cards doesn't automatically break lines.
    rule = f'{rule} ' if rule.strip() else ''
    return process_lang(rule)

def get_se_front_rule(card):
    rule = get_field(card, 'text', '')
    return get_se_rule(rule)

def get_se_back_rule(card):
    rule = get_field(card, 'back_text', '')
    return get_se_rule(rule)

def get_se_chaos(lines, index):
    lines = [line.strip() for line in lines.split('\n')]
    lines = lines[1:]
    token = ['[skull]', '[cultist]', '[tablet]', '[elder_thing]'][index]
    for line in lines:
        line = line.replace('：', ':').replace(':', '')
        if line.startswith(token):
            return line.replace(token, '').strip()
    return ''

def get_se_front_chaos(card, index):
    lines = get_field(card, 'text', '')
    rule = get_se_chaos(lines, index)
    return get_se_rule(rule)

def get_se_back_chaos(card, index):
    lines = get_field(card, 'back_text', '')
    rule = get_se_chaos(lines, index)
    return get_se_rule(rule)

def get_se_deck_line(card, index):
    lines = get_field(card, 'back_text', '')
    lines = [line.strip() for line in lines.split('\n') if line.strip()]
    line = lines[index] if index < len(lines) else ''
    line = [part.strip() for part in line.replace('：', ':').split(':')]
    if len(line) < 2:
        line.append('')
    elif len(line) > 2:
        line = [line[0], ':'.join(line[1:])]
    return line

def get_se_header(header):
    # NOTE: Some header text at the back of agenda/act may have markup text in it.
    header = get_se_markup(header)
    return process_lang(header)

def get_se_deck_header(card, index):
    header, _ = get_se_deck_line(card, index)
    header = f'<size 95%>{header}</size>'
    return get_se_header(header)

def get_se_deck_rule(card, index):
    _, rule = get_se_deck_line(card, index)
    return get_se_rule(rule)

def get_se_flavor(flavor):
    return process_lang(flavor)

def get_se_front_flavor(card):
    flavor = get_field(card, 'flavor', '')
    return get_se_flavor(flavor)

def get_se_back_flavor(card):
    flavor = get_field(card, 'back_flavor', '')
    return get_se_flavor(flavor)

def get_se_progress_line(card, index):
    text = get_field(card, 'back_text', '')
    flavor = get_field(card, 'back_flavor', '')
    # NOTE: For simple layout, ADB data will split out the flavor part as a separate field in 'back_flavor'.
    if flavor:
        lines = [(1, flavor.strip()), (2, text.strip())]
    else:
        # NOTE: Deleting the tags that are not useful for the parsing.
        text = text.replace('<blockquote>', '').replace('</blockquote>', '').replace('<hr>', '')

        # NOTE: Keep splitting header and flavor out of rule text until no more splitting. Encode header as 0, flavor as 1, and rule as 2.
        lines = [(2, text)]
        while True:
            splitted = False
            for i in range(len(lines)):
                type, text = lines[i]
                if type == 2:
                    re_header = r'(.*)<b>([^<]+[:：])</b>(.*)'
                    header = re.search(re_header, text, flags=re.S)
                    if header:
                        lines = lines[0:i] + [(2, header.group(1))] + [(0, header.group(2))] + [(2, header.group(3))] + lines[i+1:]
                        splitted = True
                        break
                    re_flavor = r'(.*)<i>([^<]+)</i>(.*)'
                    flavor = re.search(re_flavor, text, flags=re.S)
                    if flavor:
                        lines = lines[0:i] + [(2, flavor.group(1))] + [(1, flavor.group(2))] + [(2, flavor.group(3))] + lines[i+1:]
                        splitted = True
                        break
            if not splitted:
                break
        lines = [(type, text.strip()) for type, text in lines if text.strip()]

    # NOTE: Arrange text in the standard form (header, flavor, rule, header, flavor, rule, header, flavor, rule). Fill text at the corresponding location based on its type.
    filled_index = -1
    filled_lines = ['', '', '', '', '', '', '', '', '']
    for type, text in lines:
        for i in range(filled_index + 1, len(filled_lines)):
            if i % 3 == type:
                filled_lines[i] = text
                filled_index = i
                break

    return filled_lines[index * 3:(index + 1) * 3]

def get_se_progress_header(card, index):
    header, _, _ = get_se_progress_line(card, index)
    return get_se_header(header)

def get_se_progress_flavor(card, index):
    _, flavor, _ = get_se_progress_line(card, index)
    return get_se_flavor(flavor)

def get_se_progress_rule(card, index):
    _, _, rule = get_se_progress_line(card, index)
    return get_se_rule(rule)

def get_se_victory(card):
    victory = get_field(card, 'victory', None)
    if type(victory) != int:
        return ''
    victory = f'Victory {victory}.'
    return process_lang(victory)

def get_se_location_icon(icon):
    icon_map = {
        'Tilde': 'Slash',
        'Square': 'Square',
        'Plus': 'Cross',
        'Circle': 'Circle',
        'Triangle': 'Triangle',
        'Diamond': 'Diamond',
        'Crescent': 'Moon',
        'Tee': 'T',
        'Hourglass': 'Hourglass',
        'SlantedEquals': 'DoubleSlash',
        'Apostrophe': 'Quote',
        'Clover': 'Clover',
        'Star': 'Star',
        'Heart': 'Heart',
        'Spade': 'Spade',
    }
    # NOTE: SCED metadata on location may include special location types for game logic, they are not printed on cards.
    return icon_map.get(icon, 'None')

def get_se_front_location(metadata):
    icon = metadata.get('locationFront', {}).get('icons', '').split('|')[0]
    return get_se_location_icon(icon)

def get_se_back_location(metadata):
    icon = metadata.get('locationBack', {}).get('icons', '').split('|')[0]
    return get_se_location_icon(icon)

def get_se_connection(icons, index):
    icons = [get_se_location_icon(icon) for icon in icons.split('|')]
    while len(icons) < 6:
        icons.append('None')
    return icons[index]

def get_se_front_connection(metadata, index):
    icons = metadata.get('locationFront', {}).get('connections', '')
    return get_se_connection(icons, index)

def get_se_back_connection(metadata, index):
    icons = metadata.get('locationBack', {}).get('connections', '')
    return get_se_connection(icons, index)

def get_se_card(result_id, card, metadata, image_filename, image_scale, image_move_x, image_move_y):
    image_sheet = decode_result_id(result_id)[-1]
    # NOTE: Use the same schema for all SE card types to avoid duplicated code. Garbage data for a card type that doesn't need it is fine,
    # so long as a value can be generated with out error.
    return {
        'file': result_id,
        '$PortraitShare': '0',
        'port0Src': image_filename if image_sheet == 0 else '',
        'port0Scale': image_scale,
        'port0X': image_move_x,
        'port0Y': image_move_y,
        'port0Rot': '0',
        'port1Src': image_filename if image_sheet == 1 else '',
        'port1Scale': image_scale,
        'port1X': image_move_x,
        'port1Y': image_move_y,
        'port1Rot': '0',
        'name': get_se_front_name(card),
        '$Subtitle': get_se_subname(card),
        '$TitleBack': get_se_back_name(card),
        '$Subtype': get_se_subtype(card),
        '$Unique': get_se_unique(card),
        '$CardClass': get_se_faction(card, 0),
        '$CardClass2': get_se_faction(card, 1),
        '$CardClass3': get_se_faction(card, 2),
        '$ResourceCost': get_se_cost(card),
        '$Level': get_se_xp(card),
        '$Willpower': get_se_willpower(card),
        '$Intellect': get_se_intellect(card),
        '$Combat': get_se_combat(card),
        '$Agility': get_se_agility(card),
        '$Skill1': get_se_skill(card, 0),
        '$Skill2': get_se_skill(card, 1),
        '$Skill3': get_se_skill(card, 2),
        '$Skill4': get_se_skill(card, 3),
        '$Skill5': get_se_skill(card, 4),
        '$Skill6': get_se_skill(card, 5),
        '$Slot': get_se_slot(card, 0),
        '$Slot2': get_se_slot(card, 1),
        '$Stamina': get_se_health(card),
        '$Sanity': get_se_sanity(card),
        '$Health': get_se_health(card),
        '$Damage': get_se_enemy_damage(card),
        '$Horror': get_se_enemy_horror(card),
        '$Attack': get_se_enemy_fight(card),
        '$Evade': get_se_enemy_evade(card),
        '$Traits': get_se_traits(card),
        '$Rules': get_se_front_rule(card),
        '$Flavor': get_se_front_flavor(card),
        '$FlavorBack': get_se_back_flavor(card),
        '$InvStoryBack': get_se_back_flavor(card),
        '$Text1NameBack': get_se_deck_header(card, 0),
        '$Text1Back': get_se_deck_rule(card, 0),
        '$Text2NameBack': get_se_deck_header(card, 1),
        '$Text2Back': get_se_deck_rule(card, 1),
        '$Text3NameBack': get_se_deck_header(card, 2),
        '$Text3Back': get_se_deck_rule(card, 2),
        '$Text4NameBack': get_se_deck_header(card, 3),
        '$Text4Back': get_se_deck_rule(card, 3),
        '$Text5NameBack': get_se_deck_header(card, 4),
        '$Text5Back': get_se_deck_rule(card, 4),
        '$Text6NameBack': get_se_deck_header(card, 5),
        '$Text6Back': get_se_deck_rule(card, 5),
        '$Text7NameBack': get_se_deck_header(card, 6),
        '$Text7Back': get_se_deck_rule(card, 6),
        '$Text8NameBack': get_se_deck_header(card, 7),
        '$Text8Back': get_se_deck_rule(card, 7),
        '$Victory': get_se_victory(card),
        '$Artist': get_se_illustrator(card),
        '$ArtistBack': get_se_illustrator(card),
        '$Copyright': get_se_copyright(card),
        '$Collection': get_se_pack(card),
        '$CollectionNumber': get_se_pack_number(card),
        '$Encounter': get_se_encounter(card),
        '$EncounterNumber': get_se_encounter_number(card),
        '$EncounterTotal': get_se_encounter_total(card),
        '$Doom': get_se_doom(card),
        '$Clues': get_se_clue(card),
        '$Shroud': get_se_shroud(card),
        '$PerInvestigator': get_se_per_investigator(card),
        '$ScenarioIndex': get_se_stage_number(card),
        '$ScenarioDeckID': get_se_stage_letter(card),
        '$AgendaStory': get_se_front_flavor(card),
        '$ActStory': get_se_front_flavor(card),
        '$HeaderABack': get_se_progress_header(card, 0),
        '$AccentedStoryABack': get_se_progress_flavor(card, 0),
        '$RulesABack': get_se_progress_rule(card, 0),
        '$HeaderBBack': get_se_progress_header(card, 1),
        '$AccentedStoryBBack': get_se_progress_flavor(card, 1),
        '$RulesBBack': get_se_progress_rule(card, 1),
        '$HeaderCBack': get_se_progress_header(card, 2),
        '$AccentedStoryCBack': get_se_progress_flavor(card, 2),
        '$RulesCBack': get_se_progress_rule(card, 2),
        '$StoryBack': get_se_back_flavor(card),
        '$RulesBack': get_se_back_rule(card),
        '$LocationIconBack': get_se_front_location(metadata),
        '$Connection1IconBack': get_se_front_connection(metadata, 0),
        '$Connection2IconBack': get_se_front_connection(metadata, 1),
        '$Connection3IconBack': get_se_front_connection(metadata, 2),
        '$Connection4IconBack': get_se_front_connection(metadata, 3),
        '$Connection5IconBack': get_se_front_connection(metadata, 4),
        '$Connection6IconBack': get_se_front_connection(metadata, 5),
        '$LocationIcon': get_se_back_location(metadata),
        '$Connection1Icon': get_se_back_connection(metadata, 0),
        '$Connection2Icon': get_se_back_connection(metadata, 1),
        '$Connection3Icon': get_se_back_connection(metadata, 2),
        '$Connection4Icon': get_se_back_connection(metadata, 3),
        '$Connection5Icon': get_se_back_connection(metadata, 4),
        '$Connection6Icon': get_se_back_connection(metadata, 5),
        '$Skull': get_se_front_chaos(card, 0),
        '$Cultist': get_se_front_chaos(card, 1),
        '$Tablet': get_se_front_chaos(card, 2),
        '$ElderThing': get_se_front_chaos(card, 3),
        '$SkullBack': get_se_back_chaos(card, 0),
        '$CultistBack': get_se_back_chaos(card, 1),
        '$TabletBack': get_se_back_chaos(card, 2),
        '$ElderThingBack': get_se_back_chaos(card, 3),
    }

def ensure_dir(dir):
    os.makedirs(dir, exist_ok=True)

def recreate_dir(dir):
    shutil.rmtree(dir, ignore_errors=True)
    os.makedirs(dir)

ahdb = {}
def download_card(ahdb_id):
    ahdb_folder = f'{args.cache_dir}/ahdb'
    ensure_dir(ahdb_folder)
    lang_code, _ = get_lang_code_region()
    filename = f'{ahdb_folder}/{lang_code}.json'
    if not os.path.isfile(filename):
        print(f'Downloading ArkhamDB data...')
        res = requests.get(f'https://{lang_code}.arkhamdb.com/api/public/cards/?encounter=1').json()
        with open(filename, 'w', encoding='utf-8') as file:
            json_str = json.dumps(res, indent=2, ensure_ascii=False)
            file.write(json_str)
    if not len(ahdb):
        print(f'Processing ArkhamDB data...')
        cards = []
        with open(filename, 'r', encoding='utf-8') as file:
            cards.extend(json.loads(file.read()))
        with open(f'translations/{lang_code}/taboo.json', 'r', encoding='utf-8') as file:
            cards.extend(json.loads(file.read()))
        for card in cards:
            ahdb[card['code']] = card

    # NOTE: Patching some notable errors from ADB.
    ahdb['01513']['subtype_code'] = 'weakness'

    return ahdb[ahdb_id]

url_map = None
def load_url_map():
    global url_map
    ensure_dir(args.cache_dir)
    filename = f'{args.cache_dir}/urls.json'
    if not os.path.isfile(filename):
        with open(filename, 'w', encoding='utf-8') as file:
            json_str = json.dumps({}, indent=2, ensure_ascii=False)
            file.write(json_str)
    if url_map is None:
        with open(filename, 'r', encoding='utf-8') as file:
            url_map = json.loads(file.read())
    return url_map

def save_url_map():
    global url_map
    ensure_dir(args.cache_dir)
    filename = f'{args.cache_dir}/urls.json'
    if url_map is not None:
        with open(filename, 'w', encoding='utf-8') as file:
            json_str = json.dumps(url_map, indent=2, ensure_ascii=False)
            file.write(json_str)

def get_url_id(url):
    global url_map
    url_map = load_url_map()
    if url in url_map:
        return url_map[url]
    url_map[url] = str(uuid.uuid4()).replace('-', '')
    save_url_map()
    return url_map[url]

def add_url_id(url, url_id):
    global url_map
    url_map = load_url_map()
    url_map[url] = url_id
    save_url_map()

def encode_result_id(url_id, deck_w, deck_h, deck_x, deck_y, rotate, sheet):
    return f'{url_id}-{deck_w}-{deck_h}-{deck_x}-{deck_y}-{1 if rotate else 0}-{sheet}'

def decode_result_id(result_id):
    parts = result_id.split('-')
    return parts[0], int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]), bool(int(parts[5])), int(parts[6])

def download_deck_image(url):
    decks_folder = f'{args.cache_dir}/decks'
    ensure_dir(decks_folder)
    url_id = get_url_id(url)
    filename = f'{decks_folder}/{url_id}.jpg'
    if not os.path.isfile(filename):
        print(f'Downloading {url_id}.jpg...')
        urllib.request.urlretrieve(url, filename)
    return filename

def crop_card_image(result_id, deck_image_filename):
    cards_folder = f'{args.cache_dir}/cards'
    ensure_dir(cards_folder)
    filename = f'{cards_folder}/{result_id}.png'
    if not os.path.isfile(filename):
        print(f'Cropping {result_id}.png...')
        _, deck_w, deck_h, deck_x, deck_y, rotate, _ = decode_result_id(result_id)
        deck_image = Image.open(deck_image_filename)
        width = deck_image.width / deck_w
        height = deck_image.height / deck_h
        left = deck_x * width
        top = deck_y * height
        card_image = deck_image.crop((left, top, left + width, top + height))
        if rotate:
            card_image = card_image.transpose(method=Image.Transpose.ROTATE_90)
        card_image.save(filename)
    return filename

se_types = [
    'asset',
    'asset_encounter',
    'event',
    'skill',
    'investigator_front',
    'investigator_back',
    'treachery_weakness',
    'treachery_encounter',
    'enemy_weakness',
    'enemy_encounter',
    'agenda_front',
    'agenda_back',
    'agenda_image',
    'act_front',
    'act_back',
    'location_front',
    'location_back',
    'scenario_front',
    'scenario_back',
]
se_cards = dict(zip(se_types, [[] for _ in range(len(se_types))]))
result_set = set()

def get_decks(object):
    decks = []
    for deck_id, deck in object['CustomDeck'].items():
        decks.append((int(deck_id), deck))
    return decks

def translate_sced_card_object(object, metadata, card, _1, _2):
    deck_id, deck = get_decks(object)[0]
    deck_w = deck['NumWidth']
    deck_h = deck['NumHeight']
    deck_xy = object['CardID'] % 100
    deck_x = deck_xy % deck_w
    deck_y = deck_xy // deck_w

    def translate_sced_card(url, deck_w, deck_h, deck_x, deck_y, is_front, card):
        card_type = card['type_code']
        rotate = card_type in ['investigator', 'agenda', 'act']
        sheet = 0 if is_front else 1
        # NOTE: SCED and SE consider the front and back for location cards differently. Reverse here and encode the sheet number in the 'result_id' so that
        # front are generated for front, back for back for the location cards. Some location cards only have single face, so they need to be special cased.
        if card_type == 'location' and card['code'] not in ['02214', '02324', '02325', '02326', '02327', '02328']:
            sheet = 1 - sheet
        result_id = encode_result_id(get_url_id(url), deck_w, deck_h, deck_x, deck_y, rotate, sheet)
        if result_id in result_set:
            return
        print(f'Translating {result_id}...')

        if card_type == 'asset':
            if get_field(card, 'encounter_code', None):
                se_type = 'asset_encounter'
            else:
                se_type = 'asset'
        elif card_type == 'event':
            se_type = 'event'
        elif card_type == 'skill':
            se_type = 'skill'
        elif card_type == 'investigator':
            if is_front:
                se_type = 'investigator_front'
            else:
                se_type = 'investigator_back'
        elif card_type == 'treachery':
            if get_field(card, 'subtype_code', None) in ['basicweakness', 'weakness']:
                se_type = 'treachery_weakness'
            else:
                se_type = 'treachery_encounter'
        elif card_type == 'enemy':
            if get_field(card, 'subtype_code', None) in ['basicweakness', 'weakness']:
                se_type = 'enemy_weakness'
            else:
                se_type = 'enemy_encounter'
        elif card_type == 'agenda':
            # NOTE: Agenda with image back are special cased.
            if card['code'] in ['01145', '02314'] and not is_front:
                se_type = 'agenda_image'
            else:
                if is_front:
                    se_type = 'agenda_front'
                else:
                    se_type = 'agenda_back'
        elif card_type == 'act':
            if is_front:
                se_type = 'act_front'
            else:
                se_type = 'act_back'
        elif card_type == 'location':
            if is_front:
                se_type = 'location_front'
            else:
                se_type = 'location_back'
        elif card_type == 'scenario':
            if is_front:
                se_type = 'scenario_front'
            else:
                se_type = 'scenario_back'
        else:
            se_type = None

        deck_image_filename = download_deck_image(url)
        image_filename = crop_card_image(result_id, deck_image_filename)
        image = Image.open(image_filename)
        template_width = 375
        template_height = 525
        image_scale = template_width / (image.height if rotate else image.width)
        move_mapping = {
            'asset': (0, 93),
            'asset_encounter': (0, 93),
            'event': (0, 118),
            'skill': (0, 75),
            'investigator_front': (247, -48),
            'investigator_back': (168, 86),
            'treachery_weakness': (0, 114),
            'treachery_encounter': (0, 114),
            'enemy_weakness': (0, -125),
            'enemy_encounter': (0, -122),
            'agenda_front': (110, 0),
            'agenda_back': (0, 0),
            'agenda_image': (0, 0),
            'act_front': (-98, 0),
            'act_back': (0, 0),
            'location_front': (0, 83),
            'location_back': (0, 81),
            'scenario_front': (0, 0),
            'scenario_back': (0, 0),
        }
        image_move_x, image_move_y = move_mapping[se_type]
        image_filename = os.path.abspath(image_filename)
        se_cards[se_type].append(get_se_card(result_id, card, metadata, image_filename, image_scale, image_move_x, image_move_y))
        result_set.add(result_id)

    front_url = deck['FaceURL']
    translate_sced_card(front_url, deck_w, deck_h, deck_x, deck_y, True, card)

    back_url = deck['BackURL']
    # NOTE: Test whether it's generic player or encounter card back urls.
    if 'EcbhVuh' in back_url or 'sRsWiSG' in back_url:
        return
    # NOTE: Special cases to handle generic player or encounter card back in deck images.
    if (deck_id, deck_x, deck_y) in [(2335, 9, 5)]:
        return

    # NOTE: Some cards on ADB have separate entries for front and back. Get the correct card data through the 'linked_card' property.
    is_front = False
    if 'linked_card' in card:
        card = card['linked_card']
        is_front = True
    if deck['UniqueBack']:
        translate_sced_card(back_url, deck_w, deck_h, deck_x, deck_y, is_front, card)
    else:
        # NOTE: Even if the back is non-unique, SCED may still use it for interesting cards, e.g. Sophie: It Was All My Fault.
        translate_sced_card(back_url, 1, 1, 0, 0, is_front, card)

def download_repo(repo_folder, repo):
    if repo_folder is not None:
        return repo_folder
    ensure_dir(args.cache_dir)
    repo_name = repo.split('/')[-1]
    repo_folder = f'{args.cache_dir}/{repo_name}'
    if not os.path.isdir(repo_folder):
        print(f'Cloning {repo}...')
        subprocess.run(['git', 'clone', '--quiet', f'https://github.com/{repo}.git', repo_folder])
    return repo_folder

# TODO: Remove this check, for minicards, parallels
def is_id_translatable(ahdb_id):
    return '-' not in ahdb_id or ahdb_id.endswith('-t')

def process_player_cards(callback):
    repo_folder = download_repo(args.mod_dir, 'argonui/SCED')
    player_folder = f'{repo_folder}/objects/AllPlayerCards.15bb07'
    for filename in os.listdir(player_folder):
        if filename.endswith('.gmnotes'):
            metadata_filename = f'{player_folder}/{filename}'
            with open(metadata_filename, 'r', encoding='utf-8') as metadata_file:
                metadata = json.loads(metadata_file.read())
                ahdb_id = metadata['id']
                if is_id_translatable(ahdb_id):
                    card = download_card(ahdb_id)
                    if eval(args.filter):
                        object_filename = metadata_filename.replace('.gmnotes', '.json')
                        with open(object_filename, 'r', encoding='utf-8') as object_file:
                            object = json.loads(object_file.read())
                        callback(object, metadata, card, object_filename, object)

def process_encounter_cards(callback, **kwargs):
    include_decks = kwargs.get('include_decks', False)
    repo_folder = download_repo(args.mod_dir, 'Chr1Z93/loadable-objects')
    folders = ['campaigns', 'scenarios']
    # NOTE: These campaigns don't have data on ADB yet.
    skip_files = [
        'the_scarlet_keys.json',
        'fortune_and_folly.json',
        'machinations_through_time.json',
        'meddling_of_meowlathotep.json'
    ]
    for folder in folders:
        campaign_folder = f'{repo_folder}/{folder}'
        for filename in os.listdir(campaign_folder):
            if filename in skip_files:
                continue
            campaign_filename = f'{campaign_folder}/{filename}'
            with open(campaign_filename, 'r', encoding='utf-8') as object_file:
                def find_encounter_objects(object):
                    if type(object) == dict:
                        if include_decks and object.get('Name', None) == 'Deck':
                            results = find_encounter_objects(object['ContainedObjects'])
                            results.append(object)
                            return results
                        elif object.get('Name', None) == 'Card' and object.get('GMNotes', '').startswith('{'):
                            return [object]
                        elif 'ContainedObjects' in object:
                            return find_encounter_objects(object['ContainedObjects'])
                        else:
                            return []
                    elif type(object) == list:
                        results = []
                        for inner_object in object:
                            results.extend(find_encounter_objects(inner_object))
                        return results
                    else:
                        return []

                campaign = json.loads(object_file.read())
                for object in find_encounter_objects(campaign):
                    if object.get('Name', None) == 'Deck':
                        callback(object, None, None, campaign_filename, campaign)
                    else:
                        metadata = json.loads(object['GMNotes'])
                        ahdb_id = metadata['id']
                        if is_id_translatable(ahdb_id):
                            card = download_card(ahdb_id)
                            if eval(args.filter):
                                callback(object, metadata, card, campaign_filename, campaign)

def write_csv():
    data_dir = 'SE_Generator/data'
    recreate_dir(data_dir)
    for se_type in se_types:
        print(f'Writing {se_type}.csv...')
        filename = f'{data_dir}/{se_type}.csv'
        with open(filename, mode='w', newline='', encoding='utf-8') as file:
            components = se_cards[se_type]
            if len(components):
                fields = list(components[0].keys())
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                for component in components:
                    writer.writerow(component)

def generate_images():
    se_script = 'SE_Generator/make.js'
    print(f'Running {se_script}...')
    subprocess.run([args.se_executable, '--glang', args.lang, '--run', se_script])

def pack_images():
    deck_images = {}
    url_map = load_url_map()
    for image_dir in glob.glob('SE_Generator/images*'):
        for filename in os.listdir(image_dir):
            print(f'Packing {filename}...')
            result_id = filename.split('.')[0]
            deck_url_id, deck_w, deck_h, deck_x, deck_y, rotate, _ = decode_result_id(result_id)
            deck_url = None
            for url, url_id in url_map.items():
                if url_id == deck_url_id and 'steamusercontent.com' in url:
                    deck_url = url
            if not deck_url:
                raise Exception(f'Cannot find deck id {deck_url_id} in the url map.')
            deck_image_filename = download_deck_image(deck_url)
            if deck_url_id not in deck_images:
                deck_images[deck_url_id] = Image.open(deck_image_filename)
            deck_image = deck_images[deck_url_id]
            card_image_filename = f'{image_dir}/{filename}'
            card_image = Image.open(card_image_filename)
            if rotate:
                card_image = card_image.transpose(method=Image.Transpose.ROTATE_270)
            width = deck_image.width // deck_w
            height = deck_image.height // deck_h
            left = deck_x * width
            top = deck_y * height
            card_image = card_image.resize((width, height))
            deck_image.paste(card_image, box=(left, top))

    decks_dir = f'{args.decks_dir}/{args.lang}'
    recreate_dir(decks_dir)
    for deck_url_id, deck_image in deck_images.items():
        print(f'Writing {deck_url_id}.jpg...')
        deck_image = deck_image.convert('RGB')
        deck_image.save(f'{decks_dir}/{deck_url_id}.jpg', progressive=True, optimize=True)

def get_uploaded_folder():
    dbx = dropbox.Dropbox(args.dropbox_token)
    # NOTE: Create a folder if not already exists.
    folder = f'/SCED_Localization_Deck_Images_{args.lang}'
    try:
        dbx.files_create_folder(folder)
    except:
        pass
    return folder

def get_uploaded_image_url(image):
    dbx = dropbox.Dropbox(args.dropbox_token)
    # NOTE: Dropbox will reuse the old sharing link if there's already one exist.
    url = dbx.sharing_create_shared_link(image.path_display, short_url=True).url
    # NOTE: Get direct download link from the dropbox sharing link.
    url = url.replace('?dl=0', '').replace('www.dropbox.com', 'dl.dropboxusercontent.com')
    return url

def upload_images():
    dbx = dropbox.Dropbox(args.dropbox_token)
    folder = get_uploaded_folder()
    decks_dir = f'{args.decks_dir}/{args.lang}'
    for filename in os.listdir(decks_dir):
        print(f'Uploading {filename}...')
        with open(f'{decks_dir}/{filename}', 'rb') as file:
            deck_image_data = file.read()
            deck_filename = f'{folder}/{filename}'
            # NOTE: Setting overwrite to true so that the old deck image is replaced, and the sharing link still maintains.
            image = dbx.files_upload(deck_image_data, deck_filename, mode=dropbox.files.WriteMode.overwrite)
            url = get_uploaded_image_url(image)
            url_id = filename.split('.')[0]
            add_url_id(url, url_id)

uploaded_images = {}
def get_uploaded_images():
    if not uploaded_images:
        dbx = dropbox.Dropbox(args.dropbox_token)
        folder = get_uploaded_folder()
        for image in dbx.files_list_folder(folder).entries:
            print(f'Getting image data for {image.path_display}...')
            url_id = image.path_display.split('/')[-1].split('.')[0]
            uploaded_images[url_id] = get_uploaded_image_url(image)
    return uploaded_images

updated_files = {}
def update_sced_card_object(object, metadata, card, filename, root):
    url_id_map = get_uploaded_images()
    updated_files[filename] = root
    if card:
        name = get_se_front_name(card)
        xp = get_se_xp(card)
        if xp not in ['0', 'None']:
            name += f' ({xp})'
        # NOTE: The scenario card names are saved in the 'Description' field in SCED used for the scenario splash screen.
        if object['Nickname'] == 'Scenario':
            object['Description'] = name
        else:
            object['Nickname'] = name
            object['Description'] = re.sub(r'<[^>]*>', '', get_se_traits(card))
        print(f'Updating {name}...')

    for _, deck in get_decks(object):
        for url_key in ('FaceURL', 'BackURL'):
            if deck[url_key] in url_id_map:
                deck[url_key] = url_id_map[deck[url_key]]

def update_sced_files():
    for filename, root in updated_files.items():
        with open(filename, 'w', encoding='utf-8') as file:
            print(f'Writing {filename}...')
            json_str = json.dumps(root, indent=2, ensure_ascii=False)
            # NOTE: Reverse the lower case scientific notation 'e' to upper case, in order to be consistent with those generated by TTS.
            json_str = re.sub(r'(\d+)e-(\d\d)', r'\1E-\2', json_str)
            file.write(json_str)

if args.step in [None, steps[0]]:
    process_player_cards(translate_sced_card_object)
    process_encounter_cards(translate_sced_card_object)
    write_csv()

if args.step in [None, steps[1]]:
    generate_images()

if args.step in [None, steps[2]]:
    pack_images()

if args.step in [None, steps[3]]:
    upload_images()

if args.step in [None, steps[4]]:
    process_player_cards(update_sced_card_object)
    process_encounter_cards(update_sced_card_object, include_decks=True)
    update_sced_files()

