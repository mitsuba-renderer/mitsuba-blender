import os

if "bpy" in locals():
    import importlib
    if "export_context" in locals():
        importlib.reload(export_context)
    if "materials" in locals():
        importlib.reload(materials)
    if "geometry" in locals():
        importlib.reload(geometry)
    if "lights" in locals():
        importlib.reload(lights)
    if "camera" in locals():
        importlib.reload(camera)

import bpy

from . import export_context
from . import materials
from . import geometry
from . import lights
from . import camera

class SceneConverter:
    '''
    Converts a blender scene to a Mitsuba-compatible dict.
    Either save it as an XML or load it as a scene.
    '''
    def __init__(self, render=False):
        self.export_ctx = export_context.ExportContext()
        self.render = render

    def scene_to_dict(self, depsgraph, window_manager, use_selection=False, ignore_background=True):
        """
        Convert a Blender scene to a Mitsuba-compatible dict.

        Parameters
        ----------

        depsgraph : bpy.types.Depsgraph
            The evaluated dependency graph of the scene to export.
        window_manager : bpy.types.WindowManager
            The window manager to update the progress bar.
        use_selection : bool, optional
            Only export selected objects. Defaults to False.
        ignore_background : bool, optional
            Ignore the default background in Blender's world settings. Defaults to True.
        """
        # Switch to object mode before exporting stuff, so everything is defined properly
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        #depsgraph = context.evaluated_depsgraph_get()
        self.export_ctx.deg = depsgraph

        b_scene = depsgraph.scene #TODO: what if there are multiple scenes?
        if b_scene.render.engine == 'MITSUBA':
            integrator = getattr(b_scene.mitsuba.available_integrators,b_scene.mitsuba.active_integrator).to_dict()
        else:
            integrator = {
                'type':'path',
                'max_depth': b_scene.cycles.max_bounces
            }
        self.export_ctx.data_add(integrator)

        materials.export_world(self.export_ctx, b_scene.world, ignore_background)

        # Establish list of particle objects
        particles = []
        for particle_sys in bpy.data.particles:
            if particle_sys.render_type == 'OBJECT':
                particles.append(particle_sys.instance_object.name)
            elif particle_sys.render_type == 'COLLECTION':
                for obj in particle_sys.instance_collection.objects:
                    particles.append(obj.name)

        progress_counter = 0
        # Main export loop
        for object_instance in depsgraph.object_instances:
            window_manager.progress_update(progress_counter)
            progress_counter += 1

            if use_selection:
                #skip if it's not selected or if it's an instance and the parent object is not selected
                if not object_instance.is_instance and not object_instance.object.original.select_get():
                    continue
                if (object_instance.is_instance and object_instance.object.parent
                    and not object_instance.object.parent.original.select_get()):
                    continue

            evaluated_obj = object_instance.object
            object_type = evaluated_obj.type
            #type: enum in [‘MESH’, ‘CURVE’, ‘SURFACE’, ‘META’, ‘FONT’, ‘ARMATURE’, ‘LATTICE’, ‘EMPTY’, ‘GPENCIL’, ‘CAMERA’, ‘LIGHT’, ‘SPEAKER’, ‘LIGHT_PROBE’], default ‘EMPTY’, (readonly)
            if evaluated_obj.hide_render or (object_instance.is_instance
                and evaluated_obj.parent and evaluated_obj.parent.original.hide_render):
                self.export_ctx.log("Object: {} is hidden for render. Ignoring it.".format(evaluated_obj.name), 'INFO')
                continue#ignore it since we don't want it rendered (TODO: hide_viewport)
            if object_type in {'MESH', 'FONT', 'SURFACE', 'META'}:
                geometry.export_object(object_instance, self.export_ctx, evaluated_obj.name in particles)
            elif object_type == 'CAMERA':
                # When rendering inside blender, export only the active camera
                if (self.render and evaluated_obj.name_full == b_scene.camera.name_full) or not self.render:
                    camera.export_camera(object_instance, b_scene, self.export_ctx)
            elif object_type == 'LIGHT':
                lights.export_light(object_instance, self.export_ctx)
            else:
                self.export_ctx.log("Object: %s of type '%s' is not supported!" % (evaluated_obj.name_full, object_type), 'WARN')

    def dict_to_xml(self, filename):
        import mitsuba as mi
        config = mi.parser.ParserConfig(mi.variant())
        state = mi.parser.parse_dict(config, self.export_ctx.scene_data)
        # Reorder the plugins so they are written in a legible order
        mi.parser.transform_reorder(config, state)
        # Place files in convenient subfolders (e.g. textures, meshes, etc.)
        output_dir = os.path.dirname(filename)
        mi.parser.transform_relocate(config, state, output_dir)
        mi.parser.write_file(state, filename, True)

    def dict_to_scene(self):
        from mitsuba import load_dict
        return load_dict(self.export_ctx.scene_data)
