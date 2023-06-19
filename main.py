# TODO:
# 06347 Legs of Atlach-Nacha, SE missing enemy template
# 85037 Subject 8L-08, SE missing enemy template
# War of the outer god, SE missing card template
# Return to scenario, missing swapping encounter set icons data
# Promo cards, Labyrinths of Lunacy no translation

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
import copy
import warnings
from PIL import Image
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
# Suppress BeautifulSoup useless warnings.
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

steps = ['translate', 'generate', 'pack', 'upload', 'update']
langs = ['es', 'de', 'it', 'fr', 'ko', 'uk', 'pl', 'ru', 'zh_TW', 'zh_CN']

parser = argparse.ArgumentParser()
parser.add_argument('--lang', default='zh_CN', choices=langs, help='The language to translate into')
parser.add_argument('--se-executable', default=r'C:\Program Files\StrangeEons\bin\eons.exe', help='The Strange Eons executable path')
parser.add_argument('--filter', default='True', help='A Python expression filter for what cards to process')
parser.add_argument('--cache-dir', default='cache', help='The directory to keep intermediate resources during processing')
parser.add_argument('--decks-dir', default='decks', help='The directory to keep translated deck images')
parser.add_argument('--ahdb-dir', default=None, help='The directory to the ArkhamDB json data repository')
parser.add_argument('--mod-dir-primary', default=None, help='The directory to the primary mod repository')
parser.add_argument('--mod-dir-secondary', default=None, help='The directory to the secondary mod repository')
parser.add_argument('--step', default=None, choices=steps, help='The particular automation step to run')
parser.add_argument('--dropbox-token', default=None, help='The dropbox token for uploading translated deck images')
args = parser.parse_args()

def get_lang_code_region():
    parts = args.lang.split('_')
    if len(parts) > 1:
        return parts[0], parts[1]
    else:
        return parts[0], ''

def import_lang_module():
    # NOTE: Import language dependent functions.
    lang_code, region = get_lang_code_region()
    lang_folder = f'translations/{lang_code}'
    if lang_folder not in sys.path:
        sys.path.insert(1, lang_folder)
    module_name = 'transform'
    if region:
        module_name += f'_{region}'
    try:
        return importlib.import_module(module_name)
    except:
        return None

def transform_lang(value):
    # NOTE: Get the corresponding process function from stack frame. Therefore it's important to call this function from the correct 'get_se_xxx' function.
    module = import_lang_module()
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

def get_se_faction(card, index, sheet):
    if index == 0:
        # NOTE: Weakness assets in SE have are represented as faction types as well.
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
l       'mythos': 'Mythos',
        None: 'None'
    }
    faction = get_field(card, faction_field[index], None)
    faction = faction_map[faction]

    # NOTE: Handle parallel cards.
    ahdb_id = card['code']
    if ahdb_id.endswith('-p') or (ahdb_id.endswith('-pf') and sheet == 0) or (ahdb_id.endswith('-pb') and sheet == 1):
        faction = f'Parallel{faction}'
    return faction

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
        'Tarot': 'Tarot',
    }
    slots = get_field(card, 'real_slot', '')
    slots = [slot_map[slot.strip()] for slot in slots.split('.') if slot.strip()]
    # NOTE: Slot order in ADB and SE are reversed.
    slots.reverse()
    while len(slots) < 2:
        slots.append('None')
    return slots[index]

def get_se_health(card):
    # NOTE: For enemy or asset with sanity, missing health means '-', otherwise it's completely empty.
    is_enemy = card['type_code'] == 'enemy'
    default_health = 'None'
    if is_enemy or get_field(card, 'sanity', None) is not None:
        default_health = '-'
    health = get_field(card, 'health', default_health)
    # NOTE: ADB uses -2 to indicate variable health. For enemy this is 'X', otherwise SE expects it to be 'Star' for '*' assets.
    if health == -2:
        health = 'X' if is_enemy else 'Star'
    return str(health)

def get_se_sanity(card):
    # NOTE: For asset with health, missing sanity means '-', otherwise it's completely empty.
    default_sanity = 'None'
    if get_field(card, 'health', None) is not None:
        default_sanity = '-'
    sanity = get_field(card, 'sanity', default_sanity)
    # NOTE: ADB uses -2 to indicate variable sanity.
    if sanity == -2:
        sanity = 'Star'
    return str(sanity)

def get_se_enemy_damage(card):
    return str(get_field(card, 'enemy_damage', 0))

def get_se_enemy_horror(card):
    return str(get_field(card, 'enemy_horror', 0))

def get_se_enemy_fight(card):
    fight = get_field(card, 'enemy_fight', '-')
    # NOTE: ADB uses -2 to indicate variable fight.
    if fight == -2:
        fight = 'X'
    return str(fight)

def get_se_enemy_evade(card):
    evade = get_field(card, 'enemy_evade', '-')
    # NOTE: ADB uses -2 to indicate variable evade.
    if evade == -2:
        evade = 'X'
    return str(evade)

def is_se_agenda_image_front(card):
    return card['code'] in ['84043', '84044', '84045', '84046', '84047', '84048', '84049', '84050', '84051', '84052', '86034', '86040', '86046']

def is_se_agenda_image_back(card):
    return card['code'] in ['01145', '02314', '05199']

def is_se_act_image_front(card):
    return card['code'] in ['08681']

def is_se_act_image_back(card):
    return card['code'] in ['03322a', '03323a', '04048', '04049', '04318', '06292', '06337']

def is_se_bottom_line_transparent(card, sheet):
    if card['type_code'] == 'enemy':
        return True
    if sheet == 0 and (is_se_agenda_image_front(card) or is_se_act_image_front(card)):
        return True
    if sheet == 1 and (is_se_agenda_image_back(card) or is_se_act_image_back(card)):
        return True
    return False

def get_se_illustrator(card, sheet):
    if is_se_bottom_line_transparent(card, sheet):
        return ''
    return get_field(card, 'illustrator', '')

def get_se_copyright(card, sheet):
    if is_se_bottom_line_transparent(card, sheet):
        return ''
    pack = card['pack_code']
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
        'tcu': '2018',
        'tsn': '2018',
        'wos': '2018',
        'fgg': '2018',
        'uad': '2018',
        'icc': '2018',
        'bbt': '2018',
        'tde': '2019',
        'sfk': '2019',
        'tsh': '2019',
        'dsm': '2019',
        'pnr': '2019',
        'wgd': '2019',
        'woc': '2019',
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
        'eoep': '2021',
        'eoec': '2021',
        'rtnotz': '2017', 
        'rtdwl': '2018',
        'rtptc': '2019',
        'rttfa': '2020',
        'rttcu': '2021',
        'cotr': '2016',
        'coh': '2016',
        'lol': '2017',
        'guardians': '2018',
        'hotel': '2019',
        'blob': '2019',
        'wog': '2020',
        'rod': '2020',
        'aon': '2020',
        'bad': '2020',
        'btb': '2021',
        'rtr': '2021',
        'hoth': '2017',
        'tdor': '2017',
        'iotv': '2017',
        'tdg': '2017',
        'tftbw': '2017',
        'bob': '2020',
        'dre': '2020',
    }
    return f'<cop> {year_map[pack]} FFG'

def get_se_pack(card, sheet):
    if is_se_bottom_line_transparent(card, sheet):
        return ''
    pack = card['pack_code']
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
        'tcu': 'TheCircleUndone',
        'tsn': 'TheCircleUndone',
        'wos': 'TheCircleUndone',
        'fgg': 'TheCircleUndone',
        'uad': 'TheCircleUndone',
        'icc': 'TheCircleUndone',
        'bbt': 'TheCircleUndone',
        'tde': 'TheDreamEaters',
        'sfk': 'TheDreamEaters',
        'tsh': 'TheDreamEaters',
        'dsm': 'TheDreamEaters',
        'pnr': 'TheDreamEaters',
        'wgd': 'TheDreamEaters',
        'woc': 'TheDreamEaters',
        'tic': 'TheInnsmouthConspiracy',
        'itd': 'TheInnsmouthConspiracy',
        'def': 'TheInnsmouthConspiracy',
        'hhg': 'TheInnsmouthConspiracy',
        'lif': 'TheInnsmouthConspiracy',
        'lod': 'TheInnsmouthConspiracy',
        'itm': 'TheInnsmouthConspiracy',
        'eoep': 'EdgeOfTheEarthInv',
        'eoec': 'EdgeOfTheEarth',
        'rtnotz': 'ReturnToTheNightOfTheZealot', 
        'rtdwl': 'ReturnToTheDunwichLegacy',
        'rtptc': 'ReturnToThePathToCarcosa',
        'rttfa': 'ReturnToTheForgottenAge',
        'rttcu': 'ReturnToTheCircleUndone',
        'cotr': 'CurseOfTheRougarou',
        'coh': 'CarnevaleOfHorrors',
        'lol': 'LabyrinthsOfLunacy',
        'guardians': 'GuardiansOfTheAbyss',
        'hotel': 'MurderAtTheExcelsiorHotel',
        'blob': 'TheBlobThatAteEverything',
        'wog': 'WarOfTheOuterGods',
        'nat': 'NathanielCho',
        'har': 'HarveyWalters',
        'win': 'WinifredHabbamock',
        'jac': 'JacquelineFine',
        'ste': 'StellaClark',
        'rod': 'ParallelInvestigators',
        'aon': 'ParallelInvestigators',
        'bad': 'ParallelInvestigators',
        'btb': 'ParallelInvestigators',
        'rtr': 'ParallelInvestigators',
        'hoth': 'Promos',
        'tdor': 'Promos',
        'iotv': 'Promos',
        'tdg': 'Promos',
        'tftbw': 'Promos',
        'bob': 'Promos',
        'dre': 'Promos',
    }
    return pack_map[pack]

