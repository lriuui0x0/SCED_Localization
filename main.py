import argparse
import re
import csv
import json
import os
import shutil
import subprocess
import base64
import urllib.request
import imgbbpy
from enum import Enum
from PIL import Image
from hanziconv import HanziConv

se_project = 'SE_Generator'
steps = ['prepare', 'generate', 'pack', 'update']
class langs(Enum):
    spanish = 'es'
    german = 'de'
    italian = 'it'
    french = 'fr'
    korean = 'ko'
    ukrainian = 'uk'
    polish = 'pl'
    russian = 'ru'
    traditional_chinese = 'zh_TW'
    simplified_chinese = 'zh_CN'

    def __str__(self):
        return self.value

parser = argparse.ArgumentParser()
parser.add_argument('--lang', default=langs.simplified_chinese, type=langs, choices=list(langs), help='The language to translate into')
parser.add_argument('--se-executable', default=r'C:\Program Files\StrangeEons\bin\eons.exe', help='The Strange Eons executable path')
parser.add_argument('--cache-dir', default='cache', help='The directory to keep intermediate resources during processing')
parser.add_argument('--deck-images-dir', default='decks', help='The directory to keep translated deck images')
parser.add_argument('--filter', default='True', help='A Python expression filter for what cards to process')
parser.add_argument('--step', default=None, choices=steps, help='The particular automation step to run')
parser.add_argument('--repo-primary', default=None, help='The primary repository path for the SCED mod')
parser.add_argument('--repo-secondary', default=None, help='The secondary repository path for the SCED mod')
parser.add_argument('--imgbb-api-key', default=None, help='The ImgBB API key for uploading translated deck images')
args = parser.parse_args()

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
    return str(get_field(card, 'cost', '-'))

def get_se_xp(card):
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
    return str(get_field(card, 'enemy_fight', 0))

def get_se_enemy_evade(card):
    return str(get_field(card, 'enemy_evade', 0))

def get_se_illustrator(card):
    return get_field(card, 'illustrator', '')

def get_se_copyright(card):
    pack = get_field(card, 'pack_code', None)
    year_map = {
        'core': '2016',
        'rcore': '2020',
        'dwl': '2016',
        'tmm': '2016',
        'tece': '2016',
        'bota': '2016',
        'uau': '2016',
        'wda': '2016',
        'litas': '2016',
    }
    return f'<cop> {year_map[pack]} FFG'

