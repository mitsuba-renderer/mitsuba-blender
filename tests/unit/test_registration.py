"""Enable/disable/enable cycles of the extension must not leak state."""

import bpy
import pytest


def _blender_render_panels_with_mitsuba():
    return [panel.__name__ for panel in bpy.types.Panel.__subclasses__()
            if 'BLENDER_RENDER' in getattr(panel, 'COMPAT_ENGINES', ())
            and 'MITSUBA' in panel.COMPAT_ENGINES]


def test_enable_disable_enable(mi_addon, fresh_scene):
    scene = fresh_scene

    assert bpy.ops.preferences.addon_disable(module=mi_addon) == {'FINISHED'}

    # Everything must be unregistered
    assert 'mitsuba' not in bpy.types.Scene.bl_rna.properties
    assert 'mitsuba' not in bpy.types.Camera.bl_rna.properties
    for class_name in ('MitsubaRenderSettings', 'MitsubaCameraSettings',
                       'MITSUBA_RENDER_PT_integrator', 'MITSUBA_CAMERA_PT_sampler',
                       'MITSUBA_CAMERA_PT_rfilter'):
        assert getattr(bpy.types, class_name, None) is None, \
            f'{class_name} leaked through addon_disable'
    assert _blender_render_panels_with_mitsuba() == []
    with pytest.raises(TypeError):
        scene.render.engine = 'MITSUBA'

    assert bpy.ops.preferences.addon_enable(module=mi_addon) == {'FINISHED'}

    # And everything must be back
    scene.render.engine = 'MITSUBA'
    assert scene.mitsuba.active_integrator == 'path'
    assert scene.camera.data.mitsuba.active_sampler == 'independent'
    assert len(_blender_render_panels_with_mitsuba()) > 0
    assert getattr(bpy.types, 'MITSUBA_RENDER_PT_integrator', None) is not None
