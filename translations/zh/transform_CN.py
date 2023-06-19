import opencc

zh_cn_converter = opencc.OpenCC('t2s.json')

def fix_char(text):
    # NOTE: Replace the middle dot for names otherwise the font doesn't recognize.
    return text.replace('‧', '·')

def fix_quote(text):
    # NOTE: Replace straight quotes with matching curly quotes.
    chars = list(text)
    left = True
    for i, char in enumerate(chars):
        if char == '"':
            chars[i] = '“' if left else '”'
            left = not left
    return ''.join(chars)

def fix_simplified(text):
    return zh_cn_converter.convert(text)

def fix_common_text(text):
    return fix_simplified(fix_quote(fix_char(text)))

def transform_name(name):
    return fix_common_text(fix_char(name))

def transform_rule(rule):
    return fix_common_text(fix_char(rule))

def transform_flavor(flavor):
    return fix_common_text(fix_char(flavor))

def transform_header(header):
    return fix_common_text(fix_char(header))

def transform_traits(traits):
    return fix_simplified('<size 50%> <size 200%>'.join(traits.split(' ')))

def transform_taboo():
    return '限卡'

def transform_vengeance(vengeance):
    return vengeance.replace('Vengeance', '复仇').replace('.', '。')

def transform_victory(victory):
    return victory.replace('Victory', '胜利').replace('.', '。')

def transform_shelter(shelter):
    return shelter.replace('Shelter', '庇护').replace('.', '。')

def transform_blob(blob):
    return blob.replace('Blob', '团块').replace('.', '。')

def transform_tracker(tracker):
    if tracker == 'Current Depth':
        return '当前深度'
    elif tracker == 'Spent Keys':
        return '花费的钥匙'
    elif tracker == 'Strength of the Abyss':
        return '深渊之力'
    return tracker

