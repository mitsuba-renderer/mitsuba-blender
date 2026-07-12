import bpy

from . import export_context
from . import materials
from . import camera
from ...convert.export import lights, mesh, world

class SceneConverter:
    '''
    Converts a blender scene to a Mitsuba-compatible dict.
    Either save it as an XML or load it as a scene.
    '''
    def __init__(self, render=False):
        self.export_ctx = export_context.ExportContext()
        self.export_ctx.render = render
        self.render = render

    def scene_to_dict(self, depsgraph, window_manager=None, use_selection=False, ignore_background=True):
        """
        Convert a Blender scene to a Mitsuba-compatible dict.

        Parameters
        ----------

        depsgraph : bpy.types.Depsgraph
            The evaluated dependency graph of the scene to export.
        window_manager : bpy.types.WindowManager, optional
            The window manager to update the progress bar. No progress is
            reported when omitted.
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
            integrator = b_scene.mitsuba.integrator_to_dict()
        else:
            integrator = {
                'type':'path',
                'max_depth': b_scene.cycles.max_bounces
            }
        self.export_ctx.data_add(integrator)

        world.export_world(self.export_ctx, b_scene.world, ignore_background)

        geometry = mesh.GeometryExporter(self.export_ctx)

        # First pass: cameras, lights, and a count of how often each mesh
        # data occurs (repeated data becomes a shapegroup with instances)
        progress_counter = 0
        for object_instance in depsgraph.object_instances:
            if window_manager is not None:
                window_manager.progress_update(progress_counter)
            progress_counter += 1

            if self._skip_instance(object_instance, use_selection):
                continue

            evaluated_obj = object_instance.object
            object_type = evaluated_obj.type
            if object_type in {'MESH', 'FONT', 'SURFACE', 'META'}:
                geometry.count_instance(object_instance)
            elif object_type == 'CAMERA':
                # When rendering inside blender, export only the active camera
                if (self.render and evaluated_obj.name_full == b_scene.camera.name_full) or not self.render:
                    camera.export_camera(object_instance, b_scene, self.export_ctx)
            elif object_type == 'LIGHT':
                lights.export_light(self.export_ctx, object_instance)
            else:
                self.export_ctx.log("Object: %s of type '%s' is not supported!" % (evaluated_obj.name_full, object_type), 'WARN')

        # Second pass: convert the geometry. Evaluated objects may not be
        # kept alive across iteration steps, so each one is converted while
        # the iterator points at it.
        for object_instance in depsgraph.object_instances:
            if self._skip_instance(object_instance, use_selection, log=False):
                continue
            if object_instance.object.type in {'MESH', 'FONT', 'SURFACE', 'META'}:
                geometry.export_instance(object_instance)

    def _skip_instance(self, object_instance, use_selection, log=True):
        if use_selection:
            #skip if it's not selected or if it's an instance and the parent object is not selected
            if not object_instance.is_instance and not object_instance.object.original.select_get():
                return True
            if (object_instance.is_instance and object_instance.object.parent
                and not object_instance.object.parent.original.select_get()):
                return True

        evaluated_obj = object_instance.object
        if evaluated_obj.hide_render or (object_instance.is_instance
            and evaluated_obj.parent and evaluated_obj.parent.original.hide_render):
            #ignore it since we don't want it rendered (TODO: hide_viewport)
            if log:
                self.export_ctx.log("Object: {} is hidden for render. Ignoring it.".format(evaluated_obj.name), 'INFO')
            return True
        return False

    def dict_to_xml(self, filename):
        import mitsuba as mi
        config = mi.parser.ParserConfig(mi.variant())
        state = mi.parser.parse_dict(config, self.export_ctx.scene_data)
        # Reorder the plugins so they are written in a legible order
        mi.parser.transform_reorder(config, state)
        # The exporter already placed meshes and textures in subfolders of the
        # output directory, matching the relative references in the dict.
        mi.parser.write_file(state, filename, True)

    def dict_to_scene(self):
        import mitsuba as mi
        # Resolve relative file references against the export directory
        fr = mi.file_resolver()
        paths = list(fr)
        fr.prepend(self.export_ctx.directory)
        try:
            return mi.load_dict(self.export_ctx.scene_data)
        finally:
            fr.clear()
            for path in paths:
                fr.append(path)
