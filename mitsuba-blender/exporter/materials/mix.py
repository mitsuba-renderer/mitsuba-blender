from ..nodes import *
from .common import *

def convert_mix_materials_cycles(ctx, current_node, extra): #TODO: test and fix this
    if not current_node.inputs[1].is_linked or not current_node.inputs[2].is_linked:
        raise NotImplementedError("Mix shader is not linked to two materials.")

    mat1 = next_node_upstream(ctx, current_node.inputs[1])
    mat2 = next_node_upstream(ctx, current_node.inputs[2])

    if mat1.type == 'EMISSION' and mat2.type == 'EMISSION':
        #weight radiances
        #only RGB values for emitter colors are supported for now, so we can do this. It may be broken if we allow textures or spectra in blender
        if current_node.inputs['Fac'].is_linked: # texture weight
            raise NotImplementedError("Only uniform weight is supported for mixing emitters.")
        radiance1 = [float(f) for f in convert_emitter_materials_cycles(ctx, mat1, extra)['radiance']['value'].split(" ")]
        radiance2 = [float(f) for f in convert_emitter_materials_cycles(ctx, mat2, extra)['radiance']['value'].split(" ")]
        w = current_node.inputs['Fac'].default_value
        weighted_radiance = [(1.0-w)*radiance1[i] + w*radiance2[i] for i in range(3)]
        params = {
            'type': 'area',
            'radiance': ctx.spectrum(weighted_radiance),
        }
        return params

    elif mat1.type != 'EMISSION' and mat2.type != 'EMISSION':
        fac_node = next_node_upstream(ctx, current_node.inputs['Fac'])

        # One-sided material created when importing Mitsuba scene
        if fac_node.type == 'NEW_GEOMETRY':
            if current_node.inputs['Fac'].links[0].from_socket.name == 'Backfacing':
                return {
                    'type': 'twosided',
                    'bsdf1': cycles_material_to_dict(ctx, mat1, extra),
                    'bsdf2': cycles_material_to_dict(ctx, mat2, extra),
                    'allow_transmission': True,
                }
            return cycles_material_to_dict(ctx, mat1, extra)

        return {
            'type': 'blendbsdf',
            'weight': convert_float_texture_node(ctx, current_node.inputs['Fac']),
            'bsdf1': cycles_material_to_dict(ctx, mat1, extra),
            'bsdf2': cycles_material_to_dict(ctx, mat2, extra)
        }
    else: # one bsdf, one emitter
        raise NotImplementedError("Mixing a BSDF and an emitter is not supported. Consider using an Add shader instead.")
