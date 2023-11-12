import math

import bpy

from . import mi_spectra_utils
from . import mi_props_utils
from . import textures
from ..utils import nodetree
from ..utils import material
from ..utils import math as math_utils

class MaterialConverter:
    '''
    Base class for material converters
    '''
    def __init__(self, mi_context):
        self.mi_context = mi_context

    def write_error_material(self, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_material(self, mi_mat, parent_node, in_socket_id, is_within_twosided=False):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_null_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_principled_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_diffuse_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_twosided_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_dielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_roughdielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_thindielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_blendbsdf_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_conductor_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_roughconductor_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_mask_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_plastic_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_roughplastic_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_bumpmap_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_normalmap_bsdf(self, mi_mat, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_generic_bsdf(self, mi_mat, parent_node, in_socket_id):
        mat_type = mi_mat.plugin_name()
        function_name = f'write_mi_{mat_type}_bsdf'
        converter = getattr(self, function_name)
        if converter is None:
            self.mi_context.log(f'Mitsuba BSDF type "{mat_type}" not supported. Skipping.', 'WARN')
            self.write_error_material(parent_node, in_socket_id)
            return False
        return converter(mi_mat, parent_node, in_socket_id)

    def write_mi_float_texture(self, mi_texture, parent_node, in_socket_id, default=None):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_float_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_float_value(self, value, parent_node, in_socket_id, transformation=None):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_float_property(self, mi_props, mi_prop_name, parent_node, in_socket_id, default=None, transformation=None):
        from mitsuba import Properties
        if mi_props.has_property(mi_prop_name):
            mi_prop_type = mi_props.type(mi_prop_name)
            if mi_prop_type == Properties.Type.Float:
                mi_prop_value = mi_props.get(mi_prop_name, default)
                self.write_mi_float_value(mi_prop_value, parent_node, in_socket_id, transformation)
            elif mi_prop_type == Properties.Type.NamedReference:
                mi_texture_ref_id = mi_props.get(mi_prop_name)
                mi_texture = self.mi_context.mi_scene_props.get_with_id_and_class(mi_texture_ref_id, 'Texture')
                assert mi_texture is not None
                self.write_mi_float_texture(mi_texture, parent_node, in_socket_id, default)
            elif mi_prop_type == Properties.Type.Object:
                mi_props = mi_props.get(mi_prop_name)
                self.write_mi_float_spectrum(mi_props, parent_node, in_socket_id, default)
            else:
                self.mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to float.', 'ERROR')
        elif default is not None:
            self.write_mi_float_value(default, parent_node, in_socket_id, transformation)
        else:
            self.mi_context.log(f'Material "{mi_props.id()}" does not have property "{mi_prop_name}".', 'ERROR')

    def write_mi_rgb_texture(self, mi_texture, parent_node, in_socket_id, default=None):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_rgb_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_rgb_value(self, value, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

    def write_mi_rgb_property(self, mi_props, mi_prop_name, parent_node, in_socket_id, default=None):
        from mitsuba import Properties
        if mi_props.has_property(mi_prop_name):
            mi_prop_type = mi_props.type(mi_prop_name)
            if mi_prop_type == Properties.Type.Color:
                self.write_mi_rgb_value(list(mi_props.get(mi_prop_name, default)), parent_node, in_socket_id)
            elif mi_prop_type == Properties.Type.NamedReference:
                mi_texture_ref_id = mi_props.get(mi_prop_name)
                mi_texture = self.mi_context.mi_scene_props.get_with_id_and_class(mi_texture_ref_id, 'Texture')
                assert mi_texture is not None
                self.write_mi_rgb_texture(mi_texture, parent_node, in_socket_id, default)
            elif mi_prop_type == Properties.Type.Object:
                mi_obj = mi_props.get(mi_prop_name)
                self.write_mi_rgb_spectrum(mi_obj, parent_node, in_socket_id, default)
            else:
                self.mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to rgb.', 'ERROR')
        elif default is not None:
            self.write_mi_rgb_value(default, parent_node, in_socket_id)
        else:
            self.mi_context.log(f'Material "{mi_props.id()}" does not have property "{mi_prop_name}".', 'ERROR')

    def write_mi_transform2d_property(self, mi_props, mi_prop_name, parent_node, in_socket_id):
        raise NotImplementedError('Implemented by subclasses')

#########################
##  Blender Converter  ##
#########################

class BlenderMaterialConverter(MaterialConverter):
    '''
    Material converter for Cycles shader node tree
    '''
    def __init__(self, mi_context):
        super().__init__(mi_context)
        self.mi_bump = None
        self.mi_normalmap = None

    def _eval_mi_bsdf_retro_reflection(self, mi_mat, default=None):
        ''' Evaluate the reflectance color of a BSDF for a perfect perpendicular reflection '''
        from mitsuba import load_dict, BSDFContext, SurfaceInteraction3f, Vector3f
        # Generate the BSDF properties dictionary
        bsdf_dict = {
            'type': mi_mat.plugin_name(),
        }
        for name in mi_mat.property_names():
            bsdf_dict[name] = mi_mat.get(name)

        bsdf = load_dict(bsdf_dict)
        si = SurfaceInteraction3f()
        si.wi = Vector3f(0.0, 0.0, 1.0)
        wo = Vector3f(0.0, 0.0, 1.0)
        color, pdf = bsdf.eval_pdf(BSDFContext(), si, wo)
        if pdf == 0.0:
            if default is None:
                self.mi_context.log(f'Failed to evaluate "{mi_mat.id()}" conductor BSDF.', 'ERROR')
                return None
            return default
        return list(color / pdf)

    def _mi_wrap_mode_to_bl_extension(self, mi_wrap_mode):
        if mi_wrap_mode == 'repeat':
            return 'REPEAT'
        elif mi_wrap_mode == 'mirror':
            # NOTE: Blender does not support mirror wrap mode
            return 'REPEAT'
        elif mi_wrap_mode == 'clamp':
            return 'CLIP'
        else:
            self.mi_context.log(f'Mitsuba wrap mode "{mi_wrap_mode}" is not supported.', 'ERROR')
            return None

    def _mi_filter_type_to_bl_interpolation(self, mi_filter_type):
        if mi_filter_type == 'bilinear':
            return 'Cubic'
        elif mi_filter_type == 'nearest':
            return 'Closest'
        else:
            self.mi_context.log(f'Mitsuba filter type "{mi_filter_type}" is not supported.', 'ERROR')
            return None

    def _mi_microfacet_to_bl_microfacet(self, mi_microfacet_distribution):
        if mi_microfacet_distribution == 'beckmann':
            return 'BECKMANN'
        elif mi_microfacet_distribution == 'ggx':
            return 'GGX'
        else:
            self.mi_context.log(f'Mitsuba microfacet distribution "{mi_microfacet_distribution}" not supported.', 'ERROR')
            return 'BECKMANN'

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

    def _mi_ior_string_to_float(self, mi_ior):
        if mi_ior not in self._ior_string_values:
            self.mi_context.log(f'Mitsuba IOR name "{mi_ior}" is not supported.', 'ERROR')
            return 1.0
        return self._ior_string_values[mi_ior]

    def _write_mi_ior_property(self, mi_mat, mi_prop_name, parent_node, in_socket_id, default: str=None):
        from mitsuba import Properties
        if mi_mat.has_property(mi_prop_name):
            mi_prop_type = mi_mat.type(mi_prop_name)
            if mi_prop_type == Properties.Type.Float:
                parent_node.set_property(in_socket_id, mi_mat.get(mi_prop_name, self._mi_ior_string_to_float(default)))
            elif mi_prop_type == Properties.Type.String:
                parent_node.set_property(in_socket_id, self._mi_ior_string_to_float(mi_mat.get(mi_prop_name, 'bk7')))
            else:
                self.mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to float.', 'ERROR')
        elif default is not None:
            parent_node.set_property(in_socket_id, self._mi_ior_string_to_float(default))
        else:
            self.mi_context.log(f'Material "{mi_mat.id()}" does not have property "{mi_prop_name}".', 'ERROR')

    def _write_mi_roughness_property(self, mi_mat, mi_prop_name, parent_node, in_socket_id, default=None):
        self.write_mi_float_property(mi_mat, mi_prop_name, parent_node, in_socket_id, default ** 2, lambda x: math.sqrt(x))

    def _write_mi_bump_and_normal_maps(self, parent_node, in_socket_id):
        normalmap_parent_node = parent_node
        if self.mi_bump is not None:
            bump_node = parent_node.create_linked('ShaderNodeBump', in_socket_id, out_socket_id='Normal')
            mi_bump_textures = mi_props_utils.named_references_with_class(self.mi_context, self.mi_bump, 'Texture')
            assert len(mi_bump_textures) == 1
            self.write_mi_float_texture(mi_bump_textures[0], bump_node, 'Height', 0.0)
            # FIXME: Can we map directly this value ?
            self.write_mi_float_property(self.mi_bump, 'scale', bump_node, 'Distance', 1.0)
            normalmap_parent_node = bump_node

        if self.mi_normalmap is not None:
            normalmap_node = normalmap_parent_node.create_linked('ShaderNodeNormalMap', in_socket_id, out_socket_id='Normal')
            self.write_mi_rgb_property(self.mi_normalmap, 'normalmap', normalmap_node, 'Color', [0.5, 0.5, 1.0])

    def _write_twosided_material(self, parent_node, in_socket_id, mi_front_mat, mi_back_mat=None):
        mix_node = parent_node.create_linked('ShaderNodeMixShader', in_socket_id, out_socket_id='Shader')
        # Generate a geometry node that will select the correct BSDF based on face orientation
        mix_node.create_linked('ShaderNodeNewGeometry', 'Fac', out_socket_id='Backfacing')
        # Write the child materials
        self.write_mi_material(mi_front_mat, mix_node, 'Shader', is_within_twosided=True)
        if mi_back_mat is not None:
            self.write_mi_material(mi_back_mat, mix_node, 'Shader_001', is_within_twosided=True)
        else:
            diffuse_node = mix_node.create_linked('ShaderNodeBsdfDiffuse', 'Shader_001')
            diffuse_node.set_property('Color', material.rgb_to_rgba([0.0, 0.0, 0.0]))
        return True

    def write_mi_emitter_bsdf(self, parent_node, in_socket_id, mi_emitter):
        add_node = parent_node.create_linked('ShaderNodeAddShader', in_socket_id, out_socket_id='Shader')
        emissive_node = add_node.create_linked('ShaderNodeEmission', 'Shader', out_socket_id='Emission')
        radiance, strength = mi_spectra_utils.convert_mi_srgb_emitter_spectrum(mi_emitter.get('radiance'), [1.0, 1.0, 1.0])
        emissive_node.set_property('Color', material.rgb_to_rgba(radiance))
        emissive_node.set_property('Strength', strength)
        return add_node, 'Shader_001'

    def write_error_material(self, parent_node, in_socket_id):
        diffuse_node = parent_node.create_linked('ShaderNodeBsdfDiffuse', in_socket_id)
        diffuse_node.set_property('Color', material.rgb_to_rgba([1.0, 0.0, 0.3]))

    def write_mi_null_bsdf(self, mi_mat, parent_node, in_socket_id):
        parent_node.create_linked('ShaderNodeBsdfTransparent', in_socket_id)
        return True

    def write_mi_principled_bsdf(self, mi_mat, parent_node, in_socket_id):
        principled_node = parent_node.create_linked('ShaderNodeBsdfPrincipled', in_socket_id)
        self.write_mi_rgb_property(mi_mat, 'base_color', principled_node, 'Base Color', [0.8, 0.8, 0.8])
        self.write_mi_float_property(mi_mat, 'specular', principled_node, 'Specular', 0.5)
        self.write_mi_float_property(mi_mat, 'eta', principled_node, 'IOR', 1.450)
        self.write_mi_float_property(mi_mat, 'spec_tint', principled_node, 'Specular Tint', 0.0)
        self.write_mi_float_property(mi_mat, 'spec_trans', principled_node, 'Transmission', 0.0)
        self.write_mi_float_property(mi_mat, 'metallic', principled_node, 'Metallic', 0.0)
        self.write_mi_float_property(mi_mat, 'anisotropic', principled_node, 'Anisotropic', 0.0)
        self._write_mi_roughness_property(mi_mat, 'roughness', principled_node, 'Roughness', 0.4)
        self.write_mi_float_property(mi_mat, 'sheen', principled_node, 'Sheen', 0.0)
        self.write_mi_float_property(mi_mat, 'sheen_tint', principled_node, 'Sheen Tint', 0.5)
        self.write_mi_float_property(mi_mat, 'flatness', principled_node, 'Subsurface', 0.0)
        self.write_mi_rgb_property(mi_mat, 'base_color', principled_node, 'Subsurface Color', [0.8, 0.8, 0.8])
        self.write_mi_float_property(mi_mat, 'clearcoat', principled_node, 'Clearcoat', 0.0)
        self._write_mi_roughness_property(mi_mat, 'clearcoat_gloss', principled_node, 'Clearcoat Roughness', 0.03)
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(principled_node, 'Normal')
        return True

    def write_mi_diffuse_bsdf(self, mi_mat, parent_node, in_socket_id):
        diffuse_node = parent_node.create_linked('ShaderNodeBsdfDiffuse', in_socket_id)
        self.write_mi_rgb_property(mi_mat, 'reflectance', diffuse_node, 'Color', [0.8, 0.8, 0.8])
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(diffuse_node, 'Normal')
        return True

    def write_mi_twosided_bsdf(self, mi_mat, parent_node, in_socket_id):
        mi_child_materials = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        mi_child_material_count = len(mi_child_materials)
        if mi_child_material_count == 1:
            # This case is handled by simply parsing the material. Blender materials are two-sided by default
            # NOTE: We always parse the Mitsuba material; we don't use the material cache.
            #       This is because we have no way of reusing already created materials as a 'sub-material'.
            self.write_mi_material(mi_child_materials[0], parent_node, in_socket_id, is_within_twosided=True)
            return True
        elif mi_child_material_count == 2:
            # This case is handled by creating a two-side material where the front face has the first
            # material and the back face has the second one.
            self._write_twosided_material(parent_node, in_socket_id, mi_child_materials[0], mi_child_materials[1])
            return True
        else:
            self.mi_context.log(f'Mitsuba twosided material "{mi_mat.id()}" has {mi_child_material_count} child material(s). Expected 1 or 2.', 'ERROR')
            return False

    def write_mi_dielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        glass_node = parent_node.create_linked('ShaderNodeBsdfGlass', in_socket_id)
        # FIXME: Is this the correct distribution ?
        glass_node.set_property('distribution', 'SHARP')
        self._write_mi_ior_property(mi_mat, 'int_ior', glass_node, 'IOR', 'bk7')
        self.write_mi_rgb_property(mi_mat, 'specular_transmittance', glass_node, 'Color', [1.0, 1.0, 1.0])
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(glass_node, 'Normal')
        return True

    def write_mi_roughdielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        glass_node = parent_node.create_linked('ShaderNodeBsdfGlass', in_socket_id)
        glass_node.set_property('distribution', self._mi_microfacet_to_bl_microfacet(mi_mat.get('distribution', 'beckmann')))
        self._write_mi_ior_property(mi_mat, 'int_ior', glass_node, 'IOR', 'bk7')
        self.write_mi_rgb_property(mi_mat, 'specular_transmittance', glass_node, 'Color', [1.0, 1.0, 1.0])
        self._write_mi_roughness_property(mi_mat, 'alpha', glass_node, 'Roughness', 0.1)
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(glass_node, 'Normal')
        return True

    def write_mi_thindielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        glass_node = parent_node.create_linked('ShaderNodeBsdfGlass', in_socket_id)
        glass_node.set_property('distribution', 'SHARP')
        glass_node.set_property('IOR', 1.0)
        self.write_mi_rgb_property(mi_mat, 'specular_transmittance', glass_node, 'Color', [1.0, 1.0, 1.0])
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(glass_node, 'Normal')
        return True

    def write_mi_blendbsdf_bsdf(self, mi_mat, parent_node, in_socket_id):
        mix_node = parent_node.create_linked('ShaderNodeMixShader', in_socket_id, out_socket_id='Shader')
        self.write_mi_float_property(mi_mat, 'weight', mix_node, 'Fac', 0.5)
        # NOTE: We assume that the two BSDFs are ordered in the list of named references
        mi_child_mats = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        mi_child_mats_count = len(mi_child_mats)
        if mi_child_mats_count != 2:
            self.mi_context.log(f'Unexpected number of child BSDFs in blendbsdf. Expected 2 but got {mi_child_mats_count}.', 'ERROR')
            return False
        self.write_mi_material(mi_child_mats[0], mix_node, 'Shader')
        self.write_mi_material(mi_child_mats[1], mix_node, 'Shader_001')
        return True

    def write_mi_conductor_bsdf(self, mi_mat, parent_node, in_socket_id):
        glossy_node = parent_node.create_linked('ShaderNodeBsdfGlossy', in_socket_id)
        glossy_node.set_property('distribution', 'SHARP')
        reflectance = self._eval_mi_bsdf_retro_reflection(mi_mat, [1.0, 1.0, 1.0])
        self.write_mi_rgb_value(reflectance, glossy_node, 'Color')
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(glossy_node, 'Normal')
        return True

    def write_mi_roughconductor_bsdf(self, mi_mat, parent_node, in_socket_id):
        glossy_node = parent_node.create_linked('ShaderNodeBsdfGlossy', in_socket_id)
        glossy_node.set_property('distribution', self._mi_microfacet_to_bl_microfacet(mi_mat.get('distribution', 'beckmann')))
        reflectance = self._eval_mi_bsdf_retro_reflection(mi_mat, [1.0, 1.0, 1.0])
        self.write_mi_rgb_value(reflectance, glossy_node, 'Color')
        self._write_mi_roughness_property(mi_mat, 'alpha', glossy_node, 'Roughness', 0.1)
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(glossy_node, 'Normal')
        return True

    def write_mi_mask_bsdf(self, mi_mat, parent_node, in_socket_id):
        mix_node = parent_node.create_linked('ShaderNodeMixShader', in_socket_id, out_socket_id='Shader')
        # Connect the opacity. A value of 0 is completely transparent and 1 is completely opaque.
        self.write_mi_float_property(mi_mat, 'opacity', mix_node, 'Fac', 0.5)
        # Add a transparent node to the top socket of the mix shader
        mix_node.create_linked('ShaderNodeBsdfTransparent', 'Shader')
        # Parse the other BSDF
        mi_child_mats = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        mi_child_mats_count = len(mi_child_mats)
        if mi_child_mats_count != 1:
            self.mi_context.log(f'Unexpected number of child BSDFs in mask BSDF. Expected 1 but got {mi_child_mats_count}.', 'ERROR')
            return False
        self.write_mi_material(mi_child_mats[0], mix_node, 'Shader_001')
        return True

    # FIXME: The plastic and roughplastic don't have simple equivalent in Blender. We rely on a 
    #        crude approximation using a Disney principled shader.
    def write_mi_plastic_bsdf(self, mi_mat, parent_node, in_socket_id):
        principled_node = parent_node.create_linked('ShaderNodeBsdfPrincipled', in_socket_id)
        self.write_mi_rgb_property(mi_mat, 'diffuse_reflectance', principled_node, 'Base Color', [0.5, 0.5, 0.5])
        self._write_mi_ior_property(mi_mat, 'int_ior', principled_node, 'IOR', 'polypropylene')
        principled_node.set_property('Specular', 0.2)
        principled_node.set_property('Specular Tint', 1.0)
        principled_node.set_property('Roughness', 0.0)
        principled_node.set_property('Clearcoat', 0.8)
        principled_node.set_property('Clearcoat Roughness', 0.0)
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(principled_node, 'Normal')
        return True

    def write_mi_roughplastic_bsdf(self, mi_mat, parent_node, in_socket_id):
        principled_node = parent_node.create_linked('ShaderNodeBsdfPrincipled', in_socket_id)
        self.write_mi_rgb_property(mi_mat, 'diffuse_reflectance', principled_node, 'Base Color', [0.5, 0.5, 0.5])
        self._write_mi_ior_property(mi_mat, 'int_ior', principled_node, 'IOR', 'polypropylene')
        self._write_mi_roughness_property(mi_mat, 'alpha', principled_node, 'Roughness', 0.1)
        self._write_mi_roughness_property(mi_mat, 'alpha', principled_node, 'Clearcoat Roughness', 0.1)
        principled_node.set_property('distribution', self._mi_microfacet_to_bl_microfacet('ggx'))
        principled_node.set_property('Specular', 0.2)
        principled_node.set_property('Specular Tint', 1.0)
        principled_node.set_property('Clearcoat', 0.8)
        # Write normal and bump maps
        self._write_mi_bump_and_normal_maps(principled_node, 'Normal')
        return True

    def write_mi_bumpmap_bsdf(self, mi_mat, parent_node, in_socket_id):
        if self.mi_bump is not None:
            self.mi_context.log('Cannot have nested bumpmap BSDFs', 'ERROR')
            return False
        child_mats = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        assert len(child_mats) == 1
        
        self.mi_bump = mi_mat
        self.write_mi_material(child_mats[0], parent_node, in_socket_id)
        self.mi_bump = None

        return True

    def write_mi_normalmap_bsdf(self, mi_mat, parent_node, in_socket_id):
        if self.mi_normalmap is not None:
            self.mi_context.log('Cannot have nested normalmap BSDFs', 'ERROR')
            return False
        child_mats = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        assert len(child_mats) == 1

        self.mi_normalmap = mi_mat
        self.write_mi_material(child_mats[0], parent_node, in_socket_id)
        self.mi_normalmap = None

        return True

    # List of materials that are always two-sided. These are the transmissive materials and
    # a few material wrappers.
    _always_twosided_bsdfs = [
        'dielectric',
        'roughdielectric',
        'thindielectric',
        'mask',
        'bumpmap',
        'normalmap',
        'null',
    ]

    def write_mi_material(self, mi_mat, parent_node, in_socket_id, is_within_twosided=False):
        mat_type = mi_mat.plugin_name()
        if is_within_twosided and mat_type == 'twosided':
            self.mi_context.log('Cannot have nested twosided materials.', 'ERROR')
            return
        
        if not is_within_twosided and mat_type != 'twosided' and mat_type not in self._always_twosided_bsdfs:
            # Write one-sided material
            self._write_twosided_material(parent_node, in_socket_id, mi_front_mat=mi_mat, mi_back_mat=None)
        elif not self.write_generic_bsdf(mi_mat, parent_node, in_socket_id):
            self.mi_context.log(f'Failed to convert Mitsuba material "{mi_mat.id()}". Skipping.', 'WARN')
            self.write_error_material(parent_node, in_socket_id)

    def write_mi_float_bitmap(self, mi_texture, parent_node, in_socket_id, default=None):
        mi_texture_id = mi_texture.id()
        bl_image = self.mi_context.get_bl_image(mi_texture_id)
        if bl_image is None:
            # FIXME: We forcibly disable sRGB conversion for float textures.
            #        This should probably be done elsewhere.
            mi_texture['raw'] = True
            # If the image is not in the cache, load it from disk.
            # This can happen if we have a texture inside of a BSDF that is itself into a
            # twosided BSDF.
            bl_image = textures.mi_texture_to_bl_image(self.mi_context, mi_texture)
            if bl_image is None:
                parent_node.set_property(in_socket_id, default)
                return
            self.mi_context.register_bl_image(mi_texture_id, bl_image)

        # FIXME: Support texture coordinate mapping
        # FIXME: For float textures, it is not always clear if we should use the 'Alpha' output instead of the luminance value.
        teximage_node = parent_node.create_linked('ShaderNodeTexImage', in_socket_id, out_socket_id='Color')
        teximage_node.set_property('image', bl_image)
        teximage_node.set_property('extension', self._mi_wrap_mode_to_bl_extension(mi_texture.get('wrap_mode', 'repeat')))
        teximage_node.set_property('interpolation', self._mi_filter_type_to_bl_interpolation(mi_texture.get('filter_type', 'bilinear')))
        self.write_mi_transform2d_property(mi_texture, 'to_uv', teximage_node, 'Vector')
        
    _float_texture_writers = {
        'bitmap': write_mi_float_bitmap
    }

    def write_mi_float_texture(self, mi_texture, parent_node, in_socket_id, default=None):
        mi_texture_type = mi_texture.plugin_name()
        if mi_texture_type not in self._float_texture_writers:
            self.mi_context.log(f'Mitsuba Texture type "{mi_texture_type}" is not supported.', 'ERROR')
            return
        self._float_texture_writers[mi_texture_type](self, mi_texture, parent_node, in_socket_id, default)

    def write_mi_float_srgb_reflectance_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        reflectance = mi_spectra_utils.convert_mi_srgb_reflectance_spectrum(mi_obj, default)
        parent_node.set_property(in_socket_id, mi_spectra_utils.linear_rgb_to_luminance(reflectance))

    _float_spectrum_writers = {
        'SRGBReflectanceSpectrum': write_mi_float_srgb_reflectance_spectrum
    }

    def write_mi_float_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        mi_obj_class_name = mi_obj.class_().name()
        if mi_obj_class_name not in self._float_spectrum_writers:
            self.mi_context.log(f'Mitsuba object type "{mi_obj_class_name}" is not supported.', 'ERROR')
            return
        self._float_spectrum_writers[mi_obj_class_name](self, mi_obj, parent_node, in_socket_id, default)

    def write_mi_float_value(self, value, parent_node, in_socket_id, transformation=None):
        if transformation is not None:
            value = transformation(value)
        parent_node.set_property(in_socket_id, value)

    def write_mi_rgb_bitmap(self, mi_texture, parent_node, in_socket_id, default=None):
        mi_texture_id = mi_texture.id()
        bl_image = self.mi_context.get_bl_image(mi_texture_id)
        if bl_image is None:
            # If the image is not in the cache, load it from disk.
            # This can happen if we have a texture inside of a BSDF that is itself into a
            # twosided BSDF.
            bl_image = textures.mi_texture_to_bl_image(self.mi_context, mi_texture)
            if bl_image is None:
                parent_node.set_property(in_socket_id, material.rgb_to_rgba(default))
                return
            self.mi_context.register_bl_image(mi_texture_id, bl_image)

        # FIXME: Support texture coordinate mapping
        teximage_node = parent_node.create_linked('ShaderNodeTexImage', in_socket_id, out_socket_id='Color')
        teximage_node.set_property('image', bl_image)
        teximage_node.set_property('extension', self._mi_wrap_mode_to_bl_extension(mi_texture.get('wrap_mode', 'repeat')))
        teximage_node.set_property('interpolation', self._mi_filter_type_to_bl_interpolation(mi_texture.get('filter_type', 'bilinear')))
        self.write_mi_transform2d_property(mi_texture, 'to_uv', teximage_node, 'Vector')

    _rgb_texture_writers = {
        'bitmap': write_mi_rgb_bitmap
    }

    def write_mi_rgb_texture(self, mi_texture, parent_node, in_socket_id, default=None):
        mi_texture_type = mi_texture.plugin_name()
        if mi_texture_type not in self._rgb_texture_writers:
            self.mi_context.log(f'Mitsuba Texture type "{mi_texture_type}" is not supported.', 'ERROR')
            return
        self._rgb_texture_writers[mi_texture_type](self, mi_texture, parent_node, in_socket_id, default)

    def write_mi_rgb_srgb_reflectance_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        reflectance = mi_spectra_utils.convert_mi_srgb_reflectance_spectrum(mi_obj, default)
        parent_node.set_property(in_socket_id, material.rgb_to_rgba(reflectance))

    _rgb_spectrum_writers = {
        'SRGBReflectanceSpectrum': write_mi_rgb_srgb_reflectance_spectrum
    }

    def write_mi_rgb_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        mi_obj_class_name = mi_obj.class_().name()
        if mi_obj_class_name not in self._rgb_spectrum_writers:
            self.mi_context.log(f'Mitsuba object type "{mi_obj_class_name}" is not supported.', 'ERROR')
            return
        self._rgb_spectrum_writers[mi_obj_class_name](self, mi_obj, parent_node, in_socket_id, default)

    def write_mi_rgb_value(self, value, parent_node, in_socket_id):
        parent_node.set_property(in_socket_id, material.rgb_to_rgba(value))

    def write_mi_transform2d_property(self, mi_props, mi_prop_name, parent_node, in_socket_id):
        # TODO: Implement me
        pass

#########################
##  Mitsuba Converter  ##
#########################

class MitsubaMaterialConverter(MaterialConverter):
    '''
    Material converter for custom Mitsuba node tree
    '''
    def __init__(self, mi_context):
        super().__init__(mi_context)

    def _write_mi_ior_property(self, mi_mat, mi_prop_name, parent_node, in_socket_id, default: str=None):
        ior_enum_attr = f'{in_socket_id}_enum'
        ior_value_attr = f'{in_socket_id}_value'
        from mitsuba import Properties
        if mi_mat.has_property(mi_prop_name):
            mi_prop_type = mi_mat.type(mi_prop_name)
            if mi_prop_type == Properties.Type.Float:
                parent_node.set_property(ior_value_attr, float(mi_mat.get(mi_prop_name)))
            elif mi_prop_type == Properties.Type.String:
                parent_node.set_property(ior_enum_attr, str(mi_mat.get(mi_prop_name)))
            else:
                self.mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to float.', 'ERROR')
        elif default is not None:
            parent_node.set_property(ior_enum_attr, default)
        else:
            self.mi_context.log(f'Material "{mi_mat.id()}" does not have property "{mi_prop_name}".', 'ERROR')

    def _write_mi_eta_property(self, mi_mat, mi_prop_name, parent_node, in_socket_id, default: str=None):
        eta_enum_attr = f'{in_socket_id}_enum'
        eta_value_attr = f'{in_socket_id}_value'
        if mi_mat.has_property(mi_prop_name):
            self._write_mi_ior_property(mi_mat, mi_prop_name, parent_node, in_socket_id, default)
        elif mi_mat.has_property('specular'):
            specular = mi_mat.get('specular')
            eta = 2 / (1 - math.sqrt(0.08 * specular)) - 1
            parent_node.set_property(eta_value_attr, eta)
        elif default is not None:
            parent_node.set_property(eta_enum_attr, default)
        else:
            self.mi_context.log(f'Invalid eta/specular property in material "{mi_mat.id()}".', 'ERROR')

    def _write_mi_roughness_property(self, mi_mat, node):
        node.set_property('distribution', mi_mat.get('distribution', 'beckmann'))
        node.set_property('sample_visible', mi_mat.get('sample_visible', True))
        if mi_mat.has_property('alpha_u') or mi_mat.has_property('alpha_v'):
            node.set_property('anisotropic', True)
            self.write_mi_float_property(mi_mat, 'alpha_u', node, 'Alpha U', default=0.1)
            self.write_mi_float_property(mi_mat, 'alpha_v', node, 'Alpha V', default=0.1)
        else:
            if hasattr(node, 'anisotropic'):
                node.set_property('anisotropic', False)
            self.write_mi_float_property(mi_mat, 'alpha', node, 'Alpha', default=0.1)

    def _write_mi_conductor_property(self, mi_mat, node):
        material_prop = mi_mat.get('material', 'none')
        node.set_property('conductor_enum', material_prop)
        if material_prop == 'none':
            self.write_mi_float_property(mi_mat, 'eta', node, 'Eta', default=0.0)
            self.write_mi_float_property(mi_mat, 'k', node, 'K', default=1.0)
        elif mi_mat.has_property('eta') or mi_mat.has_property('k'):
            self.context.log(f'Conductor material "{mi_mat.id()}" specifies (eta, k) and material. Ignoring (eta, k).', 'WARN')

    def write_error_material(self, parent_node, in_socket_id):
        diffuse_node = parent_node.create_linked('MitsubaNodeDiffuseBSDF', in_socket_id)
        diffuse_node.set_property('Reflectance', [1.0, 0.0, 0.3])

    def write_mi_material(self, mi_mat, parent_node, in_socket_id, is_within_twosided=False):
        if not self.write_generic_bsdf(mi_mat, parent_node, in_socket_id):
            self.write_error_material(parent_node, in_socket_id)
            return False

    def write_mi_null_bsdf(self, mi_mat, parent_node, in_socket_id):
        parent_node.create_linked('MitsubaNodeNullBSDF', in_socket_id)
        return True

    def write_mi_principled_bsdf(self, mi_mat, parent_node, in_socket_id):
        principled_node = parent_node.create_linked('MitsubaNodePrincipledBSDF', in_socket_id)
        self._write_mi_eta_property(mi_mat, 'eta', principled_node, 'eta', 'bk7')
        self.write_mi_rgb_property(mi_mat, 'base_color', principled_node, 'Base Color', [0.5, 0.5, 0.5])
        self.write_mi_float_property(mi_mat, 'roughness', principled_node, 'Roughness', 0.5)
        self.write_mi_float_property(mi_mat, 'anisotropic', principled_node, 'Anisotropic', 0.0)
        self.write_mi_float_property(mi_mat, 'metallic', principled_node, 'Metallic', 0.0)
        self.write_mi_float_property(mi_mat, 'spec_trans', principled_node, 'Specular Transmission', 0.0)
        self.write_mi_float_property(mi_mat, 'spec_tint', principled_node, 'Specular Tint', 0.0)
        self.write_mi_float_property(mi_mat, 'sheen', principled_node, 'Sheen', 0.0)
        self.write_mi_float_property(mi_mat, 'sheen_tint', principled_node, 'Sheen Tint', 0.0)
        self.write_mi_float_property(mi_mat, 'flatness', principled_node, 'Flatness', 0.0)
        self.write_mi_float_property(mi_mat, 'clearcoat', principled_node, 'Clearcoat', 0.0)
        self.write_mi_float_property(mi_mat, 'clearcoat_gloss', principled_node, 'Clearcoat Gloss', 0.0)
        return True

    def write_mi_diffuse_bsdf(self, mi_mat, parent_node, in_socket_id):
        diffuse_node = parent_node.create_linked('MitsubaNodeDiffuseBSDF', in_socket_id)
        self.write_mi_rgb_property(mi_mat, 'reflectance', diffuse_node, 'Reflectance', [0.5, 0.5, 0.5])
        return True

    def write_mi_twosided_bsdf(self, mi_mat, parent_node, in_socket_id):
        twosided_node = parent_node.create_linked('MitsubaNodeTwosidedBSDF', in_socket_id)
        mi_child_materials = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        mi_child_material_count = len(mi_child_materials)
        if mi_child_material_count == 1:
            self.write_mi_material(mi_child_materials[0], twosided_node, 'BSDF', is_within_twosided=True)
        elif mi_child_material_count == 2:
            self.write_mi_material(mi_child_materials[0], twosided_node, 'BSDF', is_within_twosided=True)
            self.write_mi_material(mi_child_materials[1], twosided_node, 'BSDF_001', is_within_twosided=True)
        else:
            self.mi_context.log(f'Mitsuba twosided material "{mi_mat.id()}" has {mi_child_material_count} child material(s). Expected 1 or 2.', 'ERROR')
            return False
        return True

    def write_mi_dielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        dielectric_node = parent_node.create_linked('MitsubaNodeDielectricBSDF', in_socket_id)
        self._write_mi_ior_property(mi_mat, 'int_ior', dielectric_node, 'int_ior', 'bk7')
        self._write_mi_ior_property(mi_mat, 'ext_ior', dielectric_node, 'ext_ior', 'bk7')
        self.write_mi_rgb_property(mi_mat, 'specular_reflectance', dielectric_node, 'Specular Reflectance', [1.0, 1.0, 1.0])
        self.write_mi_rgb_property(mi_mat, 'specular_transmittance', dielectric_node, 'Specular Transmittance', [1.0, 1.0, 1.0])
        return True

    def write_mi_roughdielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        rough_dielectric_node = parent_node.create_linked('MitsubaNodeRoughDielectricBSDF', in_socket_id)
        self._write_mi_ior_property(mi_mat, 'int_ior', rough_dielectric_node, 'int_ior', 'bk7')
        self._write_mi_ior_property(mi_mat, 'ext_ior', rough_dielectric_node, 'ext_ior', 'bk7')
        self._write_mi_roughness_property(mi_mat, rough_dielectric_node)
        self.write_mi_rgb_property(mi_mat, 'specular_reflectance', rough_dielectric_node, 'Specular Reflectance', [1.0, 1.0, 1.0])
        self.write_mi_rgb_property(mi_mat, 'specular_transmittance', rough_dielectric_node, 'Specular Transmittance', [1.0, 1.0, 1.0])
        return True

    def write_mi_thindielectric_bsdf(self, mi_mat, parent_node, in_socket_id):
        thin_dielectric_node = parent_node.create_linked('MitsubaNodeThinDielectricBSDF', in_socket_id)
        self._write_mi_ior_property(mi_mat, 'int_ior', thin_dielectric_node, 'int_ior', 'bk7')
        self._write_mi_ior_property(mi_mat, 'ext_ior', thin_dielectric_node, 'ext_ior', 'bk7')
        self.write_mi_rgb_property(mi_mat, 'specular_reflectance', thin_dielectric_node, 'Specular Reflectance', [1.0, 1.0, 1.0])
        self.write_mi_rgb_property(mi_mat, 'specular_transmittance', thin_dielectric_node, 'Specular Transmittance', [1.0, 1.0, 1.0])
        return True

    def write_mi_blendbsdf_bsdf(self, mi_mat, parent_node, in_socket_id):
        blend_node = parent_node.create_linked('MitsubaNodeBlendBSDF', in_socket_id)
        self.write_mi_float_property(mi_mat, 'weight', blend_node, 'Weight', default=0.5)
        # NOTE: We assume that the two BSDFs are ordered in the list of named references
        mi_child_mats = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        mi_child_mats_count = len(mi_child_mats)
        if mi_child_mats_count != 2:
            self.mi_context.log(f'Unexpected number of child BSDFs in blendbsdf. Expected 2 but got {mi_child_mats_count}.', 'ERROR')
            return False
        self.write_mi_material(mi_child_mats[0], blend_node, 'BSDF')
        self.write_mi_material(mi_child_mats[1], blend_node, 'BSDF_001')
        return True

    def write_mi_conductor_bsdf(self, mi_mat, parent_node, in_socket_id):
        conductor_node = parent_node.create_linked('MitsubaNodeConductorBSDF', in_socket_id)
        self._write_mi_conductor_property(mi_mat, conductor_node)
        self.write_mi_rgb_property(mi_mat, 'specular_reflectance', conductor_node, 'Specular Reflectance', [1.0, 1.0, 1.0])
        return True

    def write_mi_roughconductor_bsdf(self, mi_mat, parent_node, in_socket_id):
        rough_conductor_node = parent_node.create_linked('MitsubaNodeRoughConductorBSDF', in_socket_id)
        self._write_mi_conductor_property(mi_mat, rough_conductor_node)
        self._write_mi_roughness_property(mi_mat, rough_conductor_node)
        self.write_mi_rgb_property(mi_mat, 'specular_reflectance', rough_conductor_node, 'Specular Reflectance', [1.0, 1.0, 1.0])
        return True

    def write_mi_mask_bsdf(self, mi_mat, parent_node, in_socket_id):
        mask_node = parent_node.create_linked('MitsubaNodeMaskBSDF', in_socket_id)
        self.write_mi_float_property(mi_mat, 'opacity', mask_node, 'Opacity', default=0.5)
        mi_child_mats = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        mi_child_mats_count = len(mi_child_mats)
        if mi_child_mats_count != 1:
            self.mi_context.log(f'Unexpected number of child BSDFs in mask BSDF. Expected 1 but got {mi_child_mats_count}.', 'ERROR')
            return False
        self.write_mi_material(mi_child_mats[0], mask_node, 'BSDF')
        return True

    def write_mi_plastic_bsdf(self, mi_mat, parent_node, in_socket_id):
        plastic_node = parent_node.create_linked('MitsubaNodePlasticBSDF', in_socket_id)
        self.write_mi_rgb_property(mi_mat, 'diffuse_reflectance', plastic_node, 'Diffuse Reflectance', [0.5, 0.5, 0.5])
        plastic_node.set_property('nonlinear', mi_mat.get('nonlinear', False))
        self._write_mi_ior_property(mi_mat, 'int_ior', plastic_node, 'int_ior', default='polypropylene')
        self._write_mi_ior_property(mi_mat, 'ext_ior', plastic_node, 'ext_ior', default='air')
        self.write_mi_rgb_property(mi_mat, 'specular_reflectance', plastic_node, 'Specular Reflectance', [1.0, 1.0, 1.0])
        return True

    def write_mi_roughplastic_bsdf(self, mi_mat, parent_node, in_socket_id):
        rough_plastic_node = parent_node.create_linked('MitsubaNodeRoughPlasticBSDF', in_socket_id)
        self.write_mi_rgb_property(mi_mat, 'diffuse_reflectance', rough_plastic_node, 'Diffuse Reflectance', [0.5, 0.5, 0.5])
        rough_plastic_node.set_property('nonlinear', mi_mat.get('nonlinear', False))
        self._write_mi_ior_property(mi_mat, 'int_ior', rough_plastic_node, 'int_ior', default='polypropylene')
        self._write_mi_ior_property(mi_mat, 'ext_ior', rough_plastic_node, 'ext_ior', default='air')
        self.write_mi_rgb_property(mi_mat, 'specular_reflectance', rough_plastic_node, 'Specular Reflectance', [1.0, 1.0, 1.0])
        self._write_mi_roughness_property(mi_mat, rough_plastic_node)
        return True

    def write_mi_bumpmap_bsdf(self, mi_mat, parent_node, in_socket_id):
        bump_node = parent_node.create_linked('MitsubaNodeBumpMapBSDF', in_socket_id)
        bump_node.set_property('scale', mi_mat.get('scale', 1.0))

        mi_bump_textures = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'Texture')
        assert len(mi_bump_textures) == 1
        self.write_mi_float_texture(mi_bump_textures[0], bump_node, 'Bump Height', default=0.0)

        mi_child_mats = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        assert len(mi_child_mats) == 1
        self.write_mi_material(mi_child_mats[0], bump_node, 'BSDF')

        return True

    def write_mi_normalmap_bsdf(self, mi_mat, parent_node, in_socket_id):
        normalmap_node = parent_node.create_linked('MitsubaNodeNormalMapBSDF', in_socket_id)
        
        mi_normalmap_textures = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'Texture')
        assert len(mi_normalmap_textures) == 1
        self.write_mi_rgb_bitmap(mi_normalmap_textures[0], normalmap_node, 'Normal Map')

        mi_child_mats = mi_props_utils.named_references_with_class(self.mi_context, mi_mat, 'BSDF')
        assert len(mi_child_mats) == 1
        self.write_mi_material(mi_child_mats[0], normalmap_node, 'BSDF')

        return True

    def write_mi_float_bitmap(self, mi_texture, parent_node, in_socket_id, default=None):
        # FIXME: We forcibly disable sRGB conversion for float textures.
        #        This should probably be done elsewhere.
        mi_texture['raw'] = True
        self.write_mi_rgb_bitmap(mi_texture, parent_node, in_socket_id, default)

    def write_mi_float_checkerboard(self, mi_texture, parent_node, in_socket_id, default=None):
        self.write_mi_rgb_checkerboard(mi_texture, parent_node, in_socket_id, default)

    _float_texture_writers = {
        'bitmap': write_mi_float_bitmap,
        'checkerboard': write_mi_float_checkerboard,
    }

    def write_mi_float_texture(self, mi_texture, parent_node, in_socket_id, default=None):
        mi_texture_type = mi_texture.plugin_name()
        if mi_texture_type not in self._float_texture_writers:
            self.mi_context.log(f'Mitsuba Texture type "{mi_texture_type}" is not supported.', 'ERROR')
            return
        self._float_texture_writers[mi_texture_type](self, mi_texture, parent_node, in_socket_id, default)

    def write_mi_float_srgb_reflectance_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        reflectance = mi_spectra_utils.convert_mi_srgb_reflectance_spectrum(mi_obj, default)
        parent_node.set_property(in_socket_id, mi_spectra_utils.linear_rgb_to_luminance(reflectance))

    _float_spectrum_writers = {
        'SRGBReflectanceSpectrum': write_mi_float_srgb_reflectance_spectrum
    }

    def write_mi_float_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        mi_obj_class_name = mi_obj.class_().name()
        if mi_obj_class_name not in self._float_spectrum_writers:
            self.mi_context.log(f'Mitsuba object type "{mi_obj_class_name}" is not supported.', 'ERROR')
            return
        self._float_spectrum_writers[mi_obj_class_name](self, mi_obj, parent_node, in_socket_id, default)

    def write_mi_float_value(self, value, parent_node, in_socket_id, transformation=None):
        if transformation is not None:
            value = transformation(value)
        parent_node.set_property(in_socket_id, value)

    def write_mi_rgb_bitmap(self, mi_texture, parent_node, in_socket_id, default=None):
        mi_texture_id = mi_texture.id()
        bl_image = self.mi_context.get_bl_image(mi_texture_id)
        if bl_image is None:
            # If the image is not in the cache, load it from disk.
            # This can happen if we have a texture inside of a BSDF that is itself into a
            # twosided BSDF.
            bl_image = textures.mi_texture_to_bl_image(self.mi_context, mi_texture)
            if bl_image is None:
                parent_node.set_property(in_socket_id, default)
                return
            self.mi_context.register_bl_image(mi_texture_id, bl_image)

        bitmap_node = parent_node.create_linked('MitsubaNodeBitmapTexture', in_socket_id, out_socket_id='Color')
        bitmap_node.set_property('image', bl_image)
        bitmap_node.set_property('filter_type', mi_texture.get('filter_type', 'bilinear'))
        bitmap_node.set_property('wrap_mode', mi_texture.get('wrap_mode', 'repeat'))
        bitmap_node.set_property('raw', mi_texture.get('raw', False))
        self.write_mi_transform2d_property(mi_texture, 'to_uv', bitmap_node, 'Transform')

    def write_mi_rgb_checkerboard(self, mi_texture, parent_node, in_socket_id, default=None):
        checkerboard_node = parent_node.create_linked('MitsubaNodeCheckerboardTexture', in_socket_id, out_socket_id='Color')
        self.write_mi_rgb_property(mi_texture, 'color0', checkerboard_node, 'Color 0', [0.4, 0.4, 0.4])
        self.write_mi_rgb_property(mi_texture, 'color1', checkerboard_node, 'Color 1', [0.2, 0.2, 0.2])
        self.write_mi_transform2d_property(mi_texture, 'to_uv', checkerboard_node, 'Transform')

    _rgb_texture_writers = {
        'bitmap': write_mi_rgb_bitmap,
        'checkerboard': write_mi_rgb_checkerboard,
    }

    def write_mi_rgb_texture(self, mi_texture, parent_node, in_socket_id, default=None):
        mi_texture_type = mi_texture.plugin_name()
        if mi_texture_type not in self._rgb_texture_writers:
            self.mi_context.log(f'Mitsuba Texture type "{mi_texture_type}" is not supported.', 'ERROR')
            return
        self._rgb_texture_writers[mi_texture_type](self, mi_texture, parent_node, in_socket_id, default)

    def write_mi_rgb_srgb_reflectance_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        reflectance = mi_spectra_utils.convert_mi_srgb_reflectance_spectrum(mi_obj, default)
        parent_node.set_property(in_socket_id, reflectance)

    _rgb_spectrum_writers = {
        'SRGBReflectanceSpectrum': write_mi_rgb_srgb_reflectance_spectrum
    }

    def write_mi_rgb_spectrum(self, mi_obj, parent_node, in_socket_id, default=None):
        mi_obj_class_name = mi_obj.class_().name()
        if mi_obj_class_name not in self._rgb_spectrum_writers:
            self.mi_context.log(f'Mitsuba object type "{mi_obj_class_name}" is not supported.', 'ERROR')
            return
        self._rgb_spectrum_writers[mi_obj_class_name](self, mi_obj, parent_node, in_socket_id, default)

    def write_mi_rgb_value(self, value, parent_node, in_socket_id):
        parent_node.set_property(in_socket_id, value)

    def write_mi_transform2d_property(self, mi_props, mi_prop_name, parent_node, in_socket_id):
        if mi_props.has_property(mi_prop_name):
            transform = mi_props.get(mi_prop_name)
            translation, rotation, scale = math_utils.decompose_transform_2d(transform)
            transform_node = parent_node.create_linked('MitsubaNode2DTransform', in_socket_id, out_socket_id='Transform')
            transform_node.set_property('translate_x', translation[0])
            transform_node.set_property('translate_y', translation[1])
            transform_node.set_property('rotate', rotation)
            transform_node.set_property('scale_x', scale[0])
            transform_node.set_property('scale_y', scale[1])

######################
##   Main import    ##
######################

def mi_material_to_bl_cycles_material(mi_context, bl_mat, mi_mat, mi_emitter=None):
    ''' Convert a Mitsuba material to a Cycles shader node tree.
    This is experimental and is not guaranteed to produce a perfect result.
    '''
    bl_converter = BlenderMaterialConverter(mi_context)
    bl_node_tree = nodetree.NodeTreeWrapper.init_cycles_material(bl_mat)
    bl_node_tree.clear()
    output_node = bl_node_tree.create_node('ShaderNodeOutputMaterial')
    in_socket_id = 'Surface'

    # If the material is emissive, write the emission shader
    if mi_emitter is not None:
        old_output_node = output_node
        output_node, in_socket_id = bl_converter.write_mi_emitter_bsdf(output_node, in_socket_id, mi_emitter)

    # Write the Mitsuba material to the surface output
    bl_converter.write_mi_material(mi_mat, output_node, in_socket_id)

    # Restore the old material wrapper for formatting
    if mi_emitter is not None:
        output_node = old_output_node

    # Format the shader node graph
    bl_node_tree.prettify()

def mi_material_to_bl_mitsuba_material(mi_context, bl_mat, mi_mat, mi_emitter=None):
    ''' Convert a Mitsuba material to a custom Mitsuba shader node tree '''
    mi_converter = MitsubaMaterialConverter(mi_context)
    mi_node_tree = nodetree.NodeTreeWrapper.init_mitsuba_material(bl_mat)
    mi_node_tree.clear()
    output_node = mi_node_tree.create_node('MitsubaNodeOutputMaterial')
    in_socket_id = 'BSDF'

    mi_converter.write_mi_material(mi_mat, output_node, in_socket_id)

    mi_node_tree.prettify()

def mi_material_to_bl_material(mi_context, mi_mat, mi_emitter=None):
    ''' Create a Blender node tree representing a given Mitsuba material
    
    Params
    ------
    mi_context : Mitsuba import context
    mi_mat : Mitsuba material properties
    mi_emitter : Optional, Mitsuba area emitter properties

    Returns
    -------
    The newly created Blender material
    '''
    # Check that the emitter is of the correct type
    assert mi_emitter is None or mi_emitter.plugin_name() == 'area'

    bl_mat = bpy.data.materials.new(name=mi_mat.id())
    
    mi_material_to_bl_mitsuba_material(mi_context, bl_mat, mi_mat, mi_emitter)

    # Convert to Cycles if requested
    if mi_context.with_cycles_nodes:
        mi_material_to_bl_cycles_material(mi_context, bl_mat, mi_mat, mi_emitter)

    return bl_mat
