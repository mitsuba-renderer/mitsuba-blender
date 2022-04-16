import math

if "bpy" in locals():
    import importlib
    if "bl_material_utils" in locals():
        importlib.reload(bl_shader_utils)
    if "mi_spectra_utils" in locals():
        importlib.reload(mi_spectra_utils)
    if "mi_props_utils" in locals():
        importlib.reload(mi_props_utils)
    if "textures" in locals():
        importlib.reload(textures)
    
import bpy

from . import bl_shader_utils
from . import mi_spectra_utils
from . import mi_props_utils
from . import textures

################################
##  Misc property converters  ##
################################

def mi_wrap_mode_to_bl_extension(mi_context, mi_wrap_mode):
    if mi_wrap_mode == 'repeat':
        return 'REPEAT'
    elif mi_wrap_mode == 'mirror':
        # NOTE: Blender does not support mirror wrap mode
        return 'REPEAT'
    elif mi_wrap_mode == 'clamp':
        return 'CLIP'
    else:
        mi_context.log(f'Mitsuba wrap mode "{mi_wrap_mode}" is not supported.', 'ERROR')
        return None

def mi_filter_type_to_bl_interpolation(mi_context, mi_filter_type):
    if mi_filter_type == 'bilinear':
        return 'Cubic'
    elif mi_filter_type == 'nearest':
        return 'Closest'
    else:
        mi_context.log(f'Mitsuba filter type "{mi_filter_type}" is not supported.', 'ERROR')
        return None

_ior_string_values = {
    'acetone': 1.36,
    'acrylic glass': 1.49,
    'air': 1.00028,
    'amber': 1.55,
    'benzene': 1.501,
    'bk7': 1.5046,
    'bromine': 1.661,
    'carbon dioxide': 1.00045,
    'carbon tetrachloride': 1.461,
    'diamond': 2.419,
    'ethanol': 1.361,
    'fused quartz': 1.458,
    'glycerol': 1.4729,
    'helium': 1.00004,
    'hydrogen': 1.00013,
    'pet': 1.575,
    'polypropylene': 1.49,
    'pyrex': 1.470,
    'silicone oil': 1.52045,
    'sodium chloride': 1.544,
    'vacuum': 1.0,
    'water': 1.3330,
    'water ice': 1.31,
}

def mi_ior_string_to_float(mi_context, mi_ior):
    if mi_ior not in _ior_string_values:
        mi_context.log(f'Mitsuba IOR name "{mi_ior}" is not supported.', 'ERROR')
        return 1.0
    return _ior_string_values[mi_ior]

_microfacet_distribution_values = {
    'beckmann': 'BECKMANN',
    'ggx': 'GGX'
}

def mi_microfacet_to_bl_microfacet(mi_context, mi_microfacet_distribution):
    if mi_microfacet_distribution not in _microfacet_distribution_values:
        mi_context.log(f'Mitsuba microfacet distribution "{mi_microfacet_distribution}" not supported.', 'ERROR')
        return 'BECKMANN'
    return _microfacet_distribution_values[mi_microfacet_distribution]

##############################
##  Float property writers  ##
##############################

def write_mi_float_bitmap(mi_context, mi_texture, bl_mat_wrap, out_socket_id, default=None):
    mi_texture_id = mi_texture.id()
    bl_image = mi_context.get_bl_image(mi_texture_id)
    if bl_image is None:
        # FIXME: We forcibly disable sRGB conversion for float textures.
        #        This should probably be done elsewhere.
        mi_texture['raw'] = True
        # If the image is not in the cache, load it from disk.
        # This can happen if we have a texture inside of a BSDF that is itself into a
        # twosided BSDF.
        bl_image = textures.mi_texture_to_bl_image(mi_context, mi_texture)
        if bl_image is None:
            bl_mat_wrap.out_node[out_socket_id].default_value = default
            return
        mi_context.register_bl_image(mi_texture_id, bl_image)

    # FIXME: Support texture coordinate mapping
    bl_teximage = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeTexImage', 'Color')
    bl_teximage.image = bl_image
    bl_teximage.extension = mi_wrap_mode_to_bl_extension(mi_context, mi_texture.get('wrap_mode', 'repeat'))
    bl_teximage.interpolation = mi_filter_type_to_bl_interpolation(mi_context, mi_texture.get('filter_type', 'bilinear'))

_float_texture_writers = {
    'bitmap': write_mi_float_bitmap
}

