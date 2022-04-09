import math

if "bpy" in locals():
    import importlib
    if "bl_material_utils" in locals():
        importlib.reload(bl_shader_utils)
    if "mi_spectra_utils" in locals():
        importlib.reload(mi_spectra_utils)
    
import bpy

from . import bl_shader_utils
from . import mi_spectra_utils

######################
##      Utils       ##
######################

def _assert_mi_mat_has_property_of_type(mi_context, mi_mat, prop_name, type):
    if not mi_mat.has_property(prop_name):
        mi_context.log('ERROR', f'Material "{mi_mat.id()}" does not have property "{prop_name}".')
        assert False
    if mi_mat.type(prop_name) != type:
        mi_context.log('ERROR', f'Material property "{prop_name}" is of type "{mi_mat.type(prop_name)}". Expected {type}.')
        assert False

def _get_bsdf_with_id(mi_context, ref_id):
    mi_child_cls, mi_child_mat = mi_context.mi_scene_props.get_with_id(ref_id)
    if mi_child_cls != 'BSDF':
        mi_context.log(f'Cannot find Mitsuba BSDF "{ref_id}".', 'ERROR')
        return None
    return mi_child_mat

######################
##    Data Types    ##
######################

def mi_float_to_bl_float(mi_context, mi_mat, prop_name, default=None):
    from mitsuba import Properties
    if default is None:
        _assert_mi_mat_has_property_of_type(mi_context, mi_mat, prop_name, Properties.Type.Float)
    return float(mi_mat.get(prop_name, default))

def mi_color_to_bl_color_rgb(mi_context, mi_mat, prop_name, default=None):
    from mitsuba import Properties
    if default is None:
        _assert_mi_mat_has_property_of_type(mi_context, mi_mat, prop_name, Properties.Type.Color)
    return Color(mi_mat.get(prop_name, default))

def mi_color_to_bl_color_rgba(mi_context, mi_mat, prop_name, default=None):
    return bl_material_utils.rgb_to_rgba(mi_color_to_bl_color_rgb(mi_context, mi_mat, prop_name, default))

######################
##   BSDF writers   ##
######################

def mi_principled_to_bl_principled(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_principled = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfPrincipled', 'BSDF')
    bl_principled.inputs['Base Color'].default_value = [0.8, 0.8, 0.8, 1.0]
    bl_principled.inputs['Specular'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'specular', 0.5)
    bl_principled.inputs['Specular Tint'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'spec_tint', 0.0)
    bl_principled.inputs['Transmission'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'spec_trans', 0.0)
    bl_principled.inputs['Metallic'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'metallic', 0.0)
    bl_principled.inputs['Anisotropic'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'anisotropic', 0.0)
    bl_principled.inputs['Roughness'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'roughness', 0.4)
    bl_principled.inputs['Sheen'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'sheen', 0.0)
    bl_principled.inputs['Sheen Tint'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'sheen_tint', 0.5)
    bl_principled.inputs['Clearcoat'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'clearcoat', 0.0)
    bl_principled.inputs['Clearcoat Roughness'].default_value = mi_float_to_bl_float(mi_context, mi_mat, 'clearcoat_gloss', math.sqrt(0.03)) ** 2
    return True

def write_mi_diffuse_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_diffuse = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfDiffuse', 'BSDF')
    bl_diffuse.inputs['Color'].default_value = [0.8, 0.8, 0.8, 1.0]
    return True

def write_mi_twosided_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    mi_child_materials = []
    for _, ref_id in mi_mat.named_references():
        mi_child_mat = _get_bsdf_with_id(mi_context, ref_id)
        if mi_child_mat is None:
            return False
        mi_child_materials.append(mi_child_mat)
    mi_child_material_count = len(mi_child_materials)
    if mi_child_material_count == 1:
        # This case is handled by simply parsing the material. Blender materials are two-sided by default
        # NOTE: We always parse the Mitsuba material; we don't use the material cache.
        #       This is because we have no way of reusing already created materials as a 'sub-material'.
        write_mi_material_to_node_graph(mi_context, mi_child_materials[0], bl_mat_wrap, out_socket_id, is_within_twosided=True)
        return True
    elif mi_child_material_count == 2:
        # This case is handled by creating a two-side material where the front face has the first
        # material and the back face has the second one.
        write_twosided_material(mi_context, bl_mat_wrap, out_socket_id, mi_child_materials[0], mi_child_materials[1])
        return True
    else:
        mi_context.log(f'Mitsuba twosided material "{mi_mat.id()}" has {mi_child_material_count} child material(s). Expected 1 or 2.', 'ERROR')
        return False

######################
##   Main import    ##
######################

def write_twosided_material(mi_context, bl_mat_wrap, out_socket_id, mi_front_mat, mi_back_mat=None):
    bl_mix = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeMixShader', 'Shader')
    # Generate a geometry node that will select the correct BSDF based on face orientation
    bl_mat_wrap.ensure_node_type([out_socket_id, 'Fac'], 'ShaderNodeNewGeometry', 'Backfacing')
    # Create a new material wrapper with the mix shader as output node
    bl_child_mat_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_mix)
    # Write the child materials
    write_mi_material_to_node_graph(mi_context, mi_front_mat, bl_child_mat_wrap, 'Shader', is_within_twosided=True)
    if mi_back_mat is not None:
        write_mi_material_to_node_graph(mi_context, mi_back_mat, bl_child_mat_wrap, 'Shader_001', is_within_twosided=True)
    else:
        bl_diffuse = bl_child_mat_wrap.ensure_node_type(['Shader_001'], 'ShaderNodeBsdfDiffuse', 'BSDF')
        bl_diffuse.inputs['Color'].default_value = [0.0, 0.0, 0.0, 1.0]
    return True