def get_se_pack_number(card, sheet):
    if is_se_bottom_line_transparent(card, sheet):
        return ''
    return str(get_field(card, 'position', 0))

def get_se_encounter(card, sheet):
    encounter = get_field(card, 'encounter_code', None)
    # NOTE: Special cases for two sides of cards with different encounter sets.
    if encounter == 'vortex' and card['code'] in ['03276a', '03279b'] and sheet == 0:
        encounter = 'black_stars_rise'
    elif encounter == 'vortex' and card['code'] in ['03297', '03298'] and sheet == 1:
        encounter = 'black_stars_rise'
    elif encounter == 'flood' and card['code'] in ['03276b', '03279a'] and sheet == 0:
        encounter = 'black_stars_rise'
    elif encounter == 'flood' and card['code'] in ['03296', '03299'] and sheet == 1:
        encounter = 'black_stars_rise'
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
        'curtain_call': 'CurtainCall',
        'the_last_king': 'TheLastKing',
        'delusions': 'Delusions',
        'byakhee': 'Byakhee',
        'inhabitants_of_carcosa': 'InhabitantsOfCarcosa',
        'evil_portents': 'EvilPortents',
        'hauntings': 'Hauntings',
        'hasturs_gift': 'HastursGift',
        'cult_of_the_yellow_sign': 'CultOfTheYellowSign',
        'decay': 'DecayAndFilth',
        'stranger': 'TheStranger',
        'echoes_of_the_past': 'EchoesOfThePast',
        'the_unspeakable_oath': 'TheUnspeakableOath',
        'a_phantom_of_truth': 'APhantomOfTruth',
        'the_pallid_mask': 'ThePallidMask',
        'black_stars_rise': 'BlackStarsRise',
        'vortex': 'TheVortexAbove',
        'flood': 'TheFloodBelow',
        'dim_carcosa': 'DimCarcosa',
        'wilds': 'TheUntamedWilds',
        'eztli': 'TheDoomOfEztli',
        'rainforest': 'Rainforest',
        'serpents': 'Serpents',
        'expedition': 'Expedition',
        'agents_of_yig': 'AgentsOfYig',
        'guardians_of_time': 'GuardiansOfTime',
        'traps': 'DeadlyTraps',
        'flux': 'TemporalFlux',
        'ruins': 'ForgottenRuins',
        'pnakotic_brotherhood': 'PnakoticBrotherhood',
        'venom': 'YigsVenom',
        'poison': 'Poison',
        'threads_of_fate': 'ThreadsOfFate',
        'the_boundary_beyond': 'TheBoundaryBeyond',
        'heart_of_the_elders': 'HeartOfTheElders',
        'pillars_of_judgment': 'PillarsOfJudgment',
        'knyan': 'KnYan',
        'the_city_of_archives': 'TheCityOfArchives',
        'the_depths_of_yoth': 'TheDepthsOfYoth',
        'shattered_aeons': 'ShatteredAeons',
        'turn_back_time': 'TurnBackTime',
        'disappearance_at_the_twilight_estate': 'DisappearanceAtTheTwilightEstate',
        'the_witching_hour': 'TheWitchingHour',
        'at_deaths_doorstep': 'AtDeathsDoorstep',
        'the_watcher': 'TheWatcher',
        'agents_of_azathoth': 'AgentsOfAzathoth',
        'anettes_coven': 'AnettesCoven',
        'witchcraft': 'Witchcraft',
        'silver_twilight_lodge': 'SilverTwilightLodge',
        'city_of_sins': 'CityOfSins',
        'spectral_predators': 'SpectralPredators',
        'trapped_spirits': 'TrappedSpirits',
        'realm_of_death': 'RealmOfDeath',
        'inexorable_fate': 'InexorableFate',
        'the_secret_name': 'TheSecretName',
        'the_wages_of_sin': 'TheWagesOfSin',
        'for_the_greater_good': 'ForTheGreaterGood',
        'union_and_disillusion': 'UnionAndDisillusion',
        'in_the_clutches_of_chaos': 'InTheClutchesOfChaos',
        'music_of_the_damned': 'MusicOfTheDamned',
        'secrets_of_the_universe': 'SecretsOfTheUniverse',
        'before_the_black_throne': 'BeforeTheBlackThrone',
        'beyond_the_gates_of_sleep': 'BeyondTheGatesOfSleep',
        'waking_nightmare': 'WakingNightmare',
        'agents_of_atlach_nacha': 'AgentsOfAtlachNacha',
        'agents_of_nyarlathotep': 'AgentsOfNyarlathotep',
        'whispers_of_hypnos': 'WhispersOfHypnos',
        'creatures_of_the_underworld': 'CreaturesOfTheUnderworld',
        'dreamers_curse': 'DreamersCurse',
        'dreamlands': 'Dreamlands',
        'merging_realities': 'MergingRealities',
        'spiders': 'Spiders',
        'corsairs': 'Corsairs',
        'zoogs': 'Zoogs',
        'the_search_for_kadath': 'TheSearchForKadath',
        'a_thousand_shapes_of_horror': 'AThousandShapesOfHorror',
        'dark_side_of_the_moon': 'DarkSideOfTheMoon',
        'point_of_no_return': 'PointOfNoReturn',
        'terror_of_the_vale': 'TerrorOfTheVale',
        'descent_into_the_pitch': 'DescentIntoThePitch',
        'where_the_gods_dwell': 'WhereTheGodsDwell',
        'weaver_of_the_cosmos': 'WeaverOfTheCosmos',
        'the_pit_of_despair': 'ThePitOfDespair',
        'the_vanishing_of_elina_harper': 'TheVanishingOfElinaHarper',
        'agents_of_dagon': 'AgentsOfDagon',
        'agents_of_hydra': 'AgentsOfHydra',
        'creatures_of_the_deep': 'CreaturesOfTheDeep',
        'rising_tide': 'RisingTide',
        'fog_over_innsmouth': 'FogOverInnsmouth',
        'shattered_memories': 'ShatteredMemories',
        'malfunction': 'Malfunction',
        'syzygy': 'Syzygy',
        'flooded_caverns': 'FloodedCaverns',
        'the_locals': 'TheLocals',
        'in_too_deep': 'InTooDeep',
        'devil_reef': 'DevilReef',
        'horror_in_high_gear': 'HorrorInHighGear',
        'a_light_in_the_fog': 'ALightInTheFog',
        'the_lair_of_dagon': 'TheLairOfDagon',
        'into_the_maelstrom': 'IntoTheMaelstrom',
        'ice_and_death': 'IceAndDeath',
        'the_crash': 'TheCrash',
        'lost_in_the_night': 'LostInTheNight',
        'seeping_nightmares': 'SeepingNightmares',
        'fatal_mirage': 'FatalMirage',
        'to_the_forbidden_peaks': 'ToTheForbiddenPeaks',
        'city_of_the_elder_things': 'CityOfTheElderThings',
        'the_heart_of_madness': 'TheHeartOfMadness',
        'the_great_seal': 'TheGreatSeal',
        'stirring_in_the_deep': 'StirringInTheDeep',
        'agents_of_the_unknown': 'AgentsOfTheUnknown',
        'creatures_in_the_ice': 'CreaturesInTheIce',
        'deadly_weather': 'DeadlyWeather',
        'elder_things': 'ElderThings',
        'hazards_of_antarctica': 'HazardsOfAntarctica',
        'left_behind': 'LeftBehind',
        'nameless_horrors': 'NamelessHorrors',
        'miasma': 'Miasma',
        'penguins': 'Penguins',
        'shoggoths': 'Shoggoths',
        'silence_and_mystery': 'SilenceAndMystery',
        'expedition_team': 'ExpeditionTeam',
        'tekelili': 'TekeliLi',
        'memorials_of_the_lost': 'MemorialsOfTheLost',
        'return_to_the_gathering': 'ReturnToTheGathering',
        'return_to_the_midnight_masks': 'ReturnToTheMidnightMasks',
        'return_to_the_devourer_below': 'ReturnToTheDevourerBelow',
        'ghouls_of_umôrdhoth': 'GhoulsOfUmordhoth',
        'the_devourers_cult': 'TheDevourersCult',
        'return_cult': 'ReturnToCultOfUmordhoth',
        'return_to_extracurricular_activities': 'ReturnToExtracurricularActivities',
        'return_to_the_house_always_wins': 'ReturnToTheHouseAlwaysWins',
        'return_to_the_miskatonic_museum': 'ReturnToTheMiskatonicMuseum',
        'return_to_the_essex_county_express': 'ReturnToTheEssexCountyExpress',
        'return_to_blood_on_the_altar': 'ReturnToBloodOnTheAltar',
        'return_to_undimensioned_and_unseen': 'ReturnToUndimensionedAndUnseen',
        'return_to_where_doom_awaits': 'ReturnToWhereDoomAwaits',
        'return_to_lost_in_time_and_space': 'ReturnToLostInTimeAndSpace',
        'beyond_the_threshold': 'BeyondTheThreshold',
        'resurgent_evils': 'ResurgentEvils',
        'secret_doors': 'SecretDoors',
        'creeping_cold': 'CreepingCold',
        'erratic_fear': 'ErraticFear',
        'yog_sothoths_emissaries': 'YogSothothsEmissaries',
        'return_to_curtain_call': 'ReturnToCurtainCall',
        'return_to_the_last_king': 'ReturnToTheLastKing',
        'return_to_echoes_of_the_past': 'ReturnToEchoesOfThePast',
        'return_to_the_unspeakable_oath': 'ReturnToTheUnspeakableOath',
        'return_to_a_phantom_of_truth': 'ReturnToAPhantomOfTruth',
        'return_to_the_pallid_mask': 'ReturnToThePallidMask',
        'return_to_black_stars_rise': 'ReturnToBlackStarsRise',
        'return_to_dim_carcosa': 'ReturnToDimCarcosa',
        'delusory_evils': 'DelusoryEvils',
        'decaying_reality': 'DecayingReality',
        'hasturs_envoys': 'HastursEnvoys',
        'maddening_delusions': 'MaddeningDelusions',
        'neurotic_fear': 'NeuroticFear',
        'return_to_the_untamed_wilds': 'ReturnToTheUntamedWilds',
        'return_to_the_doom_of_eztli': 'ReturnToTheDoomOfEztli',
        'return_to_threads_of_fate': 'ReturnToThreadsOfFate',
        'return_to_the_boundary_beyond': 'ReturnToTheBoundaryBeyond',
        'return_to_pillars_of_judgment': 'ReturnToPillarsOfJudgment',
        'return_to_knyan': 'ReturnToKnYan',
        'return_to_the_city_of_archives': 'ReturnToTheCityOfArchives',
        'return_to_the_depths_of_yoth': 'ReturnToTheDepthsOfYoth',
        'return_to_shattered_aeons': 'ReturnToShatteredAeons',
        'return_to_turn_back_time': 'ReturnToTurnBackTime',
        'return_to_the_rainforest': 'ReturnToTheRainforest',
        'cult_of_pnakotus': 'CultOfPnakotus',
        'doomed_expedition': 'DoomedExpedition',
        'temporal_hunters': 'TemporalHunters',
        'venomous_hate': 'VenomousHate',
        'return_to_disappearance_at_the_twilight_estate': 'ReturnToDisappearanceAtTheTwilightEstate',
        'return_to_the_witching_hour': 'ReturnToTheWitchingHour',
        'return_to_at_deaths_doorstep': 'ReturnToAtDeathsDoorstep',
        'return_to_the_secret_name': 'ReturnToTheSecretName',
        'return_to_the_wages_of_sin': 'ReturnToTheWagesOfSin',
        'return_to_for_the_greater_good': 'ReturnToForTheGreaterGood',
        'return_to_union_and_disillusion': 'ReturnToUnionAndDisillusion',
        'return_to_in_the_clutches_of_chaos': 'ReturnToInTheClutchesOfChaos',
        'return_to_before_the_black_throne': 'ReturnToBeforeTheBlackThrone',
        'hexcraft': 'Hexcraft',
        'impending_evils': 'ImpendingEvils',
        'unspeakable_fate': 'UnspeakableFate',
        'unstable_realm': 'UnstableRealm',
        'city_of_the_damned': 'CityOfTheDamned',
        'chilling_mists': 'ChillingMists',
        'bloodthirsty_spirits': 'BloodthirstySpirits',
        'bayou': 'TheBayou',
        'rougarou': 'CurseOfTheRougarouE',
        'venice': 'CarnevaleOfHorrorsE',
        'in_the_labyrinths_of_lunacy': 'LabyrinthsOfLunacyE',
        'single_group': 'SingleGroup',
        'epic_multiplayer': 'EpicMultiplayer',
        'the_eternal_slumber': 'TheEternalSlumber',
        'the_nights_usurper': 'TheNightsUsurper',
        'brotherhood_of_the_beast': 'BrotherhoodOfTheBeast',
        'sands_of_egypt': 'SandsOfEgypt',
        'abyssal_tribute': 'AbyssalTribute',
        'abyssal_gifts': 'AbyssalGifts',
        'murder_at_the_excelsior_hotel': 'MurderAtTheExcelsiorHotelE',
        'alien_interference': 'AlienInterference',
        'excelsior_management': 'ExcelsiorManagement',
        'dark_rituals': 'DarkRituals',
        'vile_experiments': 'VileExperiments',
        'sins_of_the_past': 'SinsOfThePast',
        'blob': 'TheBlobThatAteEverythingE',
        'blob_epic_multiplayer': 'EpicMultiplayer',
        'blob_single_group': 'SingleGroup',
        'migo_incursion': 'MiGoIncursion',
        'war_of_the_outer_gods': 'WarOfTheOuterGodsE',
        'death_of_stars': 'DeathOfStars',
        'children_of_paradise': 'ChildrenOfParadise',
        'swarm_of_assimilation': 'SwarmOfAssimilation',
        None: '',
    }
    return encounter_map[encounter]

