import re


def sanitize_attribute_name(name):
    '''Mesh attribute names as exported to Mitsuba, shared between the
    mesh exporter and the Color Attribute texture converter so that
    mesh_attribute references match the exported attributes.'''
    return re.sub(r'\W', '_', name)
