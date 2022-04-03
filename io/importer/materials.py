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
##       BSDF       ##
######################

def mi_principled_to_bl_principled(mi_context, mi_mat, bl_mat, bl_mat_wrap):
    bl_principled = bl_mat_wrap.ensure_node_type(['Surface'], 'ShaderNodeBsdfPrincipled', 'BSDF')
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

def mi_diffuse_to_bl_diffuse(mi_context, mi_mat, bl_mat, bl_mat_wrap):
    bl_diffuse = bl_mat_wrap.ensure_node_type(['Surface'], 'ShaderNodeBsdfDiffuse', 'BSDF')
    bl_diffuse.inputs['Color'].default_value = [0.8, 0.8, 0.8, 1.0]

######################
##   Main import    ##
######################

_material_converters = {
    'principled': mi_principled_to_bl_principled,
    'diffuse': mi_diffuse_to_bl_diffuse,
}

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
    # Ensure that we have a converter for that material type
    mat_type = mi_mat.plugin_name()
    if mat_type not in _material_converters:
        mi_context.log(f'Mitsuba BSDF type "{mat_type}" not supported. Skipping.', 'WARN')
        return None
    
    # Create the Blender material and the shader node wrapper
    bl_mat = bpy.data.materials.new(name=mi_mat.id())
    bl_mat_wrap = bl_material_utils.NodeMaterialWrapper(bl_mat)
    
    # Call the material converter
    _material_converters[mat_type](mi_context, mi_mat, bl_mat, bl_mat_wrap)

    # Format the shader node graph
    bl_mat_wrap.format_node_tree()
    
    return bl_mat

def generate_error_material():
    ''' Generate a Blender error material that can be applied whenever
    a Mitsuba material cannot be loaded.
    '''
    bl_mat = bpy.data.materials.new(name='mi-error-mat')
    bl_mat.diffuse_color = [1.0, 0.0, 0.3, 1.0]
    return bl_mat