def get_se_encounter_total(card, sheet):
    if is_se_bottom_line_transparent(card, sheet):
        return ''
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
        'curtain_call': 20,
        'the_last_king': 25,
        'delusions': 6,
        'byakhee': 4,
        'inhabitants_of_carcosa': 3,
        'evil_portents': 6,
        'hauntings': 4,
        'hasturs_gift': 6,
        'cult_of_the_yellow_sign': 6,
        'decay': 6,
        'stranger': 3,
        'echoes_of_the_past': 32,
        'the_unspeakable_oath': 36,
        'a_phantom_of_truth': 38,
        'the_pallid_mask': 36,
        'black_stars_rise': 38,
        'vortex': 38,
        'flood': 38,
        'dim_carcosa': 36,
        'wilds': 11,
        'eztli': 15,
        'rainforest': 11,
        'serpents': 7,
        'expedition': 5,
        'agents_of_yig': 6,
        'guardians_of_time': 4,
        'traps': 5,
        'flux': 5,
        'ruins': 7,
        'pnakotic_brotherhood': 6,
        'venom': 5,
        'poison': 6,
        'threads_of_fate': 40,
        'the_boundary_beyond': 36,
        'heart_of_the_elders': 8,
        'pillars_of_judgment': 13,
        'knyan': 13,
        'the_city_of_archives': 44,
        'the_depths_of_yoth': 36,
        'shattered_aeons': 36,
        'turn_back_time': 4,
        'disappearance_at_the_twilight_estate': 7,
        'the_witching_hour': 15,
        'at_deaths_doorstep': 21,
        'the_watcher': 3,
        'agents_of_azathoth': 4,
        'anettes_coven': 4,
        'witchcraft': 7,
        'silver_twilight_lodge': 6,
        'city_of_sins': 5,
        'spectral_predators': 5,
        'trapped_spirits': 4,
        'realm_of_death': 4,
        'inexorable_fate': 6,
        'the_secret_name': 38,
        'the_wages_of_sin': 40,
        'for_the_greater_good': 38,
        'union_and_disillusion': 42,
        'in_the_clutches_of_chaos': 22,
        'music_of_the_damned': 8,
        'secrets_of_the_universe': 8,
        'before_the_black_throne': 36,
        'beyond_the_gates_of_sleep': 25,
        'waking_nightmare': 25,
        'agents_of_atlach_nacha': 4,
        'agents_of_nyarlathotep': 4,
        'whispers_of_hypnos': 3,
        'creatures_of_the_underworld': 4,
        'dreamers_curse': 6,
        'dreamlands': 4,
        'merging_realities': 6,
        'spiders': 6,
        'corsairs': 4,
        'zoogs': 6,
        'the_search_for_kadath': 43,
        'a_thousand_shapes_of_horror': 34,
        'dark_side_of_the_moon': 37,
        'point_of_no_return': 28,
        'terror_of_the_vale': 4,
        'descent_into_the_pitch': 4,
        'where_the_gods_dwell': 41,
        'weaver_of_the_cosmos': 38,
        'the_pit_of_despair': 18,
        'the_vanishing_of_elina_harper': 28,
        'agents_of_dagon': 4,
        'agents_of_hydra': 4,
        'creatures_of_the_deep': 6,
        'rising_tide': 6,
        'fog_over_innsmouth': 3,
        'shattered_memories': 6,
        'malfunction': 2,
        'syzygy': 4,
        'flooded_caverns': 6,
        'the_locals': 6,
        'in_too_deep': 35,
        'devil_reef': 38,
        'horror_in_high_gear': 42,
        'a_light_in_the_fog': 40,
        'the_lair_of_dagon': 36,
        'into_the_maelstrom': 42,
        'ice_and_death': 21,
        'the_crash': 5,
        'lost_in_the_night': 21,
        'seeping_nightmares': 9,
        'fatal_mirage': 53,
        'to_the_forbidden_peaks': 34,
        'city_of_the_elder_things': 47,
        'the_heart_of_madness': 18,
        'the_great_seal': 14,
        'stirring_in_the_deep': 31,
        'agents_of_the_unknown': 4,
        'creatures_in_the_ice': 7,
        'deadly_weather': 6,
        'elder_things': 6,
        'hazards_of_antarctica': 5,
        'left_behind': 6,
        'nameless_horrors': 6,
        'miasma': 4,
        'penguins': 4,
        'shoggoths': 3,
        'silence_and_mystery': 5,
        'expedition_team': 9,
        'tekelili': 16,
        'memorials_of_the_lost': 9,
        'return_to_the_gathering': 16,
        'return_to_the_midnight_masks': 8,
        'return_to_the_devourer_below': 7,
        'ghouls_of_umôrdhoth': 7,
        'the_devourers_cult': 6,
        'return_cult': 3,
        'return_to_extracurricular_activities': 4,
        'return_to_the_house_always_wins': 7,
        'return_to_the_miskatonic_museum': 7,
        'return_to_the_essex_county_express': 7,
        'return_to_blood_on_the_altar': 10,
        'return_to_undimensioned_and_unseen': 7,
        'return_to_where_doom_awaits': 6,
        'return_to_lost_in_time_and_space': 8,
        'beyond_the_threshold': 6,
        'resurgent_evils': 3,
        'secret_doors': 2,
        'creeping_cold': 4,
        'erratic_fear': 7,
        'yog_sothoths_emissaries': 4,
        'return_to_curtain_call': 7,
        'return_to_the_last_king': 9,
        'return_to_echoes_of_the_past': 7,
        'return_to_the_unspeakable_oath': 6,
        'return_to_a_phantom_of_truth': 9,
        'return_to_the_pallid_mask': 6,
        'return_to_black_stars_rise': 5,
        'return_to_dim_carcosa': 6,
        'delusory_evils': 3,
        'decaying_reality': 6,
        'hasturs_envoys': 4,
        'maddening_delusions': 6,
        'neurotic_fear': 7,
        'return_to_the_untamed_wilds': 1,
        'return_to_the_doom_of_eztli': 11,
        'return_to_threads_of_fate': 10,
        'return_to_the_boundary_beyond': 7,
        'return_to_pillars_of_judgment': 4,
        'return_to_knyan': 5,
        'return_to_the_city_of_archives': 7,
        'return_to_the_depths_of_yoth': 2,
        'return_to_shattered_aeons': 6,
        'return_to_turn_back_time': 1,
        'return_to_the_rainforest': 4,
        'cult_of_pnakotus': 6,
        'doomed_expedition': 5,
        'temporal_hunters': 5,
        'venomous_hate': 5,
        'return_to_disappearance_at_the_twilight_estate': 1,
        'return_to_the_witching_hour': 7,
        'return_to_at_deaths_doorstep': 5,
        'return_to_the_secret_name': 5,
        'return_to_the_wages_of_sin': 9,
        'return_to_for_the_greater_good': 4,
        'return_to_union_and_disillusion': 4,
        'return_to_in_the_clutches_of_chaos': 7,
        'return_to_before_the_black_throne': 9,
        'hexcraft': 7,
        'impending_evils': 3,
        'unspeakable_fate': 6,
        'unstable_realm': 4,
        'city_of_the_damned': 5,
        'chilling_mists': 4,
        'bloodthirsty_spirits': 4,
        'bayou': 39,
        'rougarou': 18,
        'venice': 55,
        'in_the_labyrinths_of_lunacy': 47,
        'single_group': 13,
        'epic_multiplayer': 20,
        'the_eternal_slumber': 18,
        'the_nights_usurper': 17,
        'brotherhood_of_the_beast': 6,
        'sands_of_egypt': 33,
        'abyssal_tribute': 2,
        'abyssal_gifts': 2,
        'murder_at_the_excelsior_hotel': 53,
        'alien_interference': 5,
        'excelsior_management': 5,
        'dark_rituals': 5,
        'vile_experiments': 5,
        'sins_of_the_past': 5,
        'blob': 54,
        'blob_epic_multiplayer': 3,
        'blob_single_group': 3,
        'migo_incursion': 18,
        'war_of_the_outer_gods': 51,
        'death_of_stars': 10,
        'children_of_paradise': 10,
        'swarm_of_assimilation': 10,
        None: 0,
    }
    return str(encounter_map[encounter])