def write_bl_error_material(bl_mat_wrap, out_socket_id):
    ''' Write a Blender error material that can be applied whenever
    a Mitsuba material cannot be loaded.
    '''
    bl_diffuse = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfDiffuse', 'BSDF')
    bl_diffuse.inputs['Color'].default_value = [1.0, 0.0, 0.3, 1.0]

_material_writers = {
    'principled': write_mi_principled_bsdf,
    'diffuse': write_mi_diffuse_bsdf,
    'twosided': write_mi_twosided_bsdf,
}

def write_mi_material_to_node_graph(mi_context, mi_mat, bl_mat_wrap, out_socket_id, is_within_twosided=False):
    ''' Write a Mitsuba material in a node graph starting at a specific
    node in the shader graph. This function is always guaranteed to succeed.
    If a material cannot be converted, it will result in a distinctive error material.
    '''
    mat_type = mi_mat.plugin_name()
    if mat_type not in _material_writers:
        mi_context.log(f'Mitsuba BSDF type "{mat_type}" not supported. Skipping.', 'WARN')
        write_bl_error_material(bl_mat_wrap, out_socket_id)
        return
    
    if is_within_twosided and mat_type == 'twosided':
        mi_context.log('Cannot have nested twosided materials.', 'ERROR')
        return
    
    if not is_within_twosided and mat_type != 'twosided':
        write_twosided_material(mi_context, bl_mat_wrap, out_socket_id, mi_front_mat=mi_mat, mi_back_mat=None)
    elif not _material_writers[mat_type](mi_context, mi_mat, bl_mat_wrap, out_socket_id):
        mi_context.log(f'Failed to convert Mitsuba material "{mi_mat.id()}". Skipping.', 'WARN')
        write_bl_error_material(bl_mat_wrap, out_socket_id)

def mi_material_to_bl_material(mi_context, mi_mat):
    ''' Create a Blender node tree representing a given Mitsuba material
    
    Params
    ------
    mi_context : Mitsuba import context
    mi_mat : Mitsuba material properties

    Returns
    -------
    The newly created Blender material
    '''
    bl_mat = bpy.data.materials.new(name=mi_mat.id())
    bl_mat_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat, init_empty=True)
    
    # Write the Mitsuba material to the surface output
    write_mi_material_to_node_graph(mi_context, mi_mat, bl_mat_wrap, 'Surface')

    # Format the shader node graph
    bl_mat_wrap.format_node_tree()
    
    return bl_mat
