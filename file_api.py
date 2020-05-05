from collections import OrderedDict
import os
from shutil import copy2
from numpy import pi
from mathutils import Matrix
from .dict_to_xml import WriteXML

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
                print("Image format of '%s' not supported. Converting it to %s." % (image.name, convert_format[image.file_format]))
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
            print("Saved image '%s' as '%s'." % (image.name, name))
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

    color_mode = 'rgb'

    def __init__(self):
        self.xml_writer = WriteXML()
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
        self.xml_writer.set_filename(name, split_files)
        self.directory = self.xml_writer.directory

    def configure(self):
        '''
        Special handling of configure API.
        '''
        #temporary tests TODO: remove when thoroughly tested
        print(self.scene_data)
        '''
        from mitsuba.core.xml import load_dict
        scene = load_dict(self.scene_data)
        sensor = scene.sensors()[0]
        scene.integrator().render(scene, sensor)
        film = sensor.film()
        film.set_destination_file(os.path.join(self.directory, "python.exr"))
        film.develop()
        '''
        #the only line to keep:
        self.xml_writer.configure(self.scene_data)

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

    def spectrum(self, value, mode=''):
        if not mode:
            mode = self.color_mode

        spec = {}

        if isinstance(value, (dict)):
            if 'type' in value:
                if value['type'] in {'rgb', 'srgb', 'spectrum'}:
                    spec = self.spectrum(value['value'], value['type'])

                else:
                    spec = value

        elif isinstance(value, (float, int)):
            spec = {'value': value, 'type': 'spectrum'}

        elif isinstance(value, (str)):
            spec = {'filename': value, 'type': 'spectrum'}#TODO: export path
        #TODO: handle all types of spectra (blackbody, uniform, d65...)
        else:
            try:
                items = list(value)

                for i in items:
                    if not isinstance(i, (float, int, tuple)):
                        raise Exception('Error: spectrum list contains an unknown type')

            except:
                items = None

            if items:
                totitems = len(items)

                if isinstance(items[0], (float, int)):
                    if totitems == 3 or totitems == 4:
                        spec = {'value': items[:3]}

                        if mode == 'srgb':
                            spec.update({'type': 'srgb'})

                        else:
                            spec.update({'type': 'rgb'})

                    elif totitems == 1:
                        spec = {'value': items[0], 'type': 'spectrum'}

                    else:
                        print('Expected spectrum items to be 1, 3 or 4, got %d.' % len(items), type(items), items)

                else:
                    contspec = []

                    for spd in items:
                        (wlen, val) = spd
                        contspec.append('%d:%f' % (wlen, val))

                    spec = {'value': ", ".join(contspec), 'type': 'spectrum'}

            else:
                print('Unknown spectrum type.', type(value), value)

        if not spec:
            spec = {'value': "0.0", 'type': 'spectrum'}

        return spec

    def transform_matrix(self, matrix):
        '''
        Apply coordinate shift and convert to a mitsuba Transform 4f
        '''
        from mitsuba.core import Transform4f

        if len(matrix) == 4:
            mat = self.axis_mat @ matrix
        else: #3x3
            mat = matrix.to_4x4() # TODO: actually write a 3x3
        return Transform4f(list([list(x) for x in mat]))