def get_se_encounter_number(card, sheet):
    if is_se_bottom_line_transparent(card, sheet):
        return ''
    return str(get_field(card, 'encounter_position', 0))

def get_se_encounter_front_visibility(card):
    return '0' if card['code'] in ['06015a'] else '1'

def get_se_encounter_back_visibility(card):
    return '0' if card['code'] in [
        '06015a',
        '07048',
        '07049',
        '07050',
        '07051',
        '07052',
        '07102',
        '07103',
        '07104',
        '07174a',
        '07174b',
        '07247',
        '07248',
        '07249',
        '07250',
        '07251',
        '07290',
        '07319',
    ] else '1'

def get_se_doom(card):
    doom = get_field(card, 'doom', '-')
    # NOTE: ADB uses -2 to indicate variable shroud.
    if doom == -2:
        doom = 'Star'
    return str(doom)

def get_se_comment(card):
    # NOTE: Special cases the cards with an asterisk comment on the doom or clue.
    return '1' if card['code'] in ['04212'] else '0'

def get_se_clue(card):
    return str(get_field(card, 'clues', '-'))

def get_se_shroud(card):
    shroud = get_field(card, 'shroud', 0)
    # NOTE: ADB uses -2 to indicate variable shroud.
    if shroud == -2:
        shroud = 'X'
    return str(shroud)

def get_se_per_investigator(card):
    # NOTE: Location and act cards default to use per-investigator clue count, unless clue count is 0 or 'clues_fixed' is specified.
    if card['type_code'] in ['location', 'act']:
        return '0' if get_field(card, 'clues', 0) == 0 or get_field(card, 'clues_fixed', False) else '1'
    else:
        return '1' if get_field(card, 'health_per_investigator', False) else '0'

def get_se_progress_number(card):
    return str(get_field(card, 'stage', 0))

def get_se_progress_letter(card):
    # NOTE: Special case agenda and act letters.
    if card['code'] in ['53029', '53030', '53031', '53032', '53033', '53034', '53035', '53036']:
        return 'g'
    if card['code'] in ['04133a', '04134a', '04135', '04136', '04137a', '04138', '04139', '04140']:
        return 'e'
    if card['code'] in ['03278', '03279a', '03279b', '03280', '03282', '04125a', '04126a', '04127', '04128a', '04129', '04130a', '04131', '04132']:
        return 'c'
    return 'a'

def is_se_progress_reversed(card):
    return card['code'] in ['03278', '03279a', '03279b', '03280', '03281']

def get_se_progress_direction(card):
    # NOTE: Special case agenda and act direction.
    if is_se_progress_reversed(card):
        return 'Reversed'
    return 'Standard'

def get_se_unique(card):
    # NOTE: ADB doesn't specify 'is_unique' property for investigator cards but they are always unique.
    return '1' if get_field(card, 'is_unique', False) or card['type_code'] == 'investigator' else '0'

def get_se_name(name):
    return transform_lang(name)

def get_se_front_name(card):
    name = get_field(card, 'name', '')
    return get_se_name(name)

