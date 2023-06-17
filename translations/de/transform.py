import re

def transform_taboo():
    return 'Tabu'

def transform_vengeance(vengeance):
    return vengeance.replace('Vengeance', 'Vergeltung')

def transform_victory(victory):
    return victory.replace('Victory', 'Sieg')

def transform_shelter(shelter):
    return shelter.replace('Shelter', '')

def transform_tracker(tracker):
    if tracker == 'Current Depth':
        return 'Aktuelle Tiefe'
    elif tracker == 'Spent Keys':
        return "Ausgegebene Schlüssel"
    return tracker

