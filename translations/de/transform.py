import re

def transform_taboo():
    return 'Tabu'

def transform_point(point):
    return point.replace('Vengeance', 'Vergeltung').replace('Victory', 'Sieg')

def transform_tracker(tracker):
    if tracker == 'Current Depth':
        return 'Aktuelle Tiefe'
    return tracker