def get_se_back_name(card):
    # NOTE: ADB doesn't have back names for scenario and investigator cards but SE have them. We need to use the front names instead to avoid getting blank on the back.
    if card['type_code'] in ['scenario', 'investigator']:
        name = get_field(card, 'name', '')
    elif card['type_code'] in ['story']:
        # NOTE: Default back name as the same as front name for story cards for certain cards whose back name is missing.
        name = get_field(card, 'name', '')
        name = get_field(card, 'back_name', name)
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
    return transform_lang(traits)

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
        (r'\[frost\]', '<fro>'),
        (r'\[seal_a\]', '<seal1>'),
        (r'\[seal_b\]', '<seal2>'),
        (r'\[seal_c\]', '<seal3>'),
        (r'\[seal_d\]', '<seal4>'),
        (r'\[seal_e\]', '<seal5>'),
    ]
    for a, b in markup:
        rule = re.sub(a, b, rule, flags=re.I)
    # NOTE: Format traits. We avoid the buggy behavior of </size> in SE instead we set font size by relative percentage, 0.9 * 0.33 * 3.37 = 1.00089.
    rule = re.sub(r'\[\[([^\]]*)\]\]', r'<size 90%><t>\1</t><size 33%> <size 337%>', rule)
    return rule

def get_se_rule(rule):
    rule = get_se_markup(rule)
    # NOTE: Get rid of the errata text, e.g. Wendy's Amulet.
    rule = re.sub(r'<i>\(Erratum[^<]*</i>', '', rule)
    # NOTE: Get rid of the FAQ text, e.g. Rex Murphy.
    rule = re.sub(r'<i>\(FAQ[^<]*</i>', '', rule)
    # NOTE: Format bold action keywords.
    rule = re.sub(r'<b>([^<]*)</b>', r'<size 95%><hdr>\1</hdr><size 105%>', rule)
    # NOTE: Convert <p> tag to newline characters.
    rule = rule.replace('</p><p>', '\n').replace('<p>', '').replace('</p>', '')
    # NOTE: Format bullet icon at the start of the line.
    rule = '\n'.join([re.sub(r'^[\-—] ', '<bul> ', line.strip()) for line in rule.split('\n')])
    # NOTE: We intentionally add a space at the end to hack around a problem with SE scenario card layout. If we don't add this space,
    # the text on scenario cards doesn't automatically break lines.
    rule = f'{rule} ' if rule.strip() else ''
    return transform_lang(rule)

def get_se_front_rule(card):
    rule = get_field(card, 'text', '')
    return get_se_rule(rule)

def get_se_back_rule(card):
    rule = get_field(card, 'back_text', '')
    return get_se_rule(rule)

def get_se_chaos(rule, index):
    rule = [line.strip() for line in rule.split('\n')]
    rule = rule[1:]
    tokens = ['[skull]', '[cultist]', '[tablet]', '[elder_thing]']
    merge_tokens = ['Skull', 'Cultist', 'Tablet', 'ElderThing']
    token = tokens[index]
    for line in rule:
        if token in line:
            # NOTE: Find the greatest token this token is combined with.
            max_index = index
            for merge_token in tokens:
                if merge_token in line:
                    merge_index = tokens.index(merge_token)
                    max_index = max(max_index, merge_index)

            # NOTE: Remove tokens from the beginning of the line.
            line = re.sub(r'[:：]', '', line)
            for merge_token in tokens:
                line = line.replace(merge_token, '')
            line = line.strip()

            merge = merge_tokens[max_index] if max_index > index else 'None'
            return line, merge
    return '', 'None'

def get_se_front_chaos(card, index):
    rule = get_field(card, 'text', '')
    return get_se_chaos(rule, index)

def get_se_back_chaos(card, index):
    rule = get_field(card, 'back_text', '')
    return get_se_chaos(rule, index)

def get_se_front_chaos_rule(card, index):
    rule, _ = get_se_front_chaos(card, index)
    return get_se_rule(rule)

def get_se_front_chaos_merge(card, index):
    _, merge = get_se_front_chaos(card, index)
    return merge

def get_se_back_chaos_rule(card, index):
    rule, _ = get_se_back_chaos(card, index)
    return get_se_rule(rule)

def get_se_back_chaos_merge(card, index):
    _, merge = get_se_back_chaos(card, index)
    return merge

def get_se_tracker(card):
    tracker = ''
    if card['code'] == '04277':
        tracker = 'Current Depth'
    elif card['code'] == '07274':
        tracker = 'Spent Keys'
    elif card['code'] in ['83001', '83016']:
        tracker = 'Strength of the Abyss'
    return transform_lang(tracker)

def is_return_to_scenario(card):
    return card['pack_code'] in ['rtnotz', 'rtdwl', 'rtptc', 'rttfa', 'rttcu'] and card['type_code'] == 'scenario'

def get_se_front_template(card):
    # NOTE: Use scenario template of story card for return to scenarios. Also for some special cards.
    if is_return_to_scenario(card) or card['code'] in ['07062a']:
        return 'Chaos'
    return 'Story'

def get_se_back_template(card):
    # NOTE: Use scenario template of story card for return to scenarios.
    if is_return_to_scenario(card):
        return 'ChaosFull'
    return 'Story'

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
    return transform_lang(header)

def get_se_deck_header(card, index):
    header, _ = get_se_deck_line(card, index)
    header = f'<size 95%>{header}<size 105%>'
    return get_se_header(header)

def get_se_deck_rule(card, index):
    _, rule = get_se_deck_line(card, index)
    return get_se_rule(rule)

def get_se_flavor(flavor):
    # NOTE: Some flavor text may contain markup.
    flavor = get_se_markup(flavor)
    return transform_lang(flavor)

def get_se_front_flavor(card):
    flavor = get_field(card, 'flavor', '')
    return get_se_flavor(flavor)

def get_se_back_flavor(card):
    flavor = get_field(card, 'back_flavor', '')
    return get_se_flavor(flavor)

def get_se_back_header(card):
    # NOTE: Back header is used by scenario card with a non-standard header. We intentionally add a space at the end to work around a formatting issue in SE.
    # If we don't add the extra space, SE doesn't perform line breaking.
    header = get_field(card, 'back_text', '')
    header = [line.strip() for line in header.split('\n')][0] + ' '
    return get_se_header(header)

def get_se_paragraph_line(card, text, flavor, index):
    # NOTE: Header is determined by 'b' tag ending with colon or followed by a newline (except for resolution text).
    def is_header(elem):
        if elem.name == 'b':
            elem_text = elem.get_text().strip()
            if elem_text and elem_text[-1] in (':', '：'):
                return True
            if elem_text.startswith('(→'):
                return False
            next_elem = elem.next_sibling
            if next_elem and next_elem.get_text().startswith('\n'):
                return True
        return False

    # NOTE: Flavor is determined by 'blockquote' or 'i' tag.
    def is_flavor(elem):
        return elem.name in ['blockquote', 'i']

    # NOTE: If there's explicit flavor text, add it before the main text to handle them together. Merge it with existing flavor text if possible.
    if flavor:
        soup = BeautifulSoup(text, 'html.parser')
        if len(soup.contents):
            flavor_elem = soup.contents[0]
            if is_flavor(flavor_elem):
                flavor_elem.insert(0, f'{flavor}\n')
            else:
                flavor_elem.insert_before(f'<blockquote><i>{flavor}</i></blockquote>\n')
            text = str(soup)
        else:
            text = f'<blockquote><i>{flavor}</i></blockquote>'

    # NOTE: Normalize <hr> tag.
    text = text.replace('<hr/>', '<hr>')

    # NOTE: Swap <hr> and <b> tag in case ADB has <hr> at the beginning of the header text.
    text = re.sub(r'<b>\s*<hr>', '<hr><b>', text)

    # NOTE: Use <hr> to explicitly determine paragraphs.
    paragraphs = [paragraph.strip() for paragraph in text.split('<hr>')]

    # NOTE: Split paragraphs further before each header.
    new_paragraphs = []
    for paragraph in paragraphs:
        soup = BeautifulSoup(paragraph, 'html.parser')

        splits = [0]
        for i, elem in enumerate(soup.contents):
            if is_header(elem):
                splits.append(i)
        splits.append(None)

        for i in range(len(splits) - 1):
            new_paragraph = ''.join(str(elem) for elem in soup.contents[splits[i]:splits[i+1]]).strip()
            if new_paragraph:
                new_paragraphs.append(new_paragraph)
    paragraphs = new_paragraphs

    # NOTE: Extract out the header and flavor text from each paragraph.
    parsed_paragraphs = []
    for paragraph in paragraphs:
        soup = BeautifulSoup(paragraph, 'html.parser')

        # NOTE: Remove leading whitespace before checking for header or flavor.
        def strip_leading(node):
            for child in node.contents:
                if not str(child).strip():
                    child.extract()
                else:
                    break

        strip_leading(soup)

        # NOTE: Extract out the header text from the beginning.
        header = ''
        header_elem = soup.contents[0]
        if is_header(header_elem):
            header = str(header_elem).replace('<b>', '').replace('</b>', '').strip()
            header_elem.extract()

        strip_leading(soup)

        # NOTE: Extract out the flavor text from the beginning.
        flavor = ''
        flavor_elem = soup.contents[0]
        if is_flavor(flavor_elem):
            flavor = str(flavor_elem).replace('<blockquote>', '').replace('</blockquote>', '').replace('<i>', '').replace('</i>', '').strip()
            flavor_elem.extract()

        rule = str(soup).strip()
        parsed_paragraphs.append((header, flavor, rule))

    if index < len(parsed_paragraphs):
        return parsed_paragraphs[index]
    else:
        return '', '', ''

