import bpy

import os, time
import numpy as np

from contextlib import contextmanager
from collections import OrderedDict
import tempfile

from mathutils import Matrix

from . import materials
from . import geometry
from . import lights
from . import camera
from . import world
from .. import logging

class SceneConverter:
    '''
    Converts a blender scene to a Mitsuba-compatible dict.
    Either save it as an XML or load it as a scene.
    '''
    # Create a temporary directory for the scene conversion for exporting assets
    # when converting the scene for rendering within Blender (e.g. viewport)
    TEMP_DIR: str = tempfile.TemporaryDirectory()

    def __init__(self, render=False, viewport=False):
        self.ctx = ExportContext(render, viewport)
        self.render = render

        self.filename = os.path.join(SceneConverter.TEMP_DIR.name, 'scene.xml')
        self.ctx.directory = SceneConverter.TEMP_DIR.name

    def set_path(self, filename):
        self.filename = filename
        self.ctx.directory = os.path.dirname(filename)

    def scene_to_dict(self, depsgraph, window_manager=None):
        if not self.render:
            # Switch to object mode before exporting stuff, so everything is defined properly
            if bpy.ops.object.mode_set.poll():
                bpy.ops.object.mode_set(mode='OBJECT')

        self.ctx.b_scene = depsgraph.scene # TODO: what if there are multiple scenes?

        # ----------------------------------------------------------------------
        # Export integrator

        if self.ctx.b_scene.render.engine == 'Mitsuba':
            integrator = getattr(self.ctx.b_scene.mitsuba_engine.available_integrators, self.ctx.b_scene.mitsuba_engine.active_integrator)
            integrator = integrator.to_dict()
        else:
            integrator = {
                'type':'path',
                'max_depth': self.ctx.b_scene.cycles.max_bounces
            }
        self.ctx.add_object('integrator', integrator)

        # ----------------------------------------------------------------------
        # Export world

        world.export_world(self.ctx, self.ctx.b_scene.world)

        # ----------------------------------------------------------------------
        # Export materials

        # First export all materials in a multithreaded way
        for instance in depsgraph.object_instances:
            if self.ctx.use_selection:
                # Skip if it's not selected or if it's an instance and the parent object is not selected
                if not instance.is_instance and not instance.object.original.select_get():
                    continue
                if (instance.is_instance and instance.object.parent
                    and not instance.object.parent.original.select_get()):
                    continue

            obj = instance.object
            name_clean = bpy.path.clean_name(obj.name_full)
            name_clean = name_clean.replace('.', '_')
            object_id = f"mesh-{name_clean}"

            if obj.type in { 'MESH', 'FONT', 'SURFACE', 'META' }:
                if not object_id in self.ctx.scene_dict:
                    if obj.type == 'MESH':
                        b_mesh = obj.data
                    else: # Metaballs, text, surfaces
                        b_mesh = obj.to_mesh()

                    # Export all materials
                    for mat in b_mesh.materials:
                        materials.export_material(self.ctx, mat)

        # ----------------------------------------------------------------------
        # Export objects

        # Establish list of particle objects
        particles = []
        for particle_sys in bpy.data.particles:
            if particle_sys.render_type == 'OBJECT':
                particles.append(particle_sys.instance_object.name)
            elif particle_sys.render_type == 'COLLECTION':
                for obj in particle_sys.instance_collection.objects:
                    particles.append(obj.name)

        progress_counter = 0

        # Main export loop to export all scene elements
        for instance in depsgraph.object_instances:
            if window_manager:
                window_manager.progress_update(progress_counter)
                progress_counter += 1

            if self.ctx.use_selection:
                # Skip if it's not selected or if it's an instance and the parent object is not selected
                if not instance.is_instance and not instance.object.original.select_get():
                    continue
                if (instance.is_instance and instance.object.parent
                    and not instance.object.parent.original.select_get()):
                    continue

            obj = instance.object

            if obj.hide_render or (instance.is_instance and obj.parent and obj.parent.original.hide_render):
                logging.info("Object: {} is hidden for render. Ignoring it.".format(obj.name))
                continue # Ignore it since we don't want it rendered (TODO: hide_viewport)
            if obj.type in { 'MESH', 'FONT', 'SURFACE', 'META', 'POINTCLOUD' }:
                geometry.export_object(self.ctx, instance, instance.object.name in particles)
            elif obj.type == 'CAMERA':
                # When rendering inside blender, export only the active camera
                if (self.render and instance.object.name_full == self.ctx.b_scene.camera.name_full) or not self.render:
                    camera.export_camera(self.ctx, instance, self.ctx.b_scene)
            elif obj.type == 'LIGHT':
                lights.export_light(self.ctx, instance)
            elif obj.type == 'EMPTY':
                continue
            else:
                logging.warn("Object: %s of type '%s' is not supported!" % (obj.name_full, obj.type))

        return self.ctx.scene_dict

