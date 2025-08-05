import bpy
import time, math
from mathutils import Matrix, Vector

import numpy as np

from gpu_extras.presets import draw_texture_2d

from ..                   import logging
from ..utils              import dotdict
from ..exporter.converter import SceneConverter
from ..exporter.geometry  import convert_mesh
from ..exporter.materials import b_material_to_dict
from ..exporter.lights    import convert_point_light, convert_area_light, convert_sun_light, convert_spot_light
from ..exporter.world     import convert_world

class Changes:
    '''
    Type of changes handled by the viewport renderer
    '''
    Nothing    = 0
    Config     = 1 << 0
    Camera     = 1 << 1
    Film       = 1 << 2
    Material   = 1 << 3
    Light      = 1 << 4
    World      = 1 << 4
    Geometry   = 1 << 5
    Integrator = 1 << 6
    Scene      = 1 << 7
    Variant    = 1 << 8
    Unknown    = 1 << 9

    RequireSceneReload = Scene | Variant | Unknown
    RequireIntegratorReload = Integrator | Config | RequireSceneReload

#-------------------------------------------------------------------------------

class State:
    '''
    Finite State Machine states for the progressive viewport renderer

        Preview:     Lower resolution rendering when the render time exceeds 80ms.
                     This is helpful for quick camera motion to move around the scene.

        Progressive: In this state, the renderer refines the rendered image by
                     accumulating more samples. As soon as a change occur, the
                     state is set back to Preview.

        Done:        This state indicate that we are done rendering and no
                     rendering should take place until the next changes.
    '''
    PREVIEW     = 0
    PROGRESSIVE = 1
    DONE        = 2

