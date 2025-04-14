from ..nodes import *
from .common import *

def convert_translucent_materials_cycles(ctx, current_node, extra):
    base_color  = convert_color_texture_node(ctx, current_node.inputs['Color'])
    
    params = { 
        'type'          : 'principledthin',
        'base_color'    : base_color,
        'roughness'     : 1.0,
        'diff_trans'    : 2.0    
    }

    return params