# ------------------------------------------------------------------------------

class ExportContext:
    '''
    Export context
    '''

    IMAGE_EXPORTER_THREAD = None
    IMAGES_CACHE: dict = {}

    SUBFOLDERS = {
        'texture':  'textures',
        'emitter':  'textures',
        'shape':    'meshes',
        'spectrum': 'spectra'
    }

    def __init__(self, render=False, viewport=False):
        self.mitsuba_engine = None
        self.render = render
        self.viewport = viewport
        self.b_scene = None

        self.clear()

    def clear(self):
        self.scene_dict    = OrderedDict([('type', 'scene')])
        self.exported_mats = {}
        self.key_mapping   = {}
        self.node_groups = []

        self.texture_unbounded_rgb = False
        self.texture_raw = False

        # Counter to create unique IDs.
        self.id_counter = 0

        # All the args defined below are set in the Converter
        self.directory = SceneConverter.TEMP_DIR.name
        self.axis_mat = Matrix() # Conversion matrix to shift the "Up" Vector

        self.use_selection = False
        self.export_ids = False # Export Object IDs in the XML file
        self.export_assets = not self.render
        self.export_default_background = True

    def sanatize_id(self, id):
        # In Mitsuba `.` are not supported in object's id as it's used in `mi.traverse`
        return id.replace('.', '_')

    def add_object(self, blender_id, obj_dict, id=None, force_export_id=False):
        '''
        Add object to the scene dictionary.
        '''
        if obj_dict is None or not isinstance(obj_dict, dict) or len(obj_dict) == 0 or 'type' not in obj_dict:
            logging.warn(f'strange invalid dict added to the scene: {blender_id} -> {obj_dict}')
            return False

        if id is None or (not self.export_ids and not force_export_id):
            if 'id' in obj_dict:
                id = obj_dict.pop('id')
            else:
                id = 'elm__%i' % self.id_counter
                self.id_counter += 1

        id = self.sanatize_id(id)

        self.key_mapping[blender_id] = id
        self.scene_dict.update([(id, obj_dict)])

    @staticmethod
    def export_and_cache_texture(image, directory, suffix=''):
        '''
        Return the path to a texture.
        Ensure the image is on disk and of a correct type

        image : The Blender Image object
        '''
        import mitsuba as mi

        texture_exts = {
            'BMP':                 '.bmp',
            'HDR':                 '.hdr',
            'JPEG':                '.jpg',
            'JPEG2000':            '.jpg',
            'PNG':                 '.png',
            'OPEN_EXR':            '.exr',
            'OPEN_EXR_MULTILAYER': '.exr',
            'TARGA':               '.tga',
            'TARGA_RAW':           '.tga',
        }

        convert_format = {
            'CINEON': 'EXR',
            'DPX':    'EXR',
            'TIFF':   'PNG',
            'IRIS':   'PNG'
        }

        if image in ExportContext.IMAGES_CACHE:
            return ExportContext.IMAGES_CACHE[image]

        start = time.time()
        # print(f'  exporting texture {image.filepath} ...', end='\r')

        if directory == SceneConverter.TEMP_DIR and image.type == 'IMAGE' and image.source == 'FILE':
            key = 'bitmap'
            if image.packed_file and image.packed_file.size > 0:
                entry = mi.blender.packed_file_to_bitmap(image.packed_file.as_pointer())
            else:
                entry = mi.Bitmap(image.filepath_raw)
        else:
            key = 'filename'
            # TODO: don't save packed images but convert them to a mitsuba texture, and let the XML writer save
            textures_folder = os.path.join(directory, ExportContext.SUBFOLDERS['texture'])
            os.makedirs(textures_folder, exist_ok=True)

            file_format = image.file_format
            if file_format in convert_format:
                logging.warn(f"Image format of '{image.name}' is not supported. Converting it to {convert_format[file_format]}.")
                file_format = convert_format[file_format]
            original_name = os.path.basename(image.filepath)
            if original_name != '' and image.name.startswith(original_name): # Try to remove extensions from names of packed files to avoid stuff like 'Image.png.001.png'
                base_name, _ = os.path.splitext(original_name)
                name = image.name.replace(original_name, base_name, 1) # Remove the extension
                name += texture_exts[file_format]
            else:
                name = "%s%s" % (image.name, texture_exts[file_format])
            name = os.path.splitext(name)[0] + suffix + os.path.splitext(name)[1]
            target_path = os.path.join(textures_folder, name)

            if file_format != image.file_format:
                data = np.array(image.pixels).reshape((image.size[0], image.size[1], image.channels))
                data = np.flip(data, axis=0)
                bmp = mi.Bitmap(data)
                bmp.set_srgb_gamma(True)
                if file_format == 'PNG':
                    bmp = bmp.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, True)
                bmp.write(target_path)
            else:
                image.save(filepath=target_path)

            entry = target_path

        # print(f'  exporting texture {image.filepath}: done in {time.time() - start} seconds')

        ExportContext.IMAGES_CACHE[image] = (key, entry)

        return ExportContext.IMAGES_CACHE[image]

    def spectrum(self, value, mode='rgb'):
        '''
        Given a spectrum value, format it for the scene dict.

        value: value of the spectrum: can be a list, a rgb triplet, a single number or a filename
        mode: rgb or spectrum, defaults to rgb
        '''
        spec = {}

        if isinstance(value, (float, int)):
            spec = { 'type': mode, 'value': value }
        elif isinstance(value, (str)):
            spec = { 'type': 'spectrum', 'filename': value }
        else:
            value = list(value)
            if any(not isinstance(x, (float, int, tuple)) for x in value):
                raise ValueError("Unknown spectrum entry: %s" % value)
            if any(type(value[i]) != type(value[i+1]) for i in range(len(value)-1)):
                raise ValueError("Mixed types in spectrum entry %s" % value)
            totitems = len(value)
            if isinstance(value[0], (float, int)):
                if totitems == 3 or totitems == 4:
                    spec = { 'type': 'rgb', 'value': value[:3] }
                elif totitems == 1:
                    spec = { 'type': mode, 'value': value[0] }
                else:
                    raise ValueError('Expected spectrum items to be 1, 3 or 4 got %d: %s' % (len(value), value))
            else:
                # Wavelength list
                spec = { 'type': 'spectrum', 'value': value }

        if not spec:
            spec = { 'type': 'spectrum', 'value': 0.0 }

        if self.texture_unbounded_rgb and spec['type'] == 'rgb':
            spec = {
                'type': 'srgb',
                'color': spec['value'],
                'unbounded': True,
            }

        return spec

    @contextmanager
    def scope_unbounded_texture_input(self):
        '''
        Scope within which rgb spectrum will be set as unbounded
        '''
        try:
            self.texture_unbounded_rgb = True
            yield
        except Exception:
            raise
        finally:
            self.texture_unbounded_rgb = False

    @contextmanager
    def scope_raw_texture_input(self):
        '''
        Scope within which Bitmap texture will be set as raw
        '''
        try:
            self.texture_raw = True
            yield
        except Exception:
            raise
        finally:
            self.texture_raw = False

    def transform_matrix(self, matrix):
        '''
        Apply coordinate shift and convert to a mitsuba Transform 4f
        '''
        import mitsuba as mi
        if len(matrix) == 4:
            mat = self.axis_mat @ matrix
        else: #3x3
            mat = matrix.to_4x4()

        mat = list([list(x) for x in mat])

        return mi.ScalarTransform4f(mi.ScalarMatrix4f(mat))

    def transform_uv(self, scale, rotation, location):
        '''
        Apply coordinate shift and convert to a mitsuba Transform 4f
        '''
        import mitsuba as mi
        mat = mi.ScalarTransform4f().scale(scale) \
                                    .rotate([1, 0, 0], rotation[0]) \
                                    .rotate([0, 1 ,0], rotation[1]) \
                                    .rotate([0, 0, 1], rotation[2]) \
                                    .translate(location)
        return mat
        # return list([list(x) for x in mat.matrix])