def write_mi_float_texture(mi_context, mi_texture, bl_mat_wrap, out_socket_id, default=None):
    mi_texture_type = mi_texture.plugin_name()
    if mi_texture_type not in _float_texture_writers:
        mi_context.log(f'Mitsuba Texture type "{mi_texture_type}" is not supported.', 'ERROR')
        return
    _float_texture_writers[mi_texture_type](mi_context, mi_texture, bl_mat_wrap, out_socket_id, default)

def write_mi_float_srgb_reflectance_spectrum(mi_context, mi_obj, bl_mat_wrap, out_socket_id, default=None):
    reflectance = mi_spectra_utils.convert_mi_srgb_reflectance_spectrum(mi_obj, default)
    bl_mat_wrap.out_node.inputs[out_socket_id].default_value = mi_spectra_utils.linear_rgb_to_luminance(reflectance)

_float_spectrum_writers = {
    'SRGBReflectanceSpectrum': write_mi_float_srgb_reflectance_spectrum
}

def write_mi_float_spectrum(mi_context, mi_obj, bl_mat_wrap, out_socket_id, default=None):
    mi_obj_class_name = mi_obj.class_().name()
    if mi_obj_class_name not in _float_spectrum_writers:
        mi_context.log(f'Mitsuba object type "{mi_obj_class_name}" is not supported.', 'ERROR')
        return
    _float_spectrum_writers[mi_obj_class_name](mi_context, mi_obj, bl_mat_wrap, out_socket_id, default)

def write_mi_float_value(mi_context, float_value, bl_mat_wrap, out_socket_id, transformation=None):
    if transformation is not None:
        float_value = transformation(float_value)
    bl_mat_wrap.out_node.inputs[out_socket_id].default_value = float_value

def write_mi_float_property(mi_context, mi_mat, mi_prop_name, bl_mat_wrap, out_socket_id, default=None, transformation=None):
    from mitsuba import Properties
    if mi_mat.has_property(mi_prop_name):
        mi_prop_type = mi_mat.type(mi_prop_name)
        if mi_prop_type == Properties.Type.Float:
            mi_prop_value = mi_mat.get(mi_prop_name, default)
            write_mi_float_value(mi_context, mi_prop_value, bl_mat_wrap, out_socket_id, transformation)
        elif mi_prop_type == Properties.Type.NamedReference:
            mi_texture_ref_id = mi_mat.get(mi_prop_name)
            mi_texture = mi_context.mi_scene_props.get_with_id_and_class(mi_texture_ref_id, 'Texture')
            assert mi_texture is not None
            write_mi_float_texture(mi_context, mi_texture, bl_mat_wrap, out_socket_id, default)
        elif mi_prop_type == Properties.Type.Object:
            mi_obj = mi_mat.get(mi_prop_name)
            write_mi_float_spectrum(mi_context, mi_obj, bl_mat_wrap, out_socket_id, default)
        else:
            mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to float.', 'ERROR')
    elif default is not None:
        bl_mat_wrap.out_node.inputs[out_socket_id].default_value = default
    else:
        mi_context.log(f'Material "{mi_mat.id()}" does not have property "{mi_prop_name}".', 'ERROR')

############################
##  RGB property writers  ##
############################

def write_mi_rgb_bitmap(mi_context, mi_texture, bl_mat_wrap, out_socket_id, default=None):
    mi_texture_id = mi_texture.id()
    bl_image = mi_context.get_bl_image(mi_texture_id)
    if bl_image is None:
        # If the image is not in the cache, load it from disk.
        # This can happen if we have a texture inside of a BSDF that is itself into a
        # twosided BSDF.
        bl_image = textures.mi_texture_to_bl_image(mi_context, mi_texture)
        if bl_image is None:
            bl_mat_wrap.out_node[out_socket_id].default_value = bl_shader_utils.rgb_to_rgba(default)
            return
        mi_context.register_bl_image(mi_texture_id, bl_image)

    # FIXME: Support texture coordinate mapping
    bl_teximage = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeTexImage', 'Color')
    bl_teximage.image = bl_image
    bl_teximage.extension = mi_wrap_mode_to_bl_extension(mi_context, mi_texture.get('wrap_mode', 'repeat'))
    bl_teximage.interpolation = mi_filter_type_to_bl_interpolation(mi_context, mi_texture.get('filter_type', 'bilinear'))

_rgb_texture_writers = {
    'bitmap': write_mi_rgb_bitmap
}

def write_mi_rgb_texture(mi_context, mi_texture, bl_mat_wrap, out_socket_id, default=None):
    mi_texture_type = mi_texture.plugin_name()
    if mi_texture_type not in _rgb_texture_writers:
        mi_context.log(f'Mitsuba Texture type "{mi_texture_type}" is not supported.', 'ERROR')
        return
    _rgb_texture_writers[mi_texture_type](mi_context, mi_texture, bl_mat_wrap, out_socket_id, default)

