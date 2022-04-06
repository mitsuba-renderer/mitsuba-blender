import math

if "bpy" in locals():
    import importlib
    if "bl_material_utils" in locals():
        importlib.reload(bl_material_utils)
    
import bpy

from . import bl_material_utils
from mathutils import Color

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

def mi_diffuse_to_bl_diffuse(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_diffuse = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfDiffuse', 'BSDF')
    bl_diffuse.inputs['Color'].default_value = [0.8, 0.8, 0.8, 1.0]
    return True

def mi_twosided_to_bl_material(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    mi_mat_refs = mi_mat.named_references()
    mi_mat_ref_count = len(mi_mat_refs)
    if mi_mat_ref_count == 1:
        # This case is handled by simply parsing the material. Blender materials are two-sided by default
        # NOTE: We always parse the Mitsuba material; we don't use the material cache.
        #       This is because we have no way of reusing already created materials as a 'sub-material'.
        _, ref_id = mi_mat_refs[0]
        mi_child_mat = _get_bsdf_with_id(mi_context, ref_id)
        if mi_child_mat is None:
            return False
        write_mi_material_to_node_graph(mi_context, mi_child_mat, bl_mat_wrap, out_socket_id)
        return True
    elif mi_mat_ref_count == 2:
        # In this case, we need to create a mix shader based on which side of the face is visible.
        bl_mix = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeMixShader', 'Shader')
        # Generate a geometry node that will select the correct BSDF based on face orientation
        bl_mat_wrap.ensure_node_type([out_socket_id, 'Fac'], 'ShaderNodeNewGeometry', 'Backfacing')
        # Get the child materials
        _, first_ref_id = mi_mat_refs[0]
        _, second_ref_id = mi_mat_refs[1]
        mi_first_child_mat = _get_bsdf_with_id(mi_context, first_ref_id)
        mi_second_child_mat = _get_bsdf_with_id(mi_context, second_ref_id)
        if mi_first_child_mat is None or mi_second_child_mat is None:
            return False
        # Create a new material wrapper with the mix shader as output node
        bl_child_mat_wrap = bl_material_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_mix)
        # Write the child materials
        write_mi_material_to_node_graph(mi_context, mi_first_child_mat, bl_child_mat_wrap, 'Shader')
        write_mi_material_to_node_graph(mi_context, mi_first_child_mat, bl_child_mat_wrap, 'Shader_001')
        return True
    else:
        mi_context.log(f'Mitsuba twosided material "{mi_mat.id()}" has {mi_mat_ref_count} child material(s). Expected 1 or 2.', 'ERROR')
        return False

######################
##   Main import    ##
######################

def write_bl_error_material(bl_mat_wrap, out_socket_id):
    ''' Write a Blender error material that can be applied whenever
    a Mitsuba material cannot be loaded.
    '''
    bl_diffuse = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfDiffuse', 'BSDF')
    bl_diffuse.inputs['Color'].default_value = [1.0, 0.0, 0.3, 1.0]

_material_writers = {
    'principled': mi_principled_to_bl_principled,
    'diffuse': mi_diffuse_to_bl_diffuse,
    'twosided': mi_twosided_to_bl_material,
}

def write_mi_material_to_node_graph(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    ''' Write a Mitsuba material in a node graph starting at a specific
    node in the shader graph. This function is always guaranteed to succeed.
    If a material cannot be converted, it will result in a distinctive error material.
    '''
    mat_type = mi_mat.plugin_name()
    if mat_type not in _material_writers:
        mi_context.log(f'Mitsuba BSDF type "{mat_type}" not supported. Skipping.', 'WARN')
        write_bl_error_material(bl_mat_wrap, out_socket_id)
    
    if not _material_writers[mat_type](mi_context, mi_mat, bl_mat_wrap, out_socket_id):
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
    bl_mat_wrap = bl_material_utils.NodeMaterialWrapper(bl_mat, init_empty=True)
    
    # Write the Mitsuba material to the surface output
    write_mi_material_to_node_graph(mi_context, mi_mat, bl_mat_wrap, 'Surface')

    # Format the shader node graph
    bl_mat_wrap.format_node_tree()
    
    return bl_mat