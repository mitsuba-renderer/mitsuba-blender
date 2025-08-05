from ... import logging

from ..nodes import *
from .common import *

from .add import convert_add_materials_cycles
from .principled import convert_principled_materials_cycles
from .principled_hair import convert_principled_hair_materials_cycles
from .diffuse import convert_diffuse_materials_cycles
from .glossy import convert_glossy_materials_cycles
from .glass import convert_glass_materials_cycles
from .emitter import convert_emitter_materials_cycles
from .mix import convert_mix_materials_cycles
from .transparent import convert_transparent_materials_cycles
from .translucent import convert_translucent_materials_cycles


# TODO: Add more support for other materials: refraction
CONVERTERS = {
    'BSDF_PRINCIPLED':      convert_principled_materials_cycles,
    'BSDF_HAIR_PRINCIPLED': convert_principled_hair_materials_cycles,
    'BSDF_TRANSPARENT':     convert_transparent_materials_cycles,
    'BSDF_TRANSLUCENT':     convert_translucent_materials_cycles,
    "BSDF_DIFFUSE":         convert_diffuse_materials_cycles,
    'BSDF_GLOSSY':          convert_glossy_materials_cycles,
    'BSDF_GLASS':           convert_glass_materials_cycles,
    'EMISSION':             convert_emitter_materials_cycles,
    'MIX_SHADER':           convert_mix_materials_cycles,
    'ADD_SHADER':           convert_add_materials_cycles,
}

def convert_displacement_map(ctx, b_mat):
    '''
    Extract displacement map texture from material
    '''
    output_node_id = 'Material Output'
    if output_node_id in b_mat.node_tree.nodes:
        output_node = b_mat.node_tree.nodes[output_node_id]
        if output_node.inputs["Displacement"].is_linked:
            disp_node = next_node_upstream(ctx, output_node.inputs["Displacement"])

            if disp_node.type != 'DISPLACEMENT':
                raise NotImplementedError(f"Incorrect node type for Displacement in material {b_mat.name}!")

            with ctx.scope_raw_texture_input():
                disp_params = convert_color_texture_node(ctx, disp_node.inputs['Height'])

            disp_gain = convert_float_texture_node(ctx, disp_node.inputs['Scale'])
            if not isinstance(disp_gain, float) or disp_gain != 1.0:
                disp_params = {
                    'type'  : 'mix_rgb',
                    'mode'  : 'multiply',
                    'factor': 1.0,
                    'color0': disp_params,
                    'color1': disp_gain,
                }

            return disp_params
    return None

def b_material_to_dict(ctx, b_mat):
    '''
    Converting one material from Blender / Cycles to Mitsuba
    '''
    mat_params = {}

    if b_mat.use_nodes:
        try:
            output_node_id = 'Material Output'
            if output_node_id in b_mat.node_tree.nodes:
                output_node = b_mat.node_tree.nodes[output_node_id]
                if output_node.inputs["Surface"].is_linked:
                    surface_node = next_node_upstream(ctx, output_node.inputs["Surface"])
                else:
                    raise NotImplementedError("Manual Bug! BSDF model without any input")

                extra = {}
                if b_mat.displacement_method in ['BUMP', 'BOTH']:
                    extra['displacement'] = convert_displacement_map(ctx, b_mat)

                mat_params = cycles_material_to_dict(ctx, surface_node, extra)
            else:
                logging.warn(f'Export of material {b_mat.name} failed: Cannot find material output node. Exporting a dummy material instead.')
                mat_params = get_default_material(ctx)
        except NotImplementedError as e:
            logging.warn(f'Export of material \'{b_mat.name}\' failed: {e.args[0]}. Exporting a dummy material instead.')
            mat_params = get_default_material(ctx)
    else:
        mat_params = {
            'type': 'diffuse',
            'reflectance': ctx.spectrum(b_mat.diffuse_color)
        }

    return mat_params

def export_material(ctx, material):
    mat_params = {}

    if material is None:
        return mat_params

    mat_id = ctx.sanatize_id(f'mat-{material.name}')

    # #TODO: hide emitters

    # Check if material was already exported
    if mat_id in ctx.scene_dict:
        return

    logging.debug(f'Converting material {mat_id}')

    mat_params = b_material_to_dict(ctx, material)

    if isinstance(mat_params, list): # Add/mix shader
        mats = {}
        for mat in mat_params:
            if mat['type'] == 'area': # Emitter
                mats['emitter'] = mat # Directly store the emitter, we don't reference emitters
            else: # BSDF
                mat['id'] = mats['bsdf'] = mat_id
                ctx.add_object(material.name_full, mat)
        ctx.exported_mats[mat_id] = mats
    else:
        if mat_params['type'] == 'area': # Emitter with no bsdf
            mats = {}
            # We want the emitter object to be "shadeless", so we need to add it a dummy, empty bsdf, because all objects have a bsdf by default in mitsuba
            if not 'empty-emitter-bsdf' in ctx.scene_dict: # We only need to add one of this, but we may have multiple emitter materials
                empty_bsdf = {
                    'type': 'diffuse',
                    'reflectance':ctx.spectrum(0.0), # No interaction with light
                    'id': 'empty-emitter-bsdf'
                }
                ctx.add_object(material.name_full, empty_bsdf)
            mats['bsdf'] = 'empty-emitter-bsdf'
            mats['emitter'] = mat_params
            ctx.exported_mats[mat_id] = mats

        else: # Usual case
            ctx.add_object(material.name_full, mat_params, mat_id, True)

    return mat_id