class ProgressiveRenderingFSM:
    '''
    Finite State Machine implementation
    '''
    def __init__(self, config):
        self.max_spp = int(config.max_spp)
        self.progressive_enabled = config.progressive
        self.preview_integrator = self.progressive_integrator = None
        self.last_render_time = 0.0
        self.preview_frame_count = 0
        self.seed = 0
        self.reset_state()

    def next_state(self, render_time):
        if not self.progressive_enabled:
            self.state = State.DONE
        else:
            if self.state == State.PREVIEW:
                # Only change res_scale if preview is still too slow!
                self.last_render_time = max(render_time, self.last_render_time)
                self.preview_frame_count += 1
                # Only switch to progressive mode after 4 frame of preview mode
                if self.preview_frame_count > 4:
                    self.state = State.PROGRESSIVE
                    self.res_scale = 1.0
            elif self.state == State.PROGRESSIVE:
                self.seed += 1
                self.last_render_time = render_time
                self.integrator = self.progressive_integrator
                PROGRESSIVE_TIMEOUT = 500.0
                if render_time > PROGRESSIVE_TIMEOUT:
                    self.state = State.DONE
                if self.spp_accum >= self.max_spp:
                    self.state = State.DONE
                else:
                    self.spp_accum += self.spp
                    # Try to avoid progressive rendering to get stuck rendering too many spp at once
                    if self.last_render_time < 100.0:
                        self.spp = self.spp * 2
                    self.spp = min(self.spp, self.max_spp - self.spp_accum)

    def reset_state(self):
        self.state = State.PREVIEW
        self.preview_frame_count = 0
        self.seed = 0
        self.integrator = self.preview_integrator
        self.spp = 1
        self.spp_accum = 0

        # We are trying to get 30ms per frame
        factor = min(int(self.last_render_time) // 30, 32)
        self.res_scale = 1.0 / max(factor, 1.0)

    def reload_integrator(self, d):
        import mitsuba as mi
        self.progressive_integrator = mi.load_dict(d)
        if 'max_depth' in d:
            preview_dict = dict(d)
            preview_dict['max_depth'] = 4
            self.preview_integrator = mi.load_dict(preview_dict)
        else:
            self.preview_integrator = self.progressive_integrator
        self.integrator = self.preview_integrator

#-------------------------------------------------------------------------------

class MitsubaViewportEngine:
    def __init__(self, renderer) -> None:
        import mitsuba as mi
        self.renderer = renderer
        self.pixels = None
        self.converter = SceneConverter(render=True, viewport=True)

        self.changes = Changes.Nothing
        self.fsm = None

        self.config = dotdict()
        self.integrator_dict = {}
        self.sensor_dict = {}
        self.dimensions = mi.ScalarVector2i(1, 1)

        self.mts_scene = None
        self.sensor = None
        self.films = {}

    def update_pixel_buffer(self, context, depsgraph):
        import drjit as dr
        import mitsuba as mi
        import gpu

        # ----------------------------------------------------------------------
        # Update scene and integrator if necessary

        # Update config
        settings = context.scene.mitsuba_engine
        config = dotdict()
        config.progressive  = settings.viewport_progressive
        config.max_spp      = settings.viewport_max_spp
        config.res_scale    = settings.viewport_res_scale

        if self.config != config:
            self.changes |= Changes.Config
            self.config = config

        if self.changes & Changes.Config:
            self.fsm = ProgressiveRenderingFSM(self.config)

        # Update scene
        if self.changes & Changes.RequireSceneReload:
            self.reload_scene(depsgraph)

        # Update integrator
        prev_integrator_dict = dict(self.integrator_dict)
        self.integrator_dict = getattr(
            context.scene.mitsuba_engine.viewport_available_integrators,
            context.scene.mitsuba_engine.viewport_active_integrator
        ).to_dict()

        if self.integrator_dict != prev_integrator_dict:
            self.changes |= Changes.Integrator

        if self.changes & Changes.RequireIntegratorReload:
            self.fsm.reload_integrator(self.integrator_dict)

        # Check if the viewport camera was updated
        if self.check_update_viewport_camera():
            self.changes |= Changes.Camera

        # At this point we should have found all possible changes. So we need
        # to check whether the viewport update is necessary.
        if self.changes == Changes.Nothing and self.fsm.state == State.DONE:
            self.need_redraw = False # Request a redraw
            return

        # If we found any changes, we need to reset the state of the state machine.
        if self.changes != Changes.Nothing:
            self.fsm.reset_state()

        # print(f'FSM[state={self.fsm.state}, spp={self.fsm.spp}, res_scale={self.fsm.res_scale}]')

        # ----------------------------------------------------------------------
        # Instantiate viewport camera and film if necessary

        scale_factor = float(self.config.res_scale) * self.fsm.res_scale
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
                })
            self.dimensions = dimensions
            self.changes |= Changes.Camera

        # Reload scene if necessary
        if self.changes & Changes.Camera:
            sensor_dict = dict(self.sensor_dict)
            sensor_dict['film'] = self.films[tuple(dimensions)]
            self.sensor = mi.load_dict(sensor_dict)

        # Reset changes
        self.changes = Changes.Nothing

        # ----------------------------------------------------------------------
        # Render viewport

        self.renderer.update_stats('Mitsuba', f'Rendering ...')

        # dr.sync_thread()
        start = time.time()

        # Render new images
        img = mi.render(self.mts_scene, sensor=self.sensor, integrator=self.fsm.integrator, spp=self.fsm.spp, seed=self.fsm.seed)

        # Override alpha channel to match Cycles
        img[:, :, 3] = 1.0

        # Update status on viewport
        max_spp = int(self.config.max_spp)
        self.renderer.update_stats('Mitsuba', f'{self.fsm.spp_accum} / {max_spp} samples' if self.fsm.state == State.PROGRESSIVE else 'Preview')

        # Update pixel buffer
        if self.fsm.state == State.PROGRESSIVE and (self.img.shape == img.shape):
            self.img = (self.img * self.fsm.spp_accum + img * self.fsm.spp) / (self.fsm.spp_accum + self.fsm.spp)
            self.fsm.spp_accum + self.fsm.spp
        else:
            self.img = img

        dr.eval(self.img)

        # TODO should draw directly into the buffer, instead to going through CPU with numpy
        self.pixels = gpu.types.Buffer('FLOAT', dimensions[0] * dimensions[1] * 4, np.array(self.img))

        render_time = float(time.time() - start) * 1000

        # ----------------------------------------------------------------------
        # Move to next FSM state

        self.fsm.next_state(render_time)
        self.need_redraw = self.fsm.state != State.DONE

        if not config.progressive:
            self.renderer.update_stats('Mitsuba', f'PREVIEW')
        else:
            if not self.need_redraw and self.fsm.spp_accum != max_spp:
                self.renderer.update_stats('Mitsuba', f'{self.fsm.spp_accum} / {max_spp} samples [time out]')

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

    def update_scene(self, depsgraph):
        import mitsuba as mi

        if mi.variant != depsgraph.scene.mitsuba_engine.variant:
            mi.set_variant(depsgraph.scene.mitsuba_engine.variant)

        # Case 1: initialize the scene on the first update
        if self.mts_scene is None:
            self.changes = Changes.Scene
            return

        # Case 2: variant of the renderer has changed
        if self.variant != mi.variant():
            self.films = {}
            self.changes = Changes.Variant | Changes.Film | Changes.Integrator
            return

        if len(depsgraph.updates) == 0:
            return

        if depsgraph.updates[0].id.name == 'Scene':
            if len(depsgraph.updates) == 1:
                # Overlay, config or integrator update, handled in the update_pixel_buffer method
                return
            else:
                # Case 3: Add / remove objects or materials, reload the scene!
                self.changes |= Changes.Scene
                return

        try:
            # Case 4: Some materials have changed
            if depsgraph.id_type_updated('MATERIAL'):
                names = [update.id.name_full for update in depsgraph.updates]
                obj_name = names[0]

                if obj_name == 'World':
                    emitter_dict = convert_world(self.converter.ctx, depsgraph.scene.world)

                    if emitter_dict is None:
                        self.changes |= Changes.Scene
                        return

                    emitter = mi.load_dict(emitter_dict)
                    emitter_params = mi.traverse(emitter)

                    # Here we assume that world emitter is always named 'elm__1'

                    if emitter_dict['type'] == 'constant':
                        self.params['elm__1.radiance.value'] = emitter_params['radiance.value']
                    elif emitter_dict['type'] == 'envmap':
                        self.params['elm__1.envmap.to_world'] = emitter_params['envmap.to_world']
                        self.params['elm__1.envmap.scale']    = emitter_params['envmap.scale']
                        self.params['elm__1.envmap.data']     = emitter_params['envmap.data']
                    else:
                        raise Exception(f"Unsupported world emitter: {emitter_dict['type']}")

                    self.changes |= Changes.World
                    self.params.update()
                    return

                mat_name = names[2]

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

                        self.changes |= Changes.Material
                return

            # Test which datablocks changed
            for update in depsgraph.updates:
                name = update.id.name_full
                for instance in depsgraph.object_instances:
                    if instance.object.name_full == name:
                        b_object = instance.object

                        # Case 5: User moved an object around!
                        if update.is_updated_geometry or update.is_updated_transform:
                            if not name in self.converter.ctx.key_mapping:
                                self.changes |= Changes.Unknown
                                continue

                            id = self.converter.ctx.key_mapping[name]

                            if b_object.type == 'CURVES':
                                self.changes |= Changes.Unknown
                                continue

                            if b_object.type == 'LIGHT':
                                # Case 5.1: An emitter was moved
                                if b_object.data.type == 'POINT':
                                    l_params = convert_point_light(b_object, self.converter.ctx)
                                    if update.is_updated_transform:
                                        self.params[f'{id}.position'] = l_params['position']
                                    else:
                                        if f'{id}.soft_falloff' in self.params:
                                            self.params[f'{id}.intensity']    = l_params['intensity']
                                            self.params[f'{id}.radius']       = l_params['radius']
                                            self.params[f'{id}.soft_falloff'] = l_params['soft_falloff']
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
                                self.changes |= Changes.Light
                                self.params.update()
                            elif b_object.type in {'MESH', 'FONT', 'SURFACE', 'META'}:
                                # Case 5.2: An object was moved!
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

                                mesh = mi.load_dict(convert_mesh(self.converter.ctx, b_mesh, transform, '', 0))
                                mesh_params = mi.traverse(mesh)

                                self.params[f'{id}.faces'] = mesh_params['faces']
                                self.params[f'{id}.vertex_positions'] = mesh_params['vertex_positions']
                                if mesh.has_vertex_normals():
                                    self.params[f'{id}.vertex_normals'] = mesh_params['vertex_normals']
                                else:
                                    self.params[f'{id}.vertex_normals'] = mi.Float()
                                self.params.update()
                                self.changes |= Changes.Geometry
                            elif b_object.type == 'update_CAMERA':
                                # Case 5.3: A camera was moved, do nothing
                                self.changes |= Changes.Camera
                        elif update.is_updated_shading:
                            pass # Handled in other loop
                        else:
                            pass # Update others
        except Exception as e:
            # Case 6: Unknown case, reload the entire scene
            self.changes |= Changes.Unknown
            return

    def reload_scene(self, depsgraph):
        import drjit as dr
        import mitsuba as mi

        reason = ''
        if self.changes & Changes.Variant:
            reason = 'variant update'
        elif self.changes & Changes.Scene:
            reason = 'add/remove geometry or material'
        elif self.changes & Changes.Unknown:
            reason = 'unknown update'

        self.renderer.update_stats('Mitsuba', f'Reloading scene in viewport engine: {reason}')

        self.variant = mi.variant()

        self.mts_scene = self.params = None
        del self.mts_scene, self.params

        # Temporary workaround as long as the dict creation writes stuff to dict
        dr.sync_thread()

        self.converter.ctx.clear()
        scene_dict = self.converter.scene_to_dict(depsgraph)
        mi.Thread.thread().file_resolver().prepend(SceneConverter.TEMP_DIR.name)

        self.mts_scene = mi.load_dict(scene_dict)
        self.params = mi.traverse(self.mts_scene)

    def check_update_viewport_camera(self):
        r3d = None
        for a in bpy.data.window_managers[0].windows[0].screen.areas:
            if a.type == "VIEW_3D":
                r3d = a.spaces[0].region_3d
                break

        ctx = self.converter.ctx
        width, height = self.dimensions

        # from World space to Camera space
        view_mat = r3d.view_matrix

        prev_sensor_dict = dict(self.sensor_dict)

        if r3d.view_perspective == 'PERSP':
            focal_length = bpy.context.space_data.lens
            sensor_width = 36.0 * 2.0 # Value hardcoded in blender\intern\cycles\blender\camera.cpp
            fov = math.degrees(2.0 * np.arctan((0.5 * sensor_width / focal_length)))

            view_mat = view_mat.inverted()
            view_mat = view_mat @ Matrix.Diagonal([-1, -1, -1, 1]) # Convention that camera view dir is inverted
            to_world = ctx.transform_matrix(view_mat)
            to_world = to_world

            self.sensor_dict = {
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
            to_world = to_world

            # TODO move camera back to avoid clipping
            # view_dir = (to_world.to_3x3() @ Vector([0, 0, 1])).normalized()
            # to_world = to_world @ Matrix.Translation(0.5 * r3d.view_distance * view_dir)

            self.sensor_dict = {
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
                logging.error(f'Unknown \'sensor_fit\' value when exporting camera: {b_camera.data.sensor_fit}')

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
            to_world = to_world

            self.sensor_dict = { # TODO don't re-instanciate a sensor everytime! Just update transform matrix
                'type': 'perspective',
                'to_world': to_world,
                'fov': fov,
                'fov_axis': fov_axis,
                'near_clip': b_camera.data.clip_start,
                'far_clip': b_camera.data.clip_end,
                'principal_point_offset_x':  b_camera.data.shift_x / width * max(width, height),
                'principal_point_offset_y': -b_camera.data.shift_y / height * max(width, height),
            }

        return self.sensor_dict != prev_sensor_dict
