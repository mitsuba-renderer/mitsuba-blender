from ... import logging
from ..nodes import *
from .common import *

def convert_emitter_materials_cycles(ctx, current_node, extra):
    if current_node.inputs["Strength"].is_linked:
        raise NotImplementedError("Only default emitter strength value is supported.") #TODO: value input
    else:
        radiance = current_node.inputs["Strength"].default_value

    if current_node.inputs['Color'].is_linked:
        raise NotImplementedError("Only default emitter color is supported.") #TODO: rgb input

    else:
        radiance = [x * radiance for x in current_node.inputs["Color"].default_value[:]]
        if np.sum(radiance) == 0:
            logging.warn("Emitter has zero emission, this will case mitsuba to fail! Ignoring it.")
            return {
                'type': 'diffuse',
                'reflectance': ctx.spectrum(0)
            }

    params = {
        'type': 'area',
        'radiance': ctx.spectrum(radiance),
    }

    return params
