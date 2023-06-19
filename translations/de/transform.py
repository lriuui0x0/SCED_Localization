def transform_taboo():
    return 'Tabu'

def transform_vengeance(vengeance):
    return vengeance.replace('Vengeance', 'Vergeltung')

def transform_victory(victory):
    return victory.replace('Victory', 'Sieg')

def transform_shelter(shelter):
    return shelter.replace('Shelter', 'Schutz')

def transform_blob(blob):
    return blob.replace('Blob', 'Blob')

def transform_tracker(tracker):
    if tracker == 'Current Depth':
        return 'Aktuelle Tiefe'
    elif tracker == 'Spent Keys':
        return 'Ausgegebene Schlüssel'
    elif tracker == 'Strength of the Abyss':
        return 'Stärke des Abgrundes'
    return tracker