def write_mi_rgb_srgb_reflectance_spectrum(mi_context, mi_obj, bl_mat_wrap, out_socket_id, default=None):
    reflectance = mi_spectra_utils.convert_mi_srgb_reflectance_spectrum(mi_obj, default)
    bl_mat_wrap.out_node.inputs[out_socket_id].default_value = bl_shader_utils.rgb_to_rgba(reflectance)

_rgb_spectrum_writers = {
    'SRGBReflectanceSpectrum': write_mi_rgb_srgb_reflectance_spectrum
}

def write_mi_rgb_spectrum(mi_context, mi_obj, bl_mat_wrap, out_socket_id, default=None):
    mi_obj_class_name = mi_obj.class_().name()
    if mi_obj_class_name not in _rgb_spectrum_writers:
        mi_context.log(f'Mitsuba object type "{mi_obj_class_name}" is not supported.', 'ERROR')
        return
    _rgb_spectrum_writers[mi_obj_class_name](mi_context, mi_obj, bl_mat_wrap, out_socket_id, default)

def write_mi_rgb_value(mi_context, rgb_value, bl_mat_wrap, out_socket_id):
    bl_mat_wrap.out_node.inputs[out_socket_id].default_value = bl_shader_utils.rgb_to_rgba(rgb_value)

def write_mi_rgb_property(mi_context, mi_mat, mi_prop_name, bl_mat_wrap, out_socket_id, default=None):
    from mitsuba import Properties
    if mi_mat.has_property(mi_prop_name):
        mi_prop_type = mi_mat.type(mi_prop_name)
        if mi_prop_type == Properties.Type.Color:
            write_mi_rgb_value(mi_context, list(mi_mat.get(mi_prop_name, default)), bl_mat_wrap, out_socket_id)
        elif mi_prop_type == Properties.Type.NamedReference:
            mi_texture_ref_id = mi_mat.get(mi_prop_name)
            mi_texture = mi_context.mi_scene_props.get_with_id_and_class(mi_texture_ref_id, 'Texture')
            assert mi_texture is not None
            write_mi_rgb_texture(mi_context, mi_texture, bl_mat_wrap, out_socket_id, default)
        elif mi_prop_type == Properties.Type.Object:
            mi_obj = mi_mat.get(mi_prop_name)
            write_mi_rgb_spectrum(mi_context, mi_obj, bl_mat_wrap, out_socket_id, default)
        else:
            mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to rgb.', 'ERROR')
    elif default is not None:
        bl_mat_wrap.out_node.inputs[out_socket_id].default_value = bl_shader_utils.rgb_to_rgba(default)
    else:
        mi_context.log(f'Material "{mi_mat.id()}" does not have property "{mi_prop_name}".', 'ERROR')

############################
##  IOR property writers  ##
############################

def write_mi_ior_property(mi_context, mi_mat, mi_prop_name, bl_mat_wrap, out_socket_id, default=None):
    from mitsuba import Properties
    if mi_mat.has_property(mi_prop_name):
        mi_prop_type = mi_mat.type(mi_prop_name)
        if mi_prop_type == Properties.Type.Float:
            bl_mat_wrap.out_node.inputs[out_socket_id].default_value = mi_mat.get(mi_prop_name, default)
        elif mi_prop_type == Properties.Type.String:
            bl_mat_wrap.out_node.inputs[out_socket_id].default_value = mi_ior_string_to_float(mi_context, mi_mat.get(mi_prop_name, 'bk7'))
        else:
            mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to float.', 'ERROR')
    elif default is not None:
        bl_mat_wrap.out_node.inputs[out_socket_id].default_value = default
    else:
        mi_context.log(f'Material "{mi_mat.id()}" does not have property "{mi_prop_name}".', 'ERROR')

######################
##   BSDF writers   ##
######################

