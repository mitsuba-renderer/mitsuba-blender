from ... import logging
from ..nodes import *
from .common import *

def convert_transparent_materials_cycles(ctx, current_node, extra):
    params = { 'type': 'null' }

    # TODO Handle color input

    return params