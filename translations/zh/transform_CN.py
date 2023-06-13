import re
from hanziconv import HanziConv

def to_simplified(text):
    # NOTE: Replace the middle dot for asset names that the font doesn't recognize.
    return HanziConv.toSimplified(text).replace('‧', '·')

def transform_taboo():
    return '限卡'

def transform_name(name):
    return to_simplified(name)

def transform_rule(rule):
    return to_simplified(rule)

def transform_flavor(flavor):
    return to_simplified(flavor)

def transform_header(header):
    return to_simplified(header)

def transform_traits(traits):
    return to_simplified('<size 50%> <size 200%>'.join(traits.split(' ')))

def transform_victory(victory):
    match = re.search(r'\d+', victory)
    return f'胜利<size 50%> <size 200%>{match.group(0)}。' if match else ''

