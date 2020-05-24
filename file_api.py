from collections import OrderedDict
import os
from shutil import copy2
from numpy import pi
from mathutils import Matrix

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
    Store a set of exported textures
    Store a list of the exported materials, that have both a BSDF and an emitter
    We need it to add 2 refs to each shape using this material
    This is useless when a material is only one bsdf/emitter, so we won't add those.
    '''
    def __init__(self):
        self.mats = {} # the mixed materials (1 BSDF, 1 emitter)
        self.textures = {} # {tex_path:tex_id}
        self.tex_count = 0 # counter to give a unique name to each texture

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

    def get_tex_id(self, image, path):
        """
        If the texture is already in the dict, return its unique name.
        If not, save it, add it and return its unique name.
        """
        key = image.as_pointer()
        try:
            return self.textures[key]
        except KeyError:
            if image.file_format in convert_format.keys():
                msg = "Image format of '%s' is not supported. Converting it to %s." % (image.name, convert_format[image.file_format])
                FileExportContext.log(msg, 'WARN')
                image.file_format = convert_format[image.file_format]

            name = "tex-%d%s" % (self.tex_count, texture_exts[image.file_format])
            self.tex_count += 1
            self.textures[key] = name

            target_path = os.path.join(path, name)
            if image.packed_file: # File is packed in the blend file
                old_filepath = image.filepath
                image.filepath = target_path
                image.save()
                image.filepath = old_filepath
            else: # File is stored.we prefer this to avoid "no image data" errors when saving
                copy2(image.filepath_from_user(), target_path)
            FileExportContext.log("Saved image '%s' as '%s'." % (image.name, name), 'INFO')
            return name


class Files:
    MAIN = 0
    MATS = 1
    GEOM = 2
    EMIT = 3
    CAMS = 4
    #TODO: Volumes

class FileExportContext:
    '''
    File API
    '''

    def __init__(self):
        self.scene_data = OrderedDict([('type','scene')])
        self.counter = 0 #counter to create unique IDs.
        self.exported_mats = ExportedMaterialsCache()
        self.exported_ids = set()
        self.directory = ''
        self.axis_mat = Matrix()#overwritten in main export method

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
                name = '__elm__%i' % self.counter

        self.scene_data.update([(name, mts_dict)])
        self.counter += 1

        return True

    def data_get(self, name):
        return self.scene_data.get(name)

    def set_filename(self, name, split_files=False):
        from mitsuba.python.xml import WriteXML
        self.xml_writer = WriteXML(name, split_files)
        self.directory = self.xml_writer.directory

    def write(self):
        self.xml_writer.process(self.scene_data)

    @staticmethod
    def log(message, level='INFO'):
        '''
        Log something using mitsuba's logging API

        Params
        ------

        message: What to write
        level: Level of logging
        '''
        from mitsuba.core import Log, LogLevel
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
        Copy a texture file to the Mitsuba scene folder.
        Create the subfolder the first time this method is called

        tex_path : the full path to the texture
        """
        if not os.path.isdir(self.xml_writer.textures_folder):
            os.mkdir(self.xml_writer.textures_folder)

        img_name = self.exported_mats.get_tex_id(image, self.xml_writer.textures_folder)
        return os.path.join(self.xml_writer.textures_folder, img_name)

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
            if isinstance(value[0], (float, int)):
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
        from mitsuba.core import Transform4f

        if len(matrix) == 4:
            mat = self.axis_mat @ matrix
        else: #3x3
            mat = matrix.to_4x4()
        return Transform4f(list([list(x) for x in mat]))