def get_se_front_paragraph_line(card, index):
    text = get_field(card, 'text', '')
    flavor = get_field(card, 'flavor', '')
    return get_se_paragraph_line(card, text, flavor, index)

def get_se_front_paragraph_header(card, index):
    header, _, _ = get_se_front_paragraph_line(card, index)
    return get_se_header(header)

def get_se_front_paragraph_flavor(card, index):
    _, flavor, _ = get_se_front_paragraph_line(card, index)
    return get_se_flavor(flavor)

def get_se_front_paragraph_rule(card, index):
    _, _, rule = get_se_front_paragraph_line(card, index)
    return get_se_rule(rule)

def get_se_back_paragraph_line(card, index):
    text = get_field(card, 'back_text', '')
    flavor = get_field(card, 'back_flavor', '')
    return get_se_paragraph_line(card, text, flavor, index)

def get_se_back_paragraph_header(card, index):
    header, _, _ = get_se_back_paragraph_line(card, index)
    return get_se_header(header)

def get_se_back_paragraph_flavor(card, index):
    _, flavor, _ = get_se_back_paragraph_line(card, index)
    return get_se_flavor(flavor)

def get_se_back_paragraph_rule(card, index):
    _, _, rule = get_se_back_paragraph_line(card, index)
    return get_se_rule(rule)

def get_se_vengeance(card):
    vengeance = get_field(card, 'vengeance', None)
    vengeance = f'Vengeance {vengeance}.' if type(vengeance) == int else ''
    return transform_lang(vengeance)

def get_se_victory(card):
    victory = get_field(card, 'victory', None)
    victory = f'Victory {victory}.' if type(victory) == int else ''
    return transform_lang(victory)

def get_se_shelter(card):
    shelter = get_field(card, 'shelter', None)
    shelter = f'Shelter {shelter}.' if type(shelter) == int else ''
    return transform_lang(shelter)

def get_se_blob(card):
    blob = get_field(card, 'blob', None)
    blob = f'Blob {blob}.' if type(blob) == int else ''
    return transform_lang(blob)

def get_se_point(card):
    vengeance = get_se_vengeance(card)
    victory = get_se_victory(card)
    # NOTE: Special points have different formatting on location and enemy cards.
    if card['type_code'] == 'location':
        shelter = get_se_shelter(card)
        point = '\n'.join([point for point in [vengeance, shelter, victory] if point])
    else:
        blob = get_se_blob(card)
        point = '\n'.join([point for point in [victory, vengeance, blob] if point])
    return point

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
        '$CardClass': get_se_faction(card, 0, image_sheet),
        '$CardClass2': get_se_faction(card, 1, image_sheet),
        '$CardClass3': get_se_faction(card, 2, image_sheet),
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
        '$Victory': get_se_point(card),
        '$Artist': get_se_illustrator(card, image_sheet),
        '$ArtistBack': get_se_illustrator(card, image_sheet),
        '$Copyright': get_se_copyright(card, image_sheet),
        '$Collection': get_se_pack(card, image_sheet),
        '$CollectionNumber': get_se_pack_number(card, image_sheet),
        '$Encounter': get_se_encounter(card, image_sheet),
        '$EncounterNumber': get_se_encounter_number(card, image_sheet),
        '$EncounterTotal': get_se_encounter_total(card, image_sheet),
        '$ShowEncounterIcon': get_se_encounter_front_visibility(card),
        '$ShowEncounterIconBack': get_se_encounter_back_visibility(card),
        '$Doom': get_se_doom(card),
        '$Clues': get_se_clue(card),
        '$Asterisk': get_se_comment(card),
        '$Shroud': get_se_shroud(card),
        '$PerInvestigator': get_se_per_investigator(card),
        '$ScenarioIndex': get_se_progress_number(card),
        '$ScenarioDeckID': get_se_progress_letter(card),
        '$Orientation': get_se_progress_direction(card),
        '$AgendaStory': get_se_front_flavor(card),
        '$ActStory': get_se_front_flavor(card),
        '$HeaderA': get_se_front_paragraph_header(card, 0),
        '$AccentedStoryA': get_se_front_paragraph_flavor(card, 0),
        '$RulesA': get_se_front_paragraph_rule(card, 0),
        '$HeaderB': get_se_front_paragraph_header(card, 1),
        '$AccentedStoryB': get_se_front_paragraph_flavor(card, 1),
        '$RulesB': get_se_front_paragraph_rule(card, 1),
        '$HeaderC': get_se_front_paragraph_header(card, 2),
        '$AccentedStoryC': get_se_front_paragraph_flavor(card, 2),
        '$RulesC': get_se_front_paragraph_rule(card, 2),
        '$HeaderABack': get_se_back_paragraph_header(card, 0),
        '$AccentedStoryABack': get_se_back_paragraph_flavor(card, 0),
        '$RulesABack': get_se_back_paragraph_rule(card, 0),
        '$HeaderBBack': get_se_back_paragraph_header(card, 1),
        '$AccentedStoryBBack': get_se_back_paragraph_flavor(card, 1),
        '$RulesBBack': get_se_back_paragraph_rule(card, 1),
        '$HeaderCBack': get_se_back_paragraph_header(card, 2),
        '$AccentedStoryCBack': get_se_back_paragraph_flavor(card, 2),
        '$RulesCBack': get_se_back_paragraph_rule(card, 2),
        '$HeaderBack': get_se_back_header(card),
        '$StoryBack': get_se_back_flavor(card),
        '$RulesBack': get_se_back_rule(card),
        '$LocationIcon': get_se_front_location(metadata),
        '$Connection1Icon': get_se_front_connection(metadata, 0),
        '$Connection2Icon': get_se_front_connection(metadata, 1),
        '$Connection3Icon': get_se_front_connection(metadata, 2),
        '$Connection4Icon': get_se_front_connection(metadata, 3),
        '$Connection5Icon': get_se_front_connection(metadata, 4),
        '$Connection6Icon': get_se_front_connection(metadata, 5),
        '$LocationIconBack': get_se_back_location(metadata),
        '$Connection1IconBack': get_se_back_connection(metadata, 0),
        '$Connection2IconBack': get_se_back_connection(metadata, 1),
        '$Connection3IconBack': get_se_back_connection(metadata, 2),
        '$Connection4IconBack': get_se_back_connection(metadata, 3),
        '$Connection5IconBack': get_se_back_connection(metadata, 4),
        '$Connection6IconBack': get_se_back_connection(metadata, 5),
        '$Skull': get_se_front_chaos_rule(card, 0),
        '$MergeSkull': get_se_front_chaos_merge(card, 0),
        '$Cultist': get_se_front_chaos_rule(card, 1),
        '$MergeCultist': get_se_front_chaos_merge(card, 1),
        '$Tablet': get_se_front_chaos_rule(card, 2),
        '$MergeTablet': get_se_front_chaos_merge(card, 2),
        '$ElderThing': get_se_front_chaos_rule(card, 3),
        '$SkullBack': get_se_back_chaos_rule(card, 0),
        '$MergeSkullBack': get_se_back_chaos_merge(card, 0),
        '$CultistBack': get_se_back_chaos_rule(card, 1),
        '$MergeCultistBack': get_se_back_chaos_merge(card, 1),
        '$TabletBack': get_se_back_chaos_rule(card, 2),
        '$MergeTabletBack': get_se_back_chaos_merge(card, 2),
        '$ElderThingBack': get_se_back_chaos_rule(card, 3),
        '$TrackerBox': get_se_tracker(card),
        '$Template': get_se_front_template(card),
        '$TemplateBack': get_se_back_template(card),
    }

def ensure_dir(dir):
    os.makedirs(dir, exist_ok=True)

def recreate_dir(dir):
    shutil.rmtree(dir, ignore_errors=True)
    os.makedirs(dir)

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

