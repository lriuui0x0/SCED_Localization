import re

def transform_taboo():
    return 'Tabu'

def transform_victory(victory):
    match = re.search(r'\d+', victory)
    return f'Sieg {match.group(0)}.' if match else ''

