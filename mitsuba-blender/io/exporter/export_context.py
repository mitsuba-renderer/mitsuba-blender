from collections import OrderedDict
import os
from shutil import copy2
from numpy import pi

from mathutils import Matrix

import bpy

texture_exts = {
    'BMP': '.bmp',
    'HDR': '.hdr',
    'JPEG': '.jpg',
    'JPEG2000': '.jpg',
    'PNG': '.png',
    'OPEN_EXR': '.exr',
    'OPEN_EXR_MULTILAYER': '.exr',
    'TARGA': '.tga',
    'TARGA_RAW': '.tga',
}

convert_format = {
    'CINEON': 'EXR',
    'DPX': 'EXR',
    'TIFF': 'PNG',
    'IRIS': 'PNG'
}

class ExportedMaterialsCache:
    '''
    Store a list of the exported materials, that have both a BSDF and an emitter
    We need it to add 2 refs to each shape using this material
    This is useless when a material is only one bsdf/emitter, so we won't add those.
    '''
    def __init__(self):
        self.mats = {} # the mixed materials (1 BSDF, 1 emitter)

    def add_material(self, mat_dict, mat_id):
        """
        Store a dict containing one ref to a bsdf and one emitter

        mat_dict: {'emitter':emitter_dict, 'bsdf': bsdf_id}
        mat_id: id of the blender material that encapsulates all these
        """
        self.mats[mat_id] = mat_dict

    def has_mat(self, mat_id):
        """
        Determine if the given material is in the cache or not
        """
        return mat_id in self.mats.keys()

class Files:
    MAIN = 0
    MATS = 1
    GEOM = 2
    EMIT = 3
    CAMS = 4
    #TODO: Volumes

class ExportContext:
    '''
    Export Context
    '''

    def __init__(self):
        self.scene_data = OrderedDict([('type','scene')])
        self.counter = 0 # Counter to create unique IDs.
        self.exported_mats = ExportedMaterialsCache()
        self.export_ids = False # Export Object IDs in the XML file
        self.bake_materials = False
        self.bake_res_x = 1024
        self.bake_res_y = 1024
        self.bake_mat_ids = False
        self.bake_again = True
        self.exported_ids = set()
        # All the args defined below are set in the Converter
        self.directory = ''
        self.axis_mat = Matrix() # Coordinate shift
        self.deg = None # Dependency graph
        self.subfolders = {
            'texture': 'textures',
            'emitter': 'textures',
            'shape': 'meshes',
            'spectrum': 'spectra'
                            }
        self.texture_id = 0


    def data_add(self, mts_dict, name=''):
        '''
        Function to add new elements to the scene dict.
        If a name is provided it will be used as the key of the element.
        Otherwise the Id of the element is used if it exists
        or a new key is generated incrementally.
        '''
        if mts_dict is None or not isinstance(mts_dict, dict) or len(mts_dict) == 0 or 'type' not in mts_dict:
            return False

        if not name:
            try:
                name = mts_dict['id']
                #remove the corresponding entry
                del mts_dict['id']

            except KeyError:
                name = 'elm__%i' % self.counter

        self.scene_data.update([(name, mts_dict)])
        self.counter += 1

        return True

    def data_get(self, name):
        return self.scene_data.get(name)

    def log(self, message, level='INFO'):
        '''
        Log something using mitsuba's logging API

        Params
        ------

        message: What to write
        level: Level of logging
        '''
        from mitsuba import Log, LogLevel
        log_level = {
            'DEBUG': LogLevel.Debug,
            'INFO': LogLevel.Info,
            'WARN': LogLevel.Warn,
            'ERROR': LogLevel.Error,
            'TRACE': LogLevel.Trace
            }
        if level not in log_level:
            raise ValueError("Invalid logging level '%s'!" % level)
        Log(log_level[level], message)

    def export_texture(self, image):
        """
        Return the path to a texture.
        Ensure the image is on disk and of a correct type

        image : The Blender Image object
        """
        # TODO: don't save packed images but convert them to a mitsuba texture, and let the XML writer save
        textures_folder = os.path.join(self.directory, self.subfolders['texture'])
        if image.file_format in convert_format:
            msg = "Image format of '%s' is not supported. Converting it to %s." % (image.name, convert_format[image.file_format])
            self.log(msg, 'WARN')
            image.file_format = convert_format[image.file_format]
        original_name = os.path.basename(image.filepath)
        if original_name != '' and image.name.startswith(original_name): # Try to remove extensions from names of packed files to avoid stuff like 'Image.png.001.png'
            base_name, _ = os.path.splitext(original_name)
            name = image.name.replace(original_name, base_name, 1) # Remove the extension
            name += texture_exts[image.file_format]
        else:
            name = "%s%s" % (image.name, texture_exts[image.file_format])
        target_path = os.path.join(textures_folder, name)
        if not os.path.isdir(textures_folder):
            os.makedirs(textures_folder)
        old_filepath = image.filepath
        image.filepath_raw = target_path
        image.save()
        image.filepath_raw = old_filepath
        return f"{self.subfolders['texture']}/{name}"

    def blackbody(self, value):
        param = {
            "type" : "blackbody",
            "temperature" : value
        }
        return param

    def spectrum(self, value, mode='rgb'):
        '''
        Given a spectrum value, format it for the scene dict.

        Params
        ------

        value: value of the spectrum: can be a list, a rgb triplet, a single number or a filename
        mode: rgb or spectrum, defaults to rgb
        '''
        spec = {}

        if isinstance(value, (float, int)):
            spec = {'value': value, 'type': mode}

        elif isinstance(value, (str)):
            spec = {'filename': value, 'type': 'spectrum'}

        else:
            value = list(value)
            if any(not isinstance(x, (float, int, tuple)) for x in value):
                raise ValueError("Unknown spectrum entry: %s" % value)
            if any(type(value[i]) != type(value[i+1]) for i in range(len(value)-1)):
                raise ValueError("Mixed types in spectrum entry %s" % value)
            totitems = len(value)
            if  (value[0], (float, int)):
                if totitems == 3 or totitems == 4:
                    spec = {
                        'type': 'rgb',
                        'value': value[:3]
                        }
                elif totitems == 1:
                    spec = {'value': value[0], 'type': mode}
                else:
                    raise ValueError('Expected spectrum items to be 1,3 or 4 got %d: %s' % (len(value), value))

            else:
                #wavelength list
                spec = {'value': value, 'type': 'spectrum'}

        if not spec:
            spec = {'value': 0.0, 'type': 'spectrum'}

        return spec

    def transform_matrix(self, matrix):
        '''
        Apply coordinate shift and convert to a mitsuba Transform 4f
        '''
        from mitsuba import ScalarTransform4f
        if len(matrix) == 4:
            mat = self.axis_mat @ matrix
        else: #3x3
            mat = matrix.to_4x4()
        return ScalarTransform4f(list([list(x) for x in mat]))