def get_se_pack(card):
    pack = get_field(card, 'pack_code', None)
    pack_map = {
        'core': 'CoreSet',
        'rcore': 'CoreSet',
        'dwl': 'TheDunwichLegacy',
        'tmm': 'TheDunwichLegacy',
        'tece': 'TheDunwichLegacy',
        'bota': 'TheDunwichLegacy',
        'uau': 'TheDunwichLegacy',
        'wda': 'TheDunwichLegacy',
        'litas': 'TheDunwichLegacy',
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

def get_se_front_name(card):
    name = get_field(card, 'name', '')
    if args.lang == langs.simplified_chinese:
        return HanziConv.toSimplified(name)
    else:
        return name

def get_se_back_name(card):
    # NOTE: ADB doesn't have back names for scenario and investigator cards but SE have them. We need to use the front names instead to avoid getting blank on the back.
    if get_field(card, 'type_code', None) in ['scenario', 'investigator']:
        title = get_field(card, 'name', '')
    else:
        title = get_field(card, 'back_name', '')
    if args.lang == langs.simplified_chinese:
        return HanziConv.toSimplified(title)
    else:
        return title

def get_se_subname(card):
    title = get_field(card, 'subname', '')
    if args.lang == langs.simplified_chinese:
        return HanziConv.toSimplified(title)
    else:
        return title

def get_se_traits(card):
    traits = get_field(card, 'traits', '')
    traits = [f'{trait.strip()}.' for trait in traits.split('.') if trait.strip()]
    if args.lang == langs.simplified_chinese:
        return HanziConv.toSimplified('<size 50%> </size>'.join(traits))
    else:
        return ' '.join(traits)

def get_se_rule(rule):
    markup = [
        (r'\[action\]', '<act>'),
        (r'\[reaction\]', '<rea>'),
        (r'\[free\]', '<fre>'),
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
    # NOTE: Format traits.
    rule = re.sub(r'\[\[([^\]]*)\]\]', r'<size 90%><t>\1</t></size><size 30%> </size>', rule)
    # NOTE: Get rid of the erratum text, e.g. Wendy's Amulet.
    rule = re.sub(r'<i>[^<]*</i>', '', rule)
    # NOTE: Format bold action keywords.
    rule = re.sub(r'<b>([^<]*)</b>', r'<hdr><size 95%>\1</size></hdr>', rule)
    # NOTE: Increase the line height. We intentionally add a space at the end to hack around a problem with SE scenario card layout.
    # If we don't add this space, the text on scenario cards doesn't automatically break lines.
    rule = '\n'.join([f'<loose>{line.strip()}</loose> ' if line.strip() else '' for line in rule.split('\n')])
    if args.lang == langs.simplified_chinese:
        return HanziConv.toSimplified(rule)
    else:
        return rule

def get_se_front_rule(card):
    rule = get_field(card, 'text', '')
    return get_se_rule(rule)

def get_se_back_rule(card):
    rule = get_field(card, 'back_text', '')
    return get_se_rule(rule)

def get_se_chaos(paragraphs, index):
    paragraphs = [paragraph.strip() for paragraph in paragraphs.split('\n')]
    paragraphs = paragraphs[1:]
    token = ['[skull]', '[cultist]', '[tablet]', '[elder_thing]'][index]
    for paragraph in paragraphs:
        paragraph = paragraph.replace('：', ':').replace(':', '')
        if paragraph.startswith(token):
            return paragraph.replace(token, '').strip()
    return ''

def get_se_front_chaos(card, index):
    paragraphs = get_field(card, 'text', '')
    rule = get_se_chaos(paragraphs, index)
    return get_se_rule(rule)

def get_se_back_chaos(card, index):
    paragraphs = get_field(card, 'back_text', '')
    rule = get_se_chaos(paragraphs, index)
    return get_se_rule(rule)

def get_se_deck_paragraph(card, index):
    paragraphs = get_field(card, 'back_text', '')
    paragraphs = [paragraph.strip() for paragraph in paragraphs.split('\n') if paragraph.strip()]
    paragraph = paragraphs[index] if index < len(paragraphs) else ''
    paragraph = [part.strip() for part in paragraph.replace('：', ':').split(':')]
    # NOTE: Add enough paragraph parts so cards other than investigator don't generate errors.
    while len(paragraph) < 2:
        paragraph.append('')
    return paragraph

def get_se_deck_title(card, index):
    paragraph = get_se_deck_paragraph(card, index)
    title = paragraph[0]
    if args.lang == langs.simplified_chinese:
        return HanziConv.toSimplified(title)
    else:
        return title

def get_se_deck_rule(card, index):
    paragraph = get_se_deck_paragraph(card, index)
    rule = paragraph[1]
    return get_se_rule(rule)

def get_se_front_flavor(card):
    flavor = get_field(card, 'flavor', '')
    if args.lang == langs.simplified_chinese:
        return HanziConv.toSimplified(flavor)
    else:
        return flavor

def get_se_back_flavor(card):
    flavor = get_field(card, 'back_flavor', '')
    if args.lang == langs.simplified_chinese:
        return HanziConv.toSimplified(flavor)
    else:
        return flavor

def get_se_victory(card):
    victory = get_field(card, 'victory', None)
    if type(victory) != int:
        return ''
    if args.lang == langs.simplified_chinese:
        return f'胜利<size 50%> </size>{victory}。'
    else:
        return f'Victory {victory}.'

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
        '$Text1NameBack': get_se_deck_title(card, 0),
        '$Text1Back': get_se_deck_rule(card, 0),
        '$Text2NameBack': get_se_deck_title(card, 1),
        '$Text2Back': get_se_deck_rule(card, 1),
        '$Text3NameBack': get_se_deck_title(card, 2),
        '$Text3Back': get_se_deck_rule(card, 2),
        '$Text4NameBack': get_se_deck_title(card, 3),
        '$Text4Back': get_se_deck_rule(card, 3),
        '$Text5NameBack': get_se_deck_title(card, 4),
        '$Text5Back': get_se_deck_rule(card, 4),
        '$Text6NameBack': get_se_deck_title(card, 5),
        '$Text6Back': get_se_deck_rule(card, 5),
        '$Text7NameBack': get_se_deck_title(card, 6),
        '$Text7Back': get_se_deck_rule(card, 6),
        '$Text8NameBack': get_se_deck_title(card, 7),
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
        '$RulesABack': get_se_back_rule(card),
        '$AccentedStoryABack': get_se_back_flavor(card),
        '$RulesABack': get_se_back_rule(card),
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
    ensure_dir(args.cache_dir)
    filename = f'{args.cache_dir}/ahdb-{args.lang.value}.json'
    if not os.path.isfile(filename):
        print(f'Downloading ArkhamDB data...')
        api_map = {
            langs.spanish: 'https://es.arkhamdb.com/api/public/cards/?encounter=1',
            langs.german: 'https://de.arkhamdb.com/api/public/cards/?encounter=1',
            langs.italian: 'https://it.arkhamdb.com/api/public/cards/?encounter=1',
            langs.french: 'https://fr.arkhamdb.com/api/public/cards/?encounter=1',
            langs.korean: 'https://ko.arkhamdb.com/api/public/cards/?encounter=1',
            langs.ukrainian: 'https://uk.arkhamdb.com/api/public/cards/?encounter=1',
            langs.polish: 'https://pl.arkhamdb.com/api/public/cards/?encounter=1',
            langs.russian: 'https://ru.arkhamdb.com/api/public/cards/?encounter=1',
            langs.traditional_chinese: 'https://zh.arkhamdb.com/api/public/cards/?encounter=1',
            langs.simplified_chinese: 'https://zh.arkhamdb.com/api/public/cards/?encounter=1',
        }
        urllib.request.urlretrieve(api_map[args.lang], filename)

    if not len(ahdb):
        print(f'Processing ArkhamDB data...')
        with open(filename, 'r', encoding='utf-8') as file:
            cards_str = file.read()
            cards = json.loads(cards_str)
            for card in cards:
                ahdb[card['code']] = card
    return ahdb[ahdb_id]

def is_deck_url(url):
    return 'i.imgur.com' not in url

# NOTE: Use base32 to encode URL so we don't generate characters like '/' or '-' hence can be used as filenames.
def encode_url(url):
    return base64.b32encode(url.encode('ascii')).decode('ascii')

def decode_url(url_id):
    return base64.b32decode(url_id.encode('ascii')).decode('ascii')

def encode_result_id(url, deck_w, deck_h, deck_x, deck_y, rotate, sheet):
    return f'{encode_url(url)}-{deck_w}-{deck_h}-{deck_x}-{deck_y}-{1 if rotate else 0}-{sheet}'

def decode_result_id(result_id):
    parts = result_id.split('-')
    return decode_url(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]), bool(int(parts[5])), int(parts[6])

def download_deck_image(url):
    ensure_dir(args.cache_dir)
    url_id = encode_url(url)
    filename = f'{args.cache_dir}/{url_id}.jpg'
    if not os.path.isfile(filename):
        print(f'Downloading {url_id}.jpg...')
        urllib.request.urlretrieve(url, filename)
    return filename

def crop_card_image(result_id, deck_image_filename):
    ensure_dir(args.cache_dir)
    filename = f'{args.cache_dir}/{result_id}.png'
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

def get_deck(object):
    deck_id = int(list(object['CustomDeck'].keys())[0])
    deck = list(object['CustomDeck'].values())[0]
    return deck_id, deck

def translate_sced_card_object(object, metadata, card, _1, _2):
    deck_id, deck = get_deck(object)
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
        # front are generated for front, back for back.
        if card_type == 'location':
            sheet = 1 - sheet
        result_id = encode_result_id(url, deck_w, deck_h, deck_x, deck_y, rotate, sheet)
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
            if card['code'] == '01145' and not is_front:
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
    if is_deck_url(back_url):
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

# TODO: Remove this check, for minicards, parallels and taboo
def is_id_translatable(ahdb_id):
    return '-' not in ahdb_id

def process_player_cards(callback):
    repo_folder = download_repo(args.repo_primary, 'argonui/SCED')
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
    process_decks = kwargs.get('process_decks', False)
    repo_folder = download_repo(args.repo_secondary, 'Chr1Z93/loadable-objects')
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
                        if process_decks and object.get('Name', None) == 'Deck':
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
    data_dir = f'{se_project}/data'
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

def run_se():
    se_script = f'{se_project}/make.js'
    print(f'Running {se_script}...')
    subprocess.run([args.se_executable, '--glang', args.lang.value, '--run', se_script])

def pack_images():
    deck_images = {}
    image_dir = f'{se_project}/build/images'
    for filename in os.listdir(image_dir):
        print(f'Packing {filename}...')
        result_id = filename.split('.')[0]
        url, deck_w, deck_h, deck_x, deck_y, rotate, _ = decode_result_id(result_id)
        deck_image_filename = download_deck_image(url)
        deck_url_id = encode_url(url)
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

    recreate_dir(args.deck_images_dir)
    for deck_url_id, deck_image in deck_images.items():
        print(f'Writing {deck_url_id}.jpg...')
        deck_image = deck_image.convert('RGB')
        deck_image.save(f'{args.deck_images_dir}/{deck_url_id}.jpg')

deck_urls = {}
def upload_deck_images():
    if args.imgbb_api_key is None:
        raise Exception('ImageBB API key is not defined!')
    client = imgbbpy.SyncClient(args.imgbb_api_key)
    for filename in os.listdir(args.deck_images_dir):
        print(f'Uploading {filename}...')
        deck_url_id = filename.split('.')[0]
        deck_image_filename = f'{args.deck_images_dir}/{filename}'
        image = client.upload(file=deck_image_filename)
        deck_urls[deck_url_id] = image.url

def write_sced_card_object(object, metadata, card, filename, root):
    deck_id, deck = get_deck(object)
    if card:
        name = get_se_front_name(card)
        xp = get_se_xp(card)
        if xp != '0':
            name += f' ({xp})'
        # NOTE: The scenario card names are saved in the 'Description' field in SCED used for the scenario splash screen.
        if object['Nickname'] == 'Scenario':
            object['Description'] = name
        else:
            object['Nickname'] = name
        print(f'Writing {name}...')
    else:
        print(f'Writing deck {deck_id}...')

    for url_key in ('FaceURL', 'BackURL'):
        url_id = encode_url(deck[url_key])
        # NOTE: The SCED deck objects may not be translated before.
        if url_id in deck_urls:
            deck[url_key] = deck_urls[url_id]

    with open(filename, 'w', encoding='utf-8') as file:
        json_str = json.dumps(root, indent=2, ensure_ascii=False)
        # NOTE: Reverse the lower case scientific notation 'e' to upper case, in order to be consistent with those generated by TTS.
        json_str = re.sub(r'(\d+)e-(\d\d)', r'\1E-\2', json_str)
        file.write(json_str)

if args.step in [None, steps[0]]:
    process_player_cards(translate_sced_card_object)
    process_encounter_cards(translate_sced_card_object)
    write_csv()

if args.step in [None, steps[1]]:
    run_se()

if args.step in [None, steps[2]]:
    pack_images()

if args.step in [None, steps[3]]:
    upload_deck_images()
    process_player_cards(write_sced_card_object)
    process_encounter_cards(write_sced_card_object, process_decks=True)

