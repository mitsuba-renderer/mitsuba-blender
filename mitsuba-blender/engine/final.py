import bpy
import time, math
from mathutils import Matrix, Vector

import tempfile
import os
import numpy as np

from gpu_extras.presets import draw_texture_2d

from ..io.exporter import SceneConverter
from ..io.exporter.geometry  import convert_mesh
from ..io.exporter.materials import b_material_to_dict
from ..io.exporter.lights    import convert_point_light, convert_area_light, convert_sun_light, convert_spot_light

class MitsubaRenderEngine(bpy.types.RenderEngine):
    bl_idname = "MITSUBA"
    bl_label = "Mitsuba"
    bl_use_preview = False
    bl_use_shading_nodes_custom = False

    # Init is called whenever a new render engine instance is created. Multiple
    # instances may exist at the same time, for example for a viewport and final
    # render.
    def __init__(self):
        self.viewport_engine = ViewportMitsubaEngine(self)

    # When the render engine instance is destroy, this is called. Clean up any
    # render engine data here, for example stopping running render threads.
    def __del__(self):
        pass

    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        from mitsuba import set_variant
        b_scene = depsgraph.scene
        set_variant(b_scene.mitsuba.variant)

        converter = SceneConverter(render=True)

        from mitsuba import ScopedSetThreadEnvironment, Thread
        with ScopedSetThreadEnvironment(b_scene.thread_env):
            scale = b_scene.render.resolution_percentage / 100.0
            self.size_x = int(b_scene.render.resolution_x * scale)
            self.size_y = int(b_scene.render.resolution_y * scale)

            # Temporary workaround as long as the dict creation writes stuff to dict
            with tempfile.TemporaryDirectory() as dummy_dir:
                filepath = os.path.join(dummy_dir, "scene.xml")
                converter.set_path(filepath)
                converter.scene_to_dict(depsgraph)
                Thread.thread().file_resolver().prepend(dummy_dir)
                mts_scene = converter.dict_to_scene()

            sensor = mts_scene.sensors()[0]
            mts_scene.integrator().render(mts_scene, sensor)
            render_results = sensor.film().bitmap().split()

            for result in render_results:
                buf_name = result[0].replace("<root>", "Main")
                channel_count = result[1].channel_count() if result[1].channel_count() != 2 else 3

                self.add_pass(buf_name, channel_count, ''.join([f.name.split('.')[-1] for f in result[1].struct_()]))

            blender_result = self.begin_result(0, 0, self.size_x, self.size_y)

            for result in render_results:
                render_pixels = np.array(result[1])
                if result[1].channel_count() == 2:
                    # Add a dummy third channel
                    render_pixels = np.dstack((render_pixels, np.zeros((*render_pixels.shape[:2], 1))))
                #render_pixels = np.array(render.convert(Bitmap.PixelFormat.RGBA, Struct.Type.Float32, srgb_gamma=False))
                # Here we write the pixel values to the RenderResult
                buf_name = result[0].replace("<root>", "Main")
                layer = blender_result.layers[0].passes[buf_name]
                layer.rect = np.flip(render_pixels, 0).reshape((self.size_x*self.size_y, -1))
            self.end_result(blender_result)

    # For viewport renders, this method gets called once at the start and
    # whenever the scene or 3D viewport changes. This method is where data
    # should be read from Blender in the same thread. Typically a render
    # thread will be started to do the work while keeping Blender responsive.
    def view_update(self, context, depsgraph):
        if context.scene.mitsuba.viewport_disabled:
            return

        import mitsuba as mi
        mi.set_variant(depsgraph.scene.mitsuba.variant)
        self.viewport_engine.update_scene(context, depsgraph)

    # For viewport renders, this method is called whenever Blender redraws
    # the 3D viewport. The renderer is expected to quickly draw the render
    # with OpenGL, and not perform other expensive work.
    def view_draw(self, context, depsgraph):
        if context.scene.mitsuba.viewport_disabled:
            return

        import mitsuba as mi
        mi.set_variant(depsgraph.scene.mitsuba.variant)
        self.viewport_engine.update_pixel_buffer(context, depsgraph)
        self.viewport_engine.draw_pixels(context, depsgraph)

# ------------------------------------------------------------------------------

