import bpy

from .viewport import MitsubaViewportEngine
from .beauty import render_beauty

class MitsubaRenderEngine(bpy.types.RenderEngine):
    bl_idname = "Mitsuba"
    bl_label  = "Mitsuba"

    # Don't apply compositing on render results.
    bl_use_postprocess = False

    # Has something to do with tiled EXR render output, not sure about the details.
    bl_use_save_buffers = False

    # Hides Cycles node trees in the node editor.
    bl_use_shading_nodes_custom = False

    # Texture previews are disabled intentionally. It is faster and easier to let
    # Blender Internal render them.
    bl_use_texture_preview = False

    # Use Eevee nodes in look dev ("MATERIAL") shading mode in the viewport.
    bl_use_eevee_viewport = False

    def __init__(self):
        self.viewport = MitsubaViewportEngine(self)

    def render(self, depsgraph):
        '''
        This is the method called by Blender for both final renders (F12) and
        small preview for materials, world and lights.
        '''
        render_beauty(self, depsgraph)

    def view_update(self, context, depsgraph):
        '''
        For viewport renders, this method gets called once at the start and
        whenever the scene or 3D viewport changes. This method is where data
        should be read from Blender in the same thread. Typically a render
        thread will be started to do the work while keeping Blender responsive.
        '''
        if context.scene.mitsuba_engine.viewport_disabled:
            return

        self.viewport.update_scene(depsgraph)

    def view_draw(self, context, depsgraph):
        '''
        For viewport renders, this method is called whenever Blender redraws
        the 3D viewport. The renderer is expected to quickly draw the render
        with OpenGL, and not perform other expensive work.
        '''
        if context.scene.mitsuba_engine.viewport_disabled:
            return

        self.viewport.update_pixel_buffer(context, depsgraph)
        self.viewport.draw_pixels(context, depsgraph)
