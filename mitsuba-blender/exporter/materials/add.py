from ..nodes import *
from .common import *

def convert_add_materials_cycles(ctx, current_node, extra):
    if not current_node.inputs[0].is_linked or not current_node.inputs[1].is_linked:
        raise NotImplementedError("Add shader is not linked to two materials.")
    mat1 = next_node_upstream(ctx, current_node.inputs[0])
    mat2 = next_node_upstream(ctx, current_node.inputs[1])

    if current_node.outputs[0].links[0].to_node.type != 'OUTPUT_MATERIAL':
        raise NotImplementedError("Add Shader is supported only as the final node of the shader (right behind 'Material Output').")
    #TODO: we could support it better to an extent, but it creates lots of degenerate cases, some of which won't work. Is it really worth it?
    elif mat1.type != 'EMISSION' and mat2.type != 'EMISSION':
        #Two bsdfs, this is not supported
        raise NotImplementedError("Adding two BSDFs is not supported, consider using a mix shader instead.")
    elif mat1.type == 'EMISSION' and mat2.type == 'EMISSION':
        #weight radiances
        #only RGB values for emitter colors are supported for now, so we can do this. It may be broken if we allow textures or spectra in blender
        radiance1 = [float(f) for f in convert_emitter_materials_cycles(ctx, mat1, extra)['radiance']['value'].split(" ")]
        radiance2 = [float(f) for f in convert_emitter_materials_cycles(ctx, mat2, extra)['radiance']['value'].split(" ")]

        sum_radiance = [radiance1[i] + radiance2[i] for i in range(3)]
        params = {
            'type': 'area',
            'radiance': ctx.spectrum(sum_radiance),
        }
        return params
    else:
        # one emitter, one bsdf
        return [cycles_material_to_dict(ctx, mat1, extra),
                cycles_material_to_dict(ctx, mat2, extra)]