class ViewportMitsubaEngine:
    def __init__(self, renderer) -> None:
        import mitsuba as mi
        self.renderer = renderer
        self.dimensions = mi.ScalarVector2i(1, 1)
        self.pixels = None
        self.converter = SceneConverter(render=True)
        self.draw_type = ''
        self.mts_scene = None
        self.integrator = None
        self.sensor = None
        self.sensor_dict = { }
        self.films = {}
        self.preview_scale_factor = 1.0
        self.spp = 1

    def update_pixel_buffer(self, context, depsgraph):
        import drjit as dr
        import mitsuba as mi
        import gpu

        if self.mts_scene is None:
            self.reload_scene(depsgraph, reason='initialize renderer')

        self.reload_integrator(context)

        # Still want to re-render when scene parameters changed (e.g. viewport max spp)
        # if self.draw_type in 'update_overlay':
        #     print(f'viewport update: {self.draw_type}')
        #     self.draw_type = 'nothing'
        #     self.need_redraw = False # Request a redraw
        #     return

        r3d = None
        for a in bpy.data.window_managers[0].windows[0].screen.areas:
            if a.type == "VIEW_3D":
                r3d = a.spaces[0].region_3d
                break

        # Check if view matrix was modified
        sensor_dict = self.reload_sensor_dict(r3d)
        if self.sensor_dict != sensor_dict:
            self.draw_type = 'update_camera'

        if self.draw_type == 'nothing':
            print(f'viewport update: {self.draw_type}')
            self.need_redraw = False # Request a redraw
            return

        # Initialize spp count when not in progressive mode
        if self.draw_type != 'progressive':
            self.spp = 1

        # If not in preview, disable preview scale factor
        if self.draw_type == 'progressive':
            self.preview_scale_factor = 1.0

        scale_factor = self.preview_scale_factor
        dimensions = mi.ScalarVector2i(
            int(context.region.width  * scale_factor),
            int(context.region.height * scale_factor)
        )

        # Check if viewport dimensions were modified
        if dr.any(self.dimensions != dimensions) or dimensions not in self.films:
            if dimensions not in self.films:
                self.films[tuple(dimensions)] = mi.load_dict({
                    'type': 'hdrfilm',
                    'rfilter': { 'type': 'box' },
                    'width': dimensions[0], 'height': dimensions[1],
                    'pixel_format': 'rgba',
                }, parallel=False)
            self.dimensions = dimensions
            self.draw_type = 'update_camera'

        # Reload scene if necessary
        if self.sensor is None or self.draw_type in 'update_camera':
            self.sensor_dict = dict(sensor_dict)
            sensor_dict['film'] = self.films[tuple(dimensions)]
            self.sensor = mi.load_dict(sensor_dict, parallel=False)

        # print('    draw_type:', self.draw_type)

        # dr.sync_thread()
        start = time.time()

        # Render new images
        img = mi.render(self.mts_scene, sensor=self.sensor, integrator=self.integrator, spp=self.spp)

        # Override alpha channel to match Cycles
        img[:, :, 3] = 1.0

        # Update status on viewport
        max_spp = int(context.scene.mitsuba.viewport_max_spp)
        self.renderer.update_stats('Mitsuba', f'{self.spp} / {max_spp} samples')

        # Update pixel buffer
        if self.draw_type == 'progressive':
            self.img = (self.img + img) / 2
        else:
            self.img = img

        # TODO should draw directly into the buffer, instead to going through CPU with numpy
        self.pixels = gpu.types.Buffer('FLOAT', dimensions[0] * dimensions[1] * 4, np.array(self.img))

        render_time = float(time.time() - start) * 1000

        if self.spp == 1:
            if render_time > 500:
                self.preview_scale_factor = 1.0 / 32.0
            if render_time > 240:
                self.preview_scale_factor = 1.0 / 8.0
            elif render_time > 80:
                self.preview_scale_factor = 1.0 / 4.0
            else:
                self.preview_scale_factor = 1.0

        # Switch to progressive rendering and update SPP count
        if self.spp < max_spp:
            self.spp *= 2
            self.draw_type = 'progressive'
            self.need_redraw = True # Request a redraw
        else:
            self.draw_type = 'nothing'
            self.need_redraw = False # Request a redraw

    def draw_pixels(self, context, depsgraph):
        import gpu

        # Read viewport engine parameters
        scale_factor = float(self.dimensions[0] / context.region.width)

        # Bind shader that converts from scene linear to display space,
        gpu.state.blend_set('ALPHA_PREMULT')
        self.renderer.bind_display_space_shader(depsgraph.scene)

        texture = gpu.types.GPUTexture((self.dimensions[0], self.dimensions[1]), format='RGBA16F', data=self.pixels)
        draw_texture_2d(texture, (0, 0), int(texture.width / scale_factor), int(texture.height / scale_factor))

        self.renderer.unbind_display_space_shader()
        gpu.state.blend_set('NONE')

        if self.need_redraw:
            self.renderer.tag_redraw()

    def update_scene(self, context, depsgraph):
        import mitsuba as mi

        # Case 1: initialize the scene on the first update
        if self.mts_scene is None:
            print('view_update: initialize scene')
            self.reload_scene(depsgraph, reason='initialize scene')
            return

        if self.variant != mi.variant():
            print('view_update: initialize scene (variant changed)')
            self.sensor = None
            self.integrator = None
            self.films = {}
            self.reload_scene(depsgraph, reason='initialize scene (variant changed)')
            return

        print(f'view_update: {len(depsgraph.updates)}')

        if len(depsgraph.updates) == 0:
            self.draw_type = 'nothing'
            return

        if depsgraph.updates[0].id.name == 'Scene': # TODO check if it is a scene
            # Case 2: Only overlay was updated, no need to re-render
            if len(depsgraph.updates) == 1:
                self.draw_type = 'update_overlay'
                return

            # Case 3: Add / remove objects or materials, reload the scene!
            print('view_update: update scene')
            self.reload_scene(depsgraph, reason='add/remove objects')
            return

        try:
            # Case 4: Some materials have changed
            if depsgraph.id_type_updated('MATERIAL'):
                names = [update.id.name_full for update in depsgraph.updates]
                obj_name = names[0]
                mat_name = names[2]

                print(f"Update material --> {obj_name} - {mat_name}")

                obj_key = self.converter.ctx.key_mapping[obj_name]

                for instance in depsgraph.object_instances:
                    if instance.object.name_full == obj_name:
                        b_object = instance.object
                        if b_object.type == 'MESH':
                            b_mesh = b_object.data
                        else: # Metaballs, text, surfaces
                            b_mesh = b_object.to_mesh()

                        b_mat = b_mesh.materials[mat_name]

                        mat_params = b_material_to_dict(self.converter.ctx, b_mat)

                        area_params = None
                        if isinstance(mat_params, list):
                            mat_params, area_params = mat_params

                        def flatten_dict(d, prefix=''):
                            result = {}
                            for k, v in d.items():
                                if isinstance(v, dict):
                                    result.update(flatten_dict(v, prefix + k + '.'))
                                else:
                                    result[prefix + k] = v
                            return result

                        for k, v in flatten_dict(mat_params).items():
                            if isinstance(v, str):
                                continue
                            key = f'{obj_key}.bsdf.{k}'
                            if not key in self.params:
                                key += '.value'
                            self.params[key] = v

                        if area_params is not None:
                            for k, v in flatten_dict(area_params).items():
                                if isinstance(v, str):
                                    continue
                                key = f'{obj_key}.area.{k}'
                                if not key in self.params:
                                    key += '.value'
                                self.params[key] = v

                        # Case 4: Update all parameters of the material
                        self.params.update()
                        self.draw_type = 'update_material'
                return

            # Test which datablocks changed
            for update in depsgraph.updates:
                name = update.id.name_full
                print("    datablock updated: ", name, update.id.id_type)

                for instance in depsgraph.object_instances:
                    if instance.object.name_full == name:
                        b_object = instance.object

                        # Case 5: User moved an object around!
                        if update.is_updated_geometry or update.is_updated_transform:
                            if not name in self.converter.ctx.key_mapping:
                                print('unknown geometry! update scene')
                                self.reload_scene(depsgraph, reason='unknown geometry')
                                return

                            id = self.converter.ctx.key_mapping[name]

                            if b_object.type == 'LIGHT':
                                # Case 5.1: An emitter was moved
                                print("--> update light: ", name)
                                if b_object.data.type == 'POINT':
                                    l_params = convert_point_light(b_object, self.converter.ctx)
                                    if update.is_updated_transform:
                                        self.params[f'{id}.position'] = l_params['position']
                                    else:
                                        self.params[f'{id}.intensity'] = l_params['intensity']
                                elif b_object.data.type == 'AREA':
                                    l_params = convert_area_light(b_object, self.converter.ctx)
                                    if update.is_updated_transform:
                                        if b_object.data.shape in ['SQUARE', 'RECTANGLE']:
                                            transform = l_params['to_world'] @ mi.ScalarTransform4f().scale(-1.0) # Rectangle face is flipped
                                            self.params[f'{id}.to_world'] = transform
                                        else:
                                            raise Exception(f'Not supported light.data.type: {b_object.data.shape}')
                                    else:
                                        self.params[f'{id}.emitter.radiance'] = l_params['emitter']['radiance']
                                elif b_object.data.type == 'SUN':
                                    l_params = convert_sun_light(b_object, self.converter.ctx)
                                    if update.is_updated_transform:
                                        self.params[f'{id}.to_world'] = l_params['to_world']
                                    else:
                                        self.params[f'{id}.irradiance'] = l_params['irradiance']
                                elif b_object.data.type == 'SPOT':
                                    l_params = convert_spot_light(b_object, self.converter.ctx)
                                    if update.is_updated_transform:
                                        self.params[f'{id}.to_world'] = l_params['to_world']
                                    else:
                                        self.params[f'{id}.intensity']    = l_params['intensity']
                                        self.params[f'{id}.cutoff_angle'] = l_params['cutoff_angle']
                                        self.params[f'{id}.beam_width']   = l_params['beam_width']
                                else:
                                    raise Exception(f'Not supported light.data.type: {b_object.data.type}')
                                self.draw_type = 'update_light'
                                self.params.update()
                                return
                            elif b_object.type in {'MESH', 'FONT', 'SURFACE', 'META'}:
                                # Case 5.2: An object was moved!
                                print("--> update geometry: ", update.id.name)

                                if b_object.type == 'MESH':
                                    b_mesh = b_object.data
                                else: # Metaballs, text, surfaces
                                    b_mesh = b_object.to_mesh()

                                is_instance_emitter = b_object.parent is not None and b_object.parent.is_instancer
                                is_instance = instance.is_instance

                                if is_instance or is_instance_emitter:
                                    transform = None
                                else:
                                    transform = b_object.matrix_world

                                mesh = convert_mesh(self.converter.ctx, b_mesh, transform, '', 0)
                                mesh_params = mi.traverse(mesh)

                                self.params[f'{id}.faces'] = mesh_params['faces']
                                self.params[f'{id}.vertex_positions'] = mesh_params['vertex_positions']
                                if mesh.has_vertex_normals():
                                    self.params[f'{id}.vertex_normals'] = mesh_params['vertex_normals']
                                else:
                                    self.params[f'{id}.vertex_normals'] = mi.Float()
                                self.params.update()
                                self.draw_type = 'update_geom'
                                return
                            elif b_object.type == 'update_CAMERA':
                                # Case 5.3: A camera was moved, do nothing
                                self.draw_type = 'update_camera'
                        elif update.is_updated_shading:
                            pass # Handled in other loop
                        else:
                            print('--> update other!', b_object.type)
        except Exception as e:
            # Case 6: Unknown case, reload the entire scene
            print(e)
            self.reload_scene(depsgraph, str(e))
            return

    def reload_scene(self, depsgraph, reason):
        import drjit as dr
        import mitsuba as mi
        print(f'RELOAD SCENE: {reason}')
        self.variant = mi.variant()
        self.renderer.update_stats('Mitsuba', f'Unknown update, reloading the entire scene! (reason={reason})') # TODO not being displayed!
        # Temporary workaround as long as the dict creation writes stuff to dict
        with tempfile.TemporaryDirectory() as dummy_dir:
            dr.sync_thread()
            filepath = os.path.join(dummy_dir, "scene.xml")
            del self.mts_scene, self.integrator
            self.mts_scene = None
            self.integrator = None
            self.converter.ctx.clear()
            self.converter.set_path(filepath)
            self.converter.scene_to_dict(depsgraph)
            mi.Thread.thread().file_resolver().prepend(dummy_dir)
            self.mts_scene = self.converter.load_scene()
            self.params = mi.traverse(self.mts_scene)
            self.draw_type = 'update_scene'

    def reload_integrator(self, context):
        import mitsuba as mi

        integrator_dict = getattr(context.scene.mitsuba.viewport_available_integrators, context.scene.mitsuba.viewport_active_integrator)
        integrator_dict = integrator_dict.to_dict()

        if self.integrator is None or self.integrator_dict != integrator_dict:
            self.integrator = mi.load_dict(integrator_dict, parallel=False)
            self.integrator_dict = integrator_dict

    def reload_sensor_dict(self, r3d):
        ctx = self.converter.ctx
        width, height = self.dimensions

        # from World space to Camera space
        view_mat = r3d.view_matrix

        if r3d.view_perspective == 'PERSP':
            focal_length = bpy.context.space_data.lens
            sensor_width = 36.0 * 2.0 # Value hardcoded in blender\intern\cycles\blender\camera.cpp
            fov = math.degrees(2.0 * np.arctan((0.5 * sensor_width / focal_length)))

            view_mat = view_mat.inverted()
            view_mat = view_mat @ Matrix.Diagonal([-1, -1, -1, 1]) # Convention that camera view dir is inverted
            to_world = ctx.transform_matrix(view_mat)

            sensor_dict = {
                'type': 'perspective',
                'to_world': to_world,
                'fov': fov,
                'fov_axis': 'x' if width >= height else 'y',
                'near_clip': bpy.context.space_data.clip_start,
                'far_clip':  bpy.context.space_data.clip_end,
            }
        elif r3d.view_perspective == 'ORTHO':
            to_world = view_mat.inverted()
            to_world = to_world @ Matrix.Diagonal([-1, -1, -1, 1]) # Convention that camera view dir is inverted
            scale = 0.6 * r3d.view_distance # TODO figure out how to compute that number
            to_world = to_world @ Matrix.Diagonal([scale, scale, scale, 1])
            to_world = ctx.transform_matrix(to_world)

            # TODO move camera back to avoid clipping
            # view_dir = (to_world.to_3x3() @ Vector([0, 0, 1])).normalized()
            # to_world = to_world @ Matrix.Translation(0.5 * r3d.view_distance * view_dir)

            sensor_dict = {
                'type': 'orthographic',
                'to_world': to_world,
                'near_clip': 0.001,
                'far_clip':  2.5 * bpy.context.space_data.clip_end,
            }
        else:
            b_camera = bpy.context.scene.camera

            # Extract fov
            if b_camera.data.sensor_fit == 'AUTO':
                fov_axis = 'x' if width >= height else 'y'
                fov = math.degrees(b_camera.data.angle_x)
            elif b_camera.data.sensor_fit == 'HORIZONTAL':
                fov_axis = 'x'
                fov = math.degrees(b_camera.data.angle_x)
            elif b_camera.data.sensor_fit == 'VERTICAL':
                fov_axis = 'y'
                fov = math.degrees(b_camera.data.angle_y)
            else:
                ctx.log(f'Unknown \'sensor_fit\' value when exporting camera: {b_camera.data.sensor_fit}', 'ERROR')

            to_world = b_camera.matrix_world
            to_world = to_world @ Matrix.Diagonal([-1, -1, -1, 1]) # Convention that camera view dir is inverted

            # Formula from cycles/blender/camera.cpp
            zoom = r3d.view_camera_zoom
            zoom = 4.0 / (1.41421 + zoom / 50.0)**2

            # TODO something is still off here! The zoom should also affect the FOV somehow!

            # Move the camera backward along the view direction to account for the zoom factor
            view_dir = (to_world.to_3x3() @ Vector([0, 0, 1])).normalized()
            dist = view_dir.dot(to_world.translation)
            to_world = Matrix.Translation(view_dir * (dist * (zoom - 1.0))) @ to_world
            to_world = ctx.transform_matrix(to_world)

            sensor_dict = { # TODO don't re-instantiate a sensor every time! Just update transform matrix
                'type': 'perspective',
                'to_world': to_world,
                'fov': fov,
                'fov_axis': fov_axis,
                'near_clip': b_camera.data.clip_start,
                'far_clip': b_camera.data.clip_end,
                'principal_point_offset_x':  b_camera.data.shift_x / width * max(width, height),
                'principal_point_offset_y': -b_camera.data.shift_y / height * max(width, height),
            }

        return sensor_dict
