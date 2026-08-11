import mitsuba as mi

def get_texture(props: mi.Properties,
                name: str,
                value=None) -> mi.Texture:
    '''
    Helper function to check when a node is active in `props`
    Authors: Sebastien Speierer, Baptiste Nicolet
    '''
    if not props.has_property(name):
        if value is None:
            raise Exception(f'Property {name} has not been specified!')
        if isinstance(value, (float, int)):
            return mi.load_dict({ 'type': 'uniform', 'value': value }, parallel=False)
        return mi.load_dict({'type': 'rgb', 'value': value }, parallel=False)
    texture = props.get(name)
    if isinstance(texture, (float, int)):
        return mi.load_dict({ 'type': 'uniform', 'value': texture }, parallel=False)
    if not isinstance(texture, mi.Texture):
        return mi.load_dict({ 'type': 'rgb', 'value': texture }, parallel=False)
    return texture