ahdb = {}
def download_card(ahdb_id):
    ahdb_folder = f'{args.cache_dir}/ahdb'
    ensure_dir(ahdb_folder)
    lang_code, _ = get_lang_code_region()
    filename = f'{ahdb_folder}/{lang_code}.json'

    if not os.path.isfile(filename):
        print(f'Downloading ArkhamDB data...')

        def load_folder(folder):
            all_cards = {}
            for data_filename in glob.glob(f'{folder}/**/*.json'):
                with open(data_filename, 'r', encoding='utf-8') as file:
                    cards = json.loads(file.read())
                    for card in cards:
                        if 'code' in card:
                            all_cards[card['code']] = card
            return all_cards

        repo_folder = download_repo(args.ahdb_dir, 'Kamalisk/arkhamdb-json-data')
        english = load_folder(f'{repo_folder}/pack')
        translation = load_folder(f'{repo_folder}/translations/{lang_code}/pack')

        # NOTE: Patch translation data while maintain the original properties as 'real_*' to match the API result.
        for id, english_card in english.items():
            if id in translation:
                translation_card = translation[id]
                for key, value in translation_card.items():
                    if key in english_card and key != 'code':
                        english_card[f'real_{key}'] = english_card[key]
                    english_card[key] = value
        translation = english

        # NOTE: Patch 'back_link' property to match the API result.
        for id, card in translation.items():
            if get_field(card, 'back_link', None):
                card['linked_card'] = copy.deepcopy(translation[card['back_link']])

        # NOTE: Patch 'duplicate_of' property to match the API result.
        for id, card in translation.items():
            if get_field(card, 'duplicate_of', None):
                new_card = copy.deepcopy(translation[card['duplicate_of']])
                for key, value in card.items():
                    new_card[key] = value
                translation[id] = new_card

        # NOTE: Patch linked cards missing encounter set.
        for id, card in translation.items():
            if 'linked_card' in card:
                if get_field(card, 'encounter_code', None) != None and get_field(card['linked_card'], 'encounter_code', None) == None:
                    card['linked_card']['encounter_code'] = card['encounter_code']
                    card['linked_card']['encounter_position'] = card['encounter_position']
                elif get_field(card, 'encounter_code', None) == None and get_field(card['linked_card'], 'encounter_code', None) != None:
                    card['encounter_code'] = card['linked_card']['encounter_code']
                    card['encounter_position'] = card['linked_card']['encounter_position']
        
        with open(filename, 'w', encoding='utf-8') as file:
            json_str = json.dumps(list(translation.values()), indent=2, ensure_ascii=False)
            file.write(json_str)

    if not len(ahdb):
        print(f'Processing ArkhamDB data...')

        cards = []
        with open(filename, 'r', encoding='utf-8') as file:
            cards.extend(json.loads(file.read()))
        # NOTE: Add taboo cards with -t suffix.
        with open(f'translations/{lang_code}/taboo.json', 'r', encoding='utf-8') as file:
            cards.extend(json.loads(file.read()))
        for card in cards:
            ahdb[card['code']] = card
        # NOTE: Add parallel cards with all front back combinations.
        for id in ['90001', '90008', '90017', '90024', '90037']:
            card = ahdb[id]
            old_id = card['alternate_of']
            old_card = ahdb[old_id]

            pid = f'{old_id}-p'
            pp_card = copy.deepcopy(card)
            pp_card['code'] = pid
            ahdb[pid] = pp_card

            pfid = f'{old_id}-pf'
            pf_card = copy.deepcopy(card)
            pf_card['code'] = pfid
            pf_card['back_text'] = get_field(old_card, 'back_text', '')
            pf_card['back_flavor'] = get_field(old_card, 'back_flavor', '')
            ahdb[pfid] = pf_card

            pbid = f'{old_id}-pb'
            pb_card = copy.deepcopy(card)
            pb_card['code'] = pbid
            pb_card['text'] = get_field(old_card, 'text', '')
            pb_card['flavor'] = get_field(old_card, 'flavor', '')
            ahdb[pbid] = pb_card

        # NOTE: Patching special point attributes as separate fields.
        points = {
            'shelter': ['08502', '08503', '08504', '08505', '08506', '08507', '08508', '08509', '08510', '08511', '08512', '08513', '08514'],
            'blob': ['85039', '85040', '85041', '85042'],
        }
        for point_key, ids in points.items():
            for id in ids:
                card = ahdb[id]
                re_point = r'\s*<b>.*?(\d+)</b>[.。]\s*$'
                match = re.search(re_point, card['text'])
                point = int(match.group(1))
                card[point_key] = point
                card['text'] = re.sub(re_point, '', card['text'])

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

    url_id_map = {}
    for url_id, url_set in url_map.items():
        for url in url_set.values():
            url_id_map[url] = url_id

    return url_map, url_id_map

def save_url_map():
    ensure_dir(args.cache_dir)
    filename = f'{args.cache_dir}/urls.json'
    if url_map is not None:
        with open(filename, 'w', encoding='utf-8') as file:
            json_str = json.dumps(url_map, indent=2, ensure_ascii=False)
            file.write(json_str)

def get_url_id(url):
    url_map, url_id_map = load_url_map()
    if url in url_id_map:
        return url_id_map[url]
    url_id = str(uuid.uuid4()).replace('-', '')
    # NOTE: The first time we try to get an url which doesn't exist usually means it's the first time we try to download the deck image, so it's the English version.
    url_map[url_id] = {'en': url}
    save_url_map()
    return url_id

def add_url_id(url_id, url):
    url_map, _ = load_url_map()
    url_map[url_id][args.lang] = url
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
    'investigator_encounter_front',
    'investigator_encounter_back',
    'treachery_weakness',
    'treachery_encounter',
    'enemy_weakness',
    'enemy_encounter',
    'agenda_front',
    'agenda_back',
    'act_front',
    'act_back',
    'image_front',
    'image_back',
    'location_front',
    'location_back',
    'scenario_front',
    'scenario_back',
    'scenario_header',
    'story',
]
se_cards = dict(zip(se_types, [[] for _ in range(len(se_types))]))
result_set = set()

def get_decks(object):
    decks = []
    for deck_id, deck in object['CustomDeck'].items():
        decks.append((int(deck_id), deck))
    return decks

def translate_sced_card(url, deck_w, deck_h, deck_x, deck_y, is_front, card, metadata):
    card_type = card['type_code']
    rotate = card_type in ['investigator', 'agenda', 'act']
    sheet = 0 if is_front else 1
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
        if get_field(card, 'encounter_code', None) is not None:
            if is_front:
                se_type = 'investigator_encounter_front'
            else:
                se_type = 'investigator_encounter_back'
        else:
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
        # NOTE: Agenda with image are special cased.
        if is_front and is_se_agenda_image_front(card):
            se_type = 'image_front'
        elif not is_front and is_se_agenda_image_back(card):
            se_type = 'image_back'
        else:
            if is_front:
                se_type = 'agenda_front'
            else:
                se_type = 'agenda_back'
    elif card_type == 'act':
        # NOTE: Act with image are special cased.
        if is_front and is_se_act_image_front(card):
            se_type = 'image_front'
        elif not is_front and is_se_act_image_back(card):
            se_type = 'image_back'
        else:
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
        # NOTE: Return to scenario cards are using story with scenario template.
        if is_return_to_scenario(card):
            se_type = 'story'
        else:
            if is_front:
                se_type = 'scenario_front'
            else:
                se_type = 'scenario_back'
    elif card_type == 'story':
        # NOTE: Some scenario cards are recorded as story in ADB, handle them specially here.
        if card['code'] == '06078' and not is_front:
            se_type = 'scenario_header'
        else:
            se_type = 'story'
    else:
        se_type = None

    deck_image_filename = download_deck_image(url)
    image_filename = crop_card_image(result_id, deck_image_filename)
    image = Image.open(image_filename)
    template_width = 375
    template_height = 525
    image_scale = template_width / (image.height if rotate else image.width)
    move_map = {
        'asset': (0, 93),
        'asset_encounter': (0, 93),
        'event': (0, 118),
        'skill': (0, 75),
        'investigator_front': (247, -48),
        'investigator_back': (168, 86),
        'investigator_encounter_front': (247, -48),
        'investigator_encounter_back': (168, 86),
        'treachery_weakness': (0, 114),
        'treachery_encounter': (0, 114),
        'enemy_weakness': (0, -122),
        'enemy_encounter': (0, -122),
        'agenda_front': (110, 0),
        'agenda_back': (0, 0),
        'act_front': (-98, 0),
        'act_back': (0, 0),
        'image_front': (0, 0),
        'image_back': (0, 0),
        'location_front': (0, 83),
        'location_back': (0, 83),
        'scenario_front': (0, 0),
        'scenario_back': (0, 0),
        'scenario_header': (0, 0),
        'story': (0, 0),
    }
    # NOTE: Handle the case where agenda and act direction reversed on cards.
    if se_type in ['agenda_front', 'act_front'] and is_se_progress_reversed(card):
        if se_type == 'agenda_front':
            move_map_se_type = 'act_front'
        else:
            move_map_se_type = 'agenda_front'
    else:
        move_map_se_type = se_type
    image_move_x, image_move_y = move_map[move_map_se_type]
    image_filename = os.path.abspath(image_filename)
    se_cards[se_type].append(get_se_card(result_id, card, metadata, image_filename, image_scale, image_move_x, image_move_y))
    result_set.add(result_id)