def write_mi_principled_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_principled = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfPrincipled', 'BSDF')
    bl_principled_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_principled)
    write_mi_rgb_property(mi_context, mi_mat, 'base_color', bl_principled_wrap, 'Base Color', [0.8, 0.8, 0.8])
    write_mi_float_property(mi_context, mi_mat, 'specular', bl_principled_wrap, 'Specular', 0.5)
    write_mi_float_property(mi_context, mi_mat, 'spec_tint', bl_principled_wrap, 'Specular Tint', 0.0)
    write_mi_float_property(mi_context, mi_mat, 'spec_trans', bl_principled_wrap, 'Transmission', 0.0)
    write_mi_float_property(mi_context, mi_mat, 'metallic', bl_principled_wrap, 'Metallic', 0.0)
    write_mi_float_property(mi_context, mi_mat, 'anisotropic', bl_principled_wrap, 'Anisotropic', 0.0)
    # FIXME: Check which parameters need transformations when loaded
    write_mi_float_property(mi_context, mi_mat, 'roughness', bl_principled_wrap, 'Roughness', math.sqrt(0.4), lambda x: x ** 2)
    write_mi_float_property(mi_context, mi_mat, 'sheen', bl_principled_wrap, 'Sheen', 0.0)
    write_mi_float_property(mi_context, mi_mat, 'sheen_tint', bl_principled_wrap, 'Sheen Tint', 0.5)
    write_mi_float_property(mi_context, mi_mat, 'clearcoat', bl_principled_wrap, 'Clearcoat', 0.0)
    write_mi_float_property(mi_context, mi_mat, 'clearcoat_gloss', bl_principled_wrap, 'Clearcoat Roughness', math.sqrt(0.03), lambda x: x ** 2)
    return True

def write_mi_diffuse_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_diffuse = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfDiffuse', 'BSDF')
    bl_diffuse_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_diffuse)
    write_mi_rgb_property(mi_context, mi_mat, 'reflectance', bl_diffuse_wrap, 'Color', [0.8, 0.8, 0.8])
    return True

def write_mi_twosided_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    mi_child_materials = mi_props_utils.named_references_with_class(mi_context, mi_mat, 'BSDF')
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

def write_mi_dielectric_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_glass = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfGlass', 'BSDF')
    bl_glass_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_glass)
    # FIXME: Is this the correct distribution ?
    bl_glass.distribution = 'SHARP'
    write_mi_ior_property(mi_context, mi_mat, 'int_ior', bl_glass_wrap, 'IOR', 1.5046)
    write_mi_rgb_property(mi_context, mi_mat, 'specular_transmittance', bl_glass_wrap, 'Color', [1.0, 1.0, 1.0])
    return True

def write_mi_roughdielectric_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_glass = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfGlass', 'BSDF')
    bl_glass_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_glass)
    bl_glass.distribution = mi_microfacet_to_bl_microfacet(mi_context, mi_mat.get('distribution', 'beckmann'))
    write_mi_ior_property(mi_context, mi_mat, 'int_ior', bl_glass_wrap, 'IOR', 1.5046)
    write_mi_rgb_property(mi_context, mi_mat, 'specular_transmittance', bl_glass_wrap, 'Color', [1.0, 1.0, 1.0])
    write_mi_float_property(mi_context, mi_mat, 'alpha', bl_glass_wrap, 'Roughness', math.sqrt(0.1), lambda x: x ** 2)
    return True

def write_mi_thindielectric_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_glass = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfGlass', 'BSDF')
    bl_glass_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_glass)
    bl_glass.distribution = 'SHARP'
    bl_glass.inputs['IOR'].default_value = 1.0
    write_mi_rgb_property(mi_context, mi_mat, 'specular_transmittance', bl_glass_wrap, 'Color', [1.0, 1.0, 1.0])
    return True

def write_mi_blend_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_mix = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeMixShader', 'Shader')
    bl_mix_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_mix)
    write_mi_float_property(mi_context, mi_mat, 'weight', bl_mix_wrap, 'Fac', 0.5)
    # NOTE: We assume that the two BSDFs are ordered in the list of named references
    mi_child_mats = mi_props_utils.named_references_with_class(mi_context, mi_mat, 'BSDF')
    mi_child_mats_count = len(mi_child_mats)
    if mi_child_mats_count != 2:
        mi_context.log(f'Unexpected number of child BSDFs in blendbsdf. Expected 2 but got {mi_child_mats_count}.', 'ERROR')
        return False
    write_mi_material_to_node_graph(mi_context, mi_child_mats[0], bl_mix_wrap, 'Shader')
    write_mi_material_to_node_graph(mi_context, mi_child_mats[1], bl_mix_wrap, 'Shader_001')
    return True

def write_mi_conductor_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_glossy = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfGlossy', 'BSDF')
    bl_glossy_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_glossy)
    bl_glossy.distribution = 'SHARP'
    write_mi_rgb_property(mi_context, mi_mat, 'specular_reflectance', bl_glossy_wrap, 'Color', [1.0, 1.0, 1.0])
    return True

