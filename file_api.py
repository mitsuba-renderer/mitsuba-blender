from collections import OrderedDict

import os
import sys
import subprocess

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

class MixedMaterialsCache:
    '''
    Store a list of the exported materials, that have both a BSDF and an emitter
    We need it to add 2 refs to each shape using this material
    This is useless when a material is only one bsdf/emitter, so we won't add those.
    '''
    def __init__(self):
        self.mats = {}

    def add_material(self, mat_list, mat_id):
        """
        Store a list of materials in the data structure

        mat_list: list of references to materials (BSDF or emitter)
        mat_id: id of the blender material that encapsulates all these
        """
        self.mats[mat_id] = mat_list

    def has(self, mat_id):
        """
        Determine if the given material is in the cache or not
        """
        return mat_id in self.mats.keys()


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
    files = []
    file_names = []
    file_tabs = []
    file_stack = []
    current_file = Files.MAIN
    exported_ids = set()
    color_mode = 'rgb'
    directory = ''

    def __init__(self):
        self.scene_data = OrderedDict([('type','scene')])
        self.counter = 0
        self.mixed_mats = MixedMaterialsCache()

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
        self.writeHeader(Files.MAIN, '# Main Scene File')

        self.directory = '%s/' % ('/'.join(name.split('/')[:-1]))#extract directory from file path  TODO: windows paths
        print('Scene File: %s' % self.file_names[Files.MAIN])
        print('Scene Folder: %s' % self.directory)

        #TODO: splitting in different files does not work, fix that
        if split_files:

            self.file_names.append('%s/Mitsuba-Materials.xml' % self.directory)
            self.files.append(open(self.file_names[Files.MATS], 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.writeHeader(Files.MATS, '# Materials File')

            self.file_names.append('%s/Mitsuba-Geometry.xml' % self.directory)
            self.files.append(open(self.file_names[Files.GEOM], 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.writeHeader(Files.GEOM, '# Geometry File')

            self.file_names.append('%s/Mitsuba-Volumes.xml' % self.directory)
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

    def writeHeader(self, file, comment):
        self.wf(file, '<?xml version="1.0" encoding="utf-8"?>\n')
        self.wf(file, '<!-- %s -->\n' % comment)

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

        self.pmgr_create(self.scene_data)

        # Close files
        print('Wrote scene files')
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
        l = [matrix[0][0], matrix[0][1], matrix[0][2], matrix[0][3],
             matrix[1][0], matrix[1][1], matrix[1][2], matrix[1][3],
             matrix[2][0], matrix[2][1], matrix[2][2], matrix[2][3],
             matrix[3][0], matrix[3][1], matrix[3][2], matrix[3][3]]
        value = " ".join(["%f" % f for f in l])

        params = {
            'type': 'transform',
            'matrix': {
                'type': 'matrix',
                'value': value,
            }
        }
        return params