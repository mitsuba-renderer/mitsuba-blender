import drjit as dr
import mitsuba as mi

def is_active(props, name):
    '''
    Helper function to check when a lobe is active in `props`
    '''
    return props.has_property(name) and not (isinstance(props[name], (float, int)) and props[name] == 0.0)

def get_texture(props: mi.Properties,
                name: str,
                value: float = None) -> mi.Texture:
    '''
    Helper function to load a texture from a Properties object
    '''
    if not props.has_property(name):
        if value is None:
            raise Exception(f'Property {name} has not been specified!')
        if isinstance(value, float):
            texture = mi.load_dict({'type': 'uniform', 'value': value}, parallel=False)
        else:
            texture = mi.load_dict({'type': 'rgb', 'value': value}, parallel=False)
    else:
        texture = props.get(name)
        if isinstance(texture, float) or isinstance(texture, int):
            texture = mi.load_dict({'type': 'uniform', 'value': texture}, parallel=False)

    return texture