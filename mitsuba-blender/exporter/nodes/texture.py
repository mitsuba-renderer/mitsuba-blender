from ... import logging
from . import next_node_upstream

import numpy as np

def export_texture_node(ctx, tex_node):
    # return { 'type': 'uniform', 'value': 1.0 }

    image = tex_node.image

    if '<UDIM>' in image.filepath_raw:
        from ..converter import ExportContext
        import mitsuba as mi

        params = { 'type': 'udim_texture' }

        assert len(image.tiles) == len(image.packed_files)

        for i, packed_file in enumerate(image.packed_files):
            if packed_file in ExportContext.IMAGES_CACHE:
                key, entry = ExportContext.IMAGES_CACHE[packed_file]
            else:
                key = 'bitmap'
                entry = mi.blender.packed_file_to_bitmap(packed_file.packed_file.as_pointer())

                try:
                    if entry.pixel_format() == mi.Bitmap.PixelFormat.MultiChannel:
                        entry = mi.Bitmap(np.array(entry))
                    entry = entry.convert(component_format=mi.Struct.Type.Float32)
                except Exception as e:
                    logging.warn(f'Couldn\'t export UDIM texture: {image.filepath_raw} -> {e}')
                    return { 'type': 'uniform', 'value': 1.0 }

                ExportContext.IMAGES_CACHE[packed_file] = (key, entry)

            params[f'texture_{i:02d}'] = {
                'type': 'bitmap',
                key: entry,
            }

        return params

    params = { 'type': 'bitmap' }

    # Get the relative path to the copied texture from the full path to the original texture
    key, entry = ctx.export_and_cache_texture(image, ctx.directory)
    params[key] = entry

    # UV Mapping
    if tex_node.inputs["Vector"].is_linked:
        vector_node = next_node_upstream(ctx, tex_node.inputs["Vector"])
        if vector_node.type != 'MAPPING':
            raise NotImplementedError("Node: %s is not supported. Only a mapping node is supported" % vector_node.bl_idname)
        coord_node = next_node_upstream(ctx, vector_node.inputs["Vector"])
        if not vector_node.inputs["Vector"].is_linked:
            raise NotImplementedError("The node %s should be linked with a Texture coordinate node." % vector_node.bl_idname)
        if coord_node.type == 'UVMAP':
            import mitsuba as mi
            rotation = mi.ScalarVector3f(list(vector_node.inputs["Rotation"].default_value))
            scale    = mi.ScalarVector3f(list(vector_node.inputs["Scale"].default_value))
            location = mi.ScalarVector3f(list(vector_node.inputs["Location"].default_value))

            params['to_uv'] = ctx.transform_uv(scale, rotation, location)

    if image.colorspace_settings.name in ['Non-Color', 'Raw', 'Linear']:
        #non color data, tell mitsuba not to apply gamma conversion to it
        params['raw'] = True
    elif image.colorspace_settings.name != 'sRGB':
        logging.warn("Mitsuba only supports sRGB textures for color data.")

    if ctx.texture_raw:
        params['raw'] = True

    return params