def write_mi_roughconductor_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_glossy = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfGlossy', 'BSDF')
    bl_glossy_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_glossy)
    bl_glossy.distribution = mi_microfacet_to_bl_microfacet(mi_context, mi_mat.get('distribution', 'beckmann'))
    write_mi_rgb_property(mi_context, mi_mat, 'specular_reflectance', bl_glossy_wrap, 'Color', [1.0, 1.0, 1.0])
    write_mi_float_property(mi_context, mi_mat, 'alpha', bl_glossy_wrap, 'Roughness', math.sqrt(0.1), lambda x: x ** 2)
    return True

def write_mi_mask_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_mix = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeMixShader', 'Shader')
    bl_mix_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_mix)
    # Connect the opacity. A value of 0 is completely transparent and 1 is completely opaque.
    write_mi_float_property(mi_context, mi_mat, 'opacity', bl_mix_wrap, 'Fac', 0.5)
    # Add a transparent node to the top socket of the mix shader
    bl_mix_wrap.ensure_node_type(['Shader'], 'ShaderNodeBsdfTransparent', 'BSDF')
    # Parse the other BSDF
    mi_child_mats = mi_props_utils.named_references_with_class(mi_context, mi_mat, 'BSDF')
    mi_child_mats_count = len(mi_child_mats)
    if mi_child_mats_count != 1:
        mi_context.log(f'Unexpected number of child BSDFs in mask BSDF. Expected 1 but got {mi_child_mats_count}.', 'ERROR')
        return False
    write_mi_material_to_node_graph(mi_context, mi_child_mats[0], bl_mix_wrap, 'Shader_001')
    return True

# FIXME: The plastic and roughplastic don't have simple equivalent in Blender. We rely on a 
#        crude approximation using a Disney principled shader.
def write_mi_plastic_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_principled = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfPrincipled', 'BSDF')
    bl_principled_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_principled)
    write_mi_rgb_property(mi_context, mi_mat, 'diffuse_reflectance', bl_principled_wrap, 'Base Color', [0.5, 0.5, 0.5])
    write_mi_ior_property(mi_context, mi_mat, 'int_ior', bl_principled_wrap, 'IOR', 1.49)
    bl_principled.inputs['Specular'].default_value = 0.2
    bl_principled.inputs['Specular Tint'].default_value = 1.0
    bl_principled.inputs['Roughness'].default_value = 0.0
    bl_principled.inputs['Clearcoat'].default_value = 0.8
    bl_principled.inputs['Clearcoat Roughness'].default_value = 0.0
    return True

def write_mi_roughplastic_bsdf(mi_context, mi_mat, bl_mat_wrap, out_socket_id):
    bl_principled = bl_mat_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBsdfPrincipled', 'BSDF')
    bl_principled_wrap = bl_shader_utils.NodeMaterialWrapper(bl_mat_wrap.bl_mat, out_node=bl_principled)
    write_mi_rgb_property(mi_context, mi_mat, 'diffuse_reflectance', bl_principled_wrap, 'Base Color', [0.5, 0.5, 0.5])
    write_mi_ior_property(mi_context, mi_mat, 'int_ior', bl_principled_wrap, 'IOR', 1.49)
    write_mi_float_property(mi_context, mi_mat, 'alpha', bl_principled_wrap, 'Roughness', math.sqrt(0.1), lambda x: x ** 2)
    write_mi_float_property(mi_context, mi_mat, 'alpha', bl_principled_wrap, 'Clearcoat Roughness', math.sqrt(0.1), lambda x: x ** 2)
    bl_principled.distribution = mi_microfacet_to_bl_microfacet(mi_context, 'ggx')
    bl_principled.inputs['Specular'].default_value = 0.2
    bl_principled.inputs['Specular Tint'].default_value = 1.0
    bl_principled.inputs['Clearcoat'].default_value = 0.8
    return True

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
    'dielectric': write_mi_dielectric_bsdf,
    'roughdielectric': write_mi_roughdielectric_bsdf,
    'thindielectric': write_mi_thindielectric_bsdf,
    'blendbsdf': write_mi_blend_bsdf,
    'conductor': write_mi_conductor_bsdf,
    'roughconductor': write_mi_roughconductor_bsdf,
    'mask': write_mi_mask_bsdf,
    'plastic': write_mi_plastic_bsdf,
    'roughplastic': write_mi_roughplastic_bsdf,
}

# List of transmissive materials that are always two-sided
_transmissive_materials = [
    'dielectric',
    'roughdielectric',
    'thindielectric',
    'mask',
]

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
    
    if not is_within_twosided and mat_type != 'twosided' and mat_type not in _transmissive_materials:
        # Write one-sided material
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
