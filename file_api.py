from collections import OrderedDict

import os
import sys
import subprocess
from shutil import copy2

mitsuba_props = {
    'ref',
    'lookat',
    'scale',
    'matrix',
    'point',
    'vector',
    'rgb',
    'srgb',
    'blackbody',
    'spectrum',
}
#TODO: figure out if spectrum is a plugin or a property
mitsuba_tags = {
    'scene',
    'shape',
    'sampler',
    'film',
    'integrator',
    'texture',
    'sensor',
    'emitter',
    'subsurface',
    'medium',
    'phase',
    'bsdf',
    'rfilter',
    'transform'
}

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
    VOLM = 3

class FileExportContext:
    '''
    File API
    '''

    EXPORT_API_TYPE = 'FILE'
    color_mode = 'rgb'

    def __init__(self):
        self.scene_data = OrderedDict([('type','scene')])
        self.counter = 0
        self.exported_mats = ExportedMaterialsCache()
        self.exported_ids = set()
        self.files = []
        self.file_names = []
        self.file_tabs = []
        self.file_stack = []
        self.current_file = Files.MAIN
        self.directory = ''

    # Function to add new elements to the scene dict.
    # If a name is provided it will be used as the key of the element.
    # Otherwise the Id of the element is used if it exists
    # or a new key is generated incrementally.
    def data_add(self, mts_dict, name=''):
        if mts_dict is None or not isinstance(mts_dict, dict) or len(mts_dict) == 0 or 'type' not in mts_dict:
            return False

        if not name:
            try:
                name = mts_dict['id']

            except:
                name = 'elm%i' % self.counter

        self.scene_data.update([(name, mts_dict)])
        self.counter += 1

        return True

    def add_comment(self, comment):
        self.data_add({'type':'comment', 'value': comment})

    def wf(self, ind, st, tabs=0):
        '''
        ind                 int
        st                  string
        tabs                int

        Write a string to file index ind.
        Optionally indent the string by a number of tabs

        Returns None
        '''

        if len(self.files) == 0:
            scene = object()
            scene.name = 'untitled'
            scene.frame_current = 1
            self.set_filename(scene, 'default')

        # Prevent trying to write to a file that isn't open
        if self.files[ind] is None:
            ind = 0

        self.files[ind].write('%s%s' % ('\t' * tabs, st))
        self.files[ind].flush()

    def set_filename(self, name, split_files=False):
        '''
        name                string

        Open the main, materials, and geometry files for output,
        using filenames based on the given name.

        Returns None
        '''

        # If any files happen to be open, close them and start again
        for f in self.files:
            if f is not None:
                f.close()

        self.files = []
        self.file_names = []
        self.file_tabs = []
        self.file_stack = []

        if name[-4:] != '.xml':
            name += '.xml'

        self.file_names.append(name)
        self.files.append(open(self.file_names[Files.MAIN], 'w', encoding='utf-8', newline="\n"))
        self.file_tabs.append(0)
        self.file_stack.append([])
        if split_files:
            self.writeHeader(Files.MAIN, '# Main Scene File')
        else:
            self.writeHeader(Files.MAIN)

        self.directory = os.path.dirname(name)
        print('Scene File: %s' % self.file_names[Files.MAIN])
        print('Scene Folder: %s' % self.directory)

        #Set texture directory name
        self.textures_folder = os.path.join(self.directory, "textures")
        #create geometry export directory
        geometry_folder = os.path.join(self.directory, "meshes")
        if not os.path.isdir(geometry_folder):
            os.mkdir(geometry_folder)

        #TODO: splitting in different files does not work, fix that
        if split_files:

            self.file_names.append(os.path.join(self.directory, 'Mitsuba-Materials.xml'))
            self.files.append(open(self.file_names[Files.MATS], 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.writeHeader(Files.MATS, '# Materials File')

            self.file_names.append(os.path.join(self.directory, 'Mitsuba-Geometry.xml'))
            self.files.append(open(self.file_names[Files.GEOM], 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.writeHeader(Files.GEOM, '# Geometry File')

            self.file_names.append(os.path.join(self.directory, 'Mitsuba-Volumes.xml'))
            self.files.append(open(self.file_names[Files.VOLM], 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.writeHeader(Files.VOLM, '# Volume File')

        self.set_output_file(Files.MAIN)

    def set_output_file(self, file):
        '''
        file                int

        Switch next output to the given file index

        Returns None
        '''

        self.current_file = file

    def writeComment(self, file, comment):
        self.wf(file, '\n')
        self.wf(file, '<!-- %s -->\n' % comment)
        self.wf(file, '\n')

    def writeHeader(self, file, comment=None):
        self.wf(file, '<?xml version="1.0" encoding="utf-8"?>\n')
        if comment:
            self.writeComment(file, comment)

    def openElement(self, name, attributes={}, file=None):
        if file is not None:
            self.set_output_file(file)

        self.wf(self.current_file, '<%s' % name, self.file_tabs[self.current_file])

        for (k, v) in attributes.items():
            self.wf(self.current_file, ' %s=\"%s\"' % (k, v.replace('"', '')))

        self.wf(self.current_file, '>\n')

        # Indent
        self.file_tabs[self.current_file] = self.file_tabs[self.current_file] + 1
        self.file_stack[self.current_file].append(name)

    def closeElement(self, file=None):
        if file is not None:
            self.set_output_file(file)

        # Un-indent
        self.file_tabs[self.current_file] = self.file_tabs[self.current_file] - 1
        name = self.file_stack[self.current_file].pop()

        self.wf(self.current_file, '</%s>\n' % name, self.file_tabs[self.current_file])

    def element(self, name, attributes={}, file=None):
        if file is not None:
            self.set_output_file(file)

        self.wf(self.current_file, '<%s' % name, self.file_tabs[self.current_file])

        for (k, v) in attributes.items():
            self.wf(self.current_file, ' %s=\"%s\"' % (k, v))

        self.wf(self.current_file, '/>\n')

    def parameter(self, paramType, paramName, attributes={}, file=None):
        if file is not None:
            self.set_output_file(file)

        self.wf(self.current_file, '<%s name="%s"' % (paramType, paramName), self.file_tabs[self.current_file])

        for (k, v) in attributes.items():
            self.wf(self.current_file, ' %s=\"%s\"' % (k, v))

        self.wf(self.current_file, '/>\n')

    def preprocess_scene(self):
        '''
        Re-order the elements of the scene_data dict, for more readability.
        We sort the scene data such that the resulting XML file writes the camera data, then the emitters,
        then the BSDFs and finally the meshes.
        '''
        keys = list(self.scene_data.keys())
        del keys[0] # ignore the "scene" tag
        emitters = []
        mats = []
        meshes = []
        for key in keys:
            try:
                plugin = self.scene_data[key]['plugin']
            except KeyError: # not a plugin, ignore
                continue
            if plugin == 'shape':
                meshes.append(key)
            elif plugin == 'emitter':
                emitters.append(key)
            elif plugin == 'bsdf':
                mats.append(key)

        self.add_comment("Emitters")
        #re order the plugins such that we read first the emitters, then the materials, and finally the meshes
        for key in emitters:
            #re add the plugin at the end of the scene data list
            plug = self.scene_data.pop(key)
            self.scene_data[key] = plug
        self.add_comment("Materials")
        for key in mats:
            #re add the plugin at the end of the scene data list
            plug = self.scene_data.pop(key)
            self.scene_data[key] = plug
        self.add_comment("Shapes")
        for key in meshes:
            #re add the plugin at the end of the scene data list
            plug = self.scene_data.pop(key)
            self.scene_data[key] = plug

    # Funtions to emulate Mitsuba extension API
    #TODO: redo all this, it is weird and unobvious
    def pmgr_create(self, mts_dict=None, args={}):
        if mts_dict is None or not isinstance(mts_dict, dict) or len(mts_dict) == 0 or 'type' not in mts_dict:
            return

        param_dict = mts_dict.copy()
        plugin_type = param_dict.pop('type')
        #plugin = get_plugin_tag(plugin_type)
        try:
            plugin = param_dict.pop('plugin')
        except KeyError:
            plugin = plugin_type

        if plugin != plugin_type:
            args['type'] = plugin_type

        if plugin == 'scene':
            args['version'] = '2.0.0'

        elif plugin == 'comment':
            self.writeComment(Files.MAIN, param_dict['value'])
            return

        elif plugin in mitsuba_props:
            args.update(param_dict)
            param_dict = {}

            if plugin == 'ref' and 'id' in args and args['id'] not in self.exported_ids:
                print('************** Reference ID - %s - exported before referencing **************' % (args['id']))
                return

            elif plugin in {'matrix', 'lookat', 'scale'}:
                del args['name']

        else:
            if plugin != plugin_type and plugin != 'texture':
                del args['name']#plugins except textures don't need their inherited name
            if 'name' in param_dict:
                args['name'] = param_dict['name']
                del param_dict['name']

            if 'id' in param_dict:
                args['id'] = param_dict.pop('id')

                if args['id'] not in self.exported_ids:
                    self.exported_ids.add(args['id'])

                else:
                    print('************** Plugin - %s - ID - %s - already exported **************' % (plugin_type, args['id']))
                    return

        try:
            if args['name'] == args['id']:
                del(args['name'])

        except:
            pass

        if len(param_dict) > 0 and plugin in mitsuba_tags:
            self.openElement(plugin, args)

            for param, value in param_dict.items():
                if isinstance(value, dict) and 'type' in value:
                    self.pmgr_create(value, {'name': param})

                elif isinstance(value, str):
                    self.parameter('string', param, {'value': value})

                elif isinstance(value, bool):
                    self.parameter('boolean', param, {'value': str(value).lower()})

                elif isinstance(value, int):
                    self.parameter('integer', param, {'value': '%d' % value})

                elif isinstance(value, float):
                    self.parameter('float', param, {'value': '%f' % value})

                else:
                    print('************** %s param not supported: %s **************' % (plugin_type, param))
                    print(value)

            self.closeElement()

        elif len(param_dict) == 0:
            self.element(plugin, args)

        else:
            print('************** Plugin not supported: %s **************' % plugin_type)
            print(param_dict)

    def configure(self):
        '''
        Special handling of configure API.
        '''
        self.preprocess_scene() # Re order elements
        self.pmgr_create(self.scene_data) # write XML file

        # Close files
        print('Wrote scene files.')
        for f in self.files:
            if f is not None:
                f.close()
                print(' %s' % f.name)

    def cleanup(self):
        self.exit()

    def exit(self):
        # If any files happen to be open, close them and start again
        for f in self.files:
            if f is not None:
                f.close()

    def export_texture(self, image):
        """
        Copy a texture file to the Mitsuba scene folder.
        Create the subfolder the first time this method is called

        tex_path : the full path to the texture
        """
        if not os.path.isdir(self.textures_folder):
            os.mkdir(self.textures_folder)

        img_name = self.exported_mats.get_tex_id(image, self.textures_folder)
        return os.path.join("textures", img_name)

    def point(self, point):
        #convert a point to a dict
        return {
            'type' : 'point',
            'x' : point[0] , 'y' :  point[1] , 'z' :  point[2]
        }

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
            spec = {'value': "%f" % value, 'type': 'spectrum'}

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
                        spec = {'value': "%f %f %f" % (items[0], items[1], items[2])}

                        if mode == 'srgb':
                            spec.update({'type': 'srgb'})

                        else:
                            spec.update({'type': 'rgb'})

                    elif totitems == 1:
                        spec = {'value': "%f" % items[0], 'type': 'spectrum'}

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
        l = []
        for row in matrix:
            for val in row:
                l.append(val)

        value = " ".join(["%f" % f for f in l])

        params = {
            'type': 'transform',
            'matrix': {
                'type': 'matrix',
                'value': value,
            }
        }
        return params
