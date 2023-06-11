import re
from hanziconv import HanziConv

def transform_common(text):
    # NOTE: Replace the middle dot for asset names that the font doesn't recognize.
    return HanziConv.toSimplified(text).replace('‧', '·')

def transform_name(name):
    return transform_common(name)

def transform_rule(rule):
    return transform_common(rule)

def transform_flavor(flavor):
    return transform_common(flavor)

def transform_header(header):
    return transform_common(header)

def transform_traits(traits):
    return transform_common('<size 50%> </size>'.join(traits.split(' ')))

def transform_victory(victory):
    match = re.search(r'\d+', victory)
    return f'胜利<size 50%> </size>{match.group(0)}。' if match else ''