def translate_sced_card_object(object, metadata, card):
    deck_id, deck = get_decks(object)[0]
    deck_w = deck['NumWidth']
    deck_h = deck['NumHeight']
    deck_xy = object['CardID'] % 100
    deck_x = deck_xy % deck_w
    deck_y = deck_xy // deck_w

    front_card = card
    back_card = card
    # NOTE: The first front means the front side in SCED using front url, the second front means whether it's the logical front side for the card type.
    front_is_front = True
    back_is_front = False
    # NOTE: Some cards on ADB have separate entries for front and back, where the front one is the main card data. Always ensure the card id in SCED is the front one,
    # and get the correct back card data through the 'linked_card' property.
    if 'linked_card' in card:
        back_card = card['linked_card']
        back_is_front = True
        # NOTE: In certain cases the face order in SCED is opposite to that on ArkhamDB.
        if card['code'] in [
                '03182b',
                '03221b',
                '03325b',
                '03326b',
                '03326d',
                '03327b',
                '03327d',
                '03327f',
                '03328b',
                '03328d',
                '03328f',
                '03329b',
                '03329d',
                '03330b',
                '03331b',
                '05085b',
                '05166',
                '05167',
                '05168',
                '05169',
                '05170',
                '05171',
                '05172',
                '05173',
                '05174',
                '05175',
                '05176',
                '05217',
                '05262',
                '05263',
                '05264',
                '05265',
                '07252',
                '51026b',
                '82017',
                '82018',
                '82019',
                '82020',
                '83022b',
                '83023b',
                '83024b',
                '83025b',
                '83026b',
        ]:
            front_card, back_card = back_card, front_card
    else:
        # NOTE: SCED thinks the front side of location is the unrevealed side, which is different from what SE expects. Reverse it here apart from single faced locations.
        # The same goes for some special cards.
        if (card['type_code'] == 'location' and get_field(card, 'double_sided', False)) or card['code'] in ['06078', '06346']:
            front_is_front = False
            back_is_front = True

    front_url = deck['FaceURL']
    translate_front = True
    # NOTE: Do not translate front image for full portrait.
    if card['code'] in ['06346']:
        translate_front = False

    if translate_front:
        translate_sced_card(front_url, deck_w, deck_h, deck_x, deck_y, front_is_front, front_card, metadata)

    back_url = deck['BackURL']
    translate_back = True
    # NOTE: Test whether it's generic player or encounter card back urls.
    if 'EcbhVuh' in back_url or 'sRsWiSG' in back_url:
        translate_back = False
    # NOTE: Special cases to skip generic player or encounter card back in deck images.
    if (deck_id, deck_x, deck_y) in [
            (2335, 9, 5),
            (2661, 2, 1),
            (2661, 3, 1),
            (2661, 4, 1),
            (2661, 2, 2),
            (2661, 3, 2),
            (2661, 4, 2),
            (2661, 5, 2),
            (2661, 6, 2),
            (2661, 7, 2),
            (2661, 8, 2),
            (2661, 9, 2),
            (2661, 0, 3),
            (2661, 1, 3),
            (2661, 2, 3),
            (2661, 3, 3),
            (2661, 4, 3),
            (2661, 5, 3),
            (2661, 6, 3),
            (2661, 7, 3),
            (2661, 8, 3),
            (2661, 9, 3),
            (2661, 0, 4),
            (2661, 1, 4),
            (4547, 0, 4),
            (4547, 1, 4),
            (2662, 1, 1),
            (2662, 2, 1),
            (2662, 3, 1),
            (2662, 4, 1),
            (2662, 5, 1),
            (2662, 6, 1),
            (2662, 7, 1),
            (5469, 6, 1),
            (5469, 7, 1)
    ]:
        translate_back = False

    if translate_back:
        # NOTE: If back side has a separate entry, then it's treated as if it's the front side of the card.
        if deck['UniqueBack']:
            translate_sced_card(back_url, deck_w, deck_h, deck_x, deck_y, back_is_front, back_card, metadata)
        else:
            # NOTE: Even if the back is non-unique, SCED may still use it for interesting cards, e.g. Sophie: It Was All My Fault.
            translate_sced_card(back_url, 1, 1, 0, 0, back_is_front, back_card, metadata)

def translate_sced_token_object(object, metadata, card):
    image_url = object['CustomImage']['ImageURL']
    is_front = object['Description'].endswith('Easy/Standard')
    translate_sced_card(image_url, 1, 1, 0, 0, is_front, card, metadata)

def translate_sced_object(object, metadata, card, _1, _2):
    if object['Name'] in ['Card', 'CardCustom']:
        translate_sced_card_object(object, metadata, card)
    elif object['Name'] == 'Custom_Token':
        translate_sced_token_object(object, metadata, card)

def is_translatable(ahdb_id):
    # NOTE: Skip minicards.
    return '-m' not in ahdb_id

def process_player_cards(callback):
    repo_folder = download_repo(args.mod_dir_primary, 'argonui/SCED')
    player_folder = f'{repo_folder}/objects/AllPlayerCards.15bb07'
    for filename in os.listdir(player_folder):
        if filename.endswith('.gmnotes'):
            metadata_filename = f'{player_folder}/{filename}'
            with open(metadata_filename, 'r', encoding='utf-8') as metadata_file:
                metadata = json.loads(metadata_file.read())
                ahdb_id = metadata['id']
                if is_translatable(ahdb_id):
                    card = download_card(ahdb_id)
                    if eval(args.filter):
                        object_filename = metadata_filename.replace('.gmnotes', '.json')
                        with open(object_filename, 'r', encoding='utf-8') as object_file:
                            object = json.loads(object_file.read())
                        callback(object, metadata, card, object_filename, object)

def process_encounter_cards(callback, **kwargs):
    include_decks = kwargs.get('include_decks', False)
    repo_folder = download_repo(args.mod_dir_secondary, 'Chr1Z93/loadable-objects')
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
                        elif object.get('Name', None) in ['Card', 'CardCustom'] and object.get('GMNotes', '').startswith('{'):
                            return [object]
                        # NOTE: Some scenario cards have tracker box on them and are custom token object instead.
                        elif object.get('Name', None) == 'Custom_Token' and object.get('Nickname', None) == 'Scenario' and object.get('GMNotes', '').startswith('{'):
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
                        if is_translatable(ahdb_id):
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
    url_map, _ = load_url_map()
    for image_dir in glob.glob('SE_Generator/images*'):
        for filename in os.listdir(image_dir):
            print(f'Packing {filename}...')
            result_id = filename.split('.')[0]
            deck_url_id, deck_w, deck_h, deck_x, deck_y, rotate, _ = decode_result_id(result_id)
            # NOTE: We use the English version of the url as the base image to pack, which we assume to exist.
            deck_url = url_map[deck_url_id]['en']
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
            add_url_id(url_id, url)

uploaded_images = {}
def load_uploaded_images():
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
    _, old_url_id_map = load_url_map()
    new_url_id_map = load_uploaded_images()
    updated_files[filename] = root
    if card:
        name = get_se_front_name(card)
        xp = get_se_xp(card)
        if xp not in ['0', 'None']:
            name += f' ({xp})'
        if card['code'].endswith('-t'):
            module = import_lang_module()
            taboo_func = getattr(module, 'transform_taboo', None)
            name += f' ({taboo_func() if taboo_func else "Taboo"})'
        # NOTE: The scenario card names are saved in the 'Description' field in SCED used for the scenario splash screen.
        if object['Nickname'] == 'Scenario':
            object['Description'] = name
        else:
            object['Nickname'] = name
            # NOTE: Remove any markup formatting in the tooltip traits text.
            object['Description'] = re.sub(r'<[^>]*>', '', get_se_traits(card))
        print(f'Updating {name}...')

    for _, deck in get_decks(object):
        for url_key in ('FaceURL', 'BackURL'):
            # NOTE: Only update if we have seen this URL and assigned an id to it before.
            if deck[url_key] in old_url_id_map:
                deck_url_id = old_url_id_map[deck[url_key]]
                # NOTE: Only update if we have uploaded the deck image and has a sharing URL before.
                if deck_url_id in new_url_id_map:
                    deck[url_key] = new_url_id_map[deck_url_id]

def update_sced_files():
    for filename, root in updated_files.items():
        with open(filename, 'w', encoding='utf-8') as file:
            print(f'Writing {filename}...')
            json_str = json.dumps(root, indent=2, ensure_ascii=False)
            # NOTE: Reverse the lower case scientific notation 'e' to upper case, in order to be consistent with those generated by TTS.
            json_str = re.sub(r'(\d+)e-(\d\d)', r'\1E-\2', json_str)
            file.write(json_str)

if args.step in [None, steps[0]]:
    process_player_cards(translate_sced_object)
    process_encounter_cards(translate_sced_object)
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

