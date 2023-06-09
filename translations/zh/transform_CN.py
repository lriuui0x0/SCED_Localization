import re
from hanziconv import HanziConv

def transform_name(name):
    return HanziConv.toSimplified(name)

def transform_rule(rule):
    return HanziConv.toSimplified(rule)

def transform_flavor(flavor):
    return HanziConv.toSimplified(flavor)

def transform_header(header):
    return HanziConv.toSimplified(header)

def transform_traits(traits):
    return HanziConv.toSimplified('<size 50%> </size>'.join(traits.split(' ')))

def transform_victory(victory):
    match = re.search(r'\d+', victory)
    return f'胜利<size 50%> </size>{match.group(0)}。' if match else ''

