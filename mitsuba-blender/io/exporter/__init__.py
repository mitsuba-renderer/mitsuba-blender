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
from .downgrade import convert

from ipdb import set_trace

class SceneConverter:
    '''
    Converts a blender scene to a Mitsuba-compatible dict.
    Either save it as an XML or load it as a scene.
    '''
    def __init__(self, render=False):
        self.export_ctx = export_context.ExportContext()
        self.use_selection = False # Only export selection
        self.ignore_background = True
        self.render = render

    def set_path(self, name, split_files=False):
        from mitsuba.python.xml import WriteXML
        # Ideally, this should only be created if we want to write a scene.
        # For now we need it to save meshes and packed textures.
        # TODO: get rid of all writing to disk when creating the dict
        if not self.render:
            self.xml_writer = WriteXML(name, self.export_ctx.subfolders,
                                       split_files=split_files)
        # Give the path to the export context, for saving meshes and files
        self.export_ctx.directory, _ = os.path.split(name)

    def scene_to_dict(self, depsgraph, window_manager=None):
        import mitsuba as mi
        print(f"mitsuba variant - {mi.variant()}")
        # Switch to object mode before exporting stuff, so everything is defined properly
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        #depsgraph = context.evaluated_depsgraph_get()
        self.export_ctx.deg = depsgraph

        b_scene = depsgraph.scene #TODO: what if there are multiple scenes?
        if b_scene.render.engine == 'MITSUBA':
            print("get dict for integrator")
            attr = getattr(b_scene.mitsuba.available_integrators,b_scene.mitsuba.active_integrator)
            integrator = attr.to_dict()
            print(integrator)
        else:
            integrator = {
                'type':'path',
                'max_depth': b_scene.cycles.max_bounces
            }
        self.export_ctx.data_add(integrator)

        materials.export_world(self.export_ctx, b_scene.world, self.ignore_background)

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
            if window_manager:
                window_manager.progress_update(progress_counter)
            progress_counter += 1

            if self.use_selection:
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

    def dict_to_xml(self):
        import mitsuba as mi
        print(f"mitsuba variant - {mi.variant()}")
        # print(self.export_ctx.scene_data)
        self.xml_writer.process(self.export_ctx.scene_data)

    def dict_to_scene(self):
        import mitsuba as mi
        print(f"mitsuba variant - {mi.variant()}")
        from mitsuba import load_dict
        print(self.export_ctx.scene_data)
        return load_dict(self.export_ctx.scene_data)
