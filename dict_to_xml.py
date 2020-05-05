from collections import OrderedDict
from numpy import pi
import os

mitsuba_props = {
    'ref',
    'lookat',
    'scale',
    'translate',
    'rotate',
    'matrix',
    'vector',
    'rgb',
    'srgb',
    'blackbody',
    'spectrum',
    'include',
    'default',
    'integer',
    'float',
    'string',
    'boolean',
    'comment'
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
class Files:
    MAIN = 0
    MATS = 1
    GEOM = 2
    EMIT = 3
    CAMS = 4
    #TODO: Volumes

class WriteXML:
    '''
    File Writing API
    '''

    defaults = { #arg name: default name
        'sample_count': 'spp',
        'width': 'resx',
        'height': 'resy'
    }

    def __init__(self):
        self.scene_data = [OrderedDict([('type','scene')]), #MAIN
                      OrderedDict(), #MATS
                      OrderedDict(), #GEOM
                      OrderedDict(), #EMIT
                      OrderedDict()] #CAMS
        self.com_count = 0 #counter for comment ids
        self.exported_ids = set()
        self.files = []
        self.file_names = [] #relative paths to the fragment files
        self.file_tabs = []
        self.file_stack = []
        self.current_file = Files.MAIN
        self.directory = ''

    def data_add(self, key, value, file=Files.MAIN):
        self.scene_data[file].update([(key, value)])

    def add_comment(self, comment, file=Files.MAIN):
        key = "__com__%d" % self.com_count
        self.com_count += 1
        self.data_add(key,{'type':'comment', 'value': comment}, file)

    def add_include(self, file):
        key = "__include__%d" % file
        value = {'type':'include', 'filename':self.file_names[file]}
        self.data_add(key, value) #add to main

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

        self.file_names.append(name)
        self.files.append(open(self.file_names[Files.MAIN], 'w', encoding='utf-8', newline="\n"))
        self.file_tabs.append(0)
        self.file_stack.append([])
        if split_files:
            self.write_header(Files.MAIN, '# Main Scene File')
        else:
            self.write_header(Files.MAIN)

        self.directory, main_file = os.path.split(name)
        base_name = os.path.splitext(main_file)[0] #remove the extension

        print('Scene File: %s' % self.file_names[Files.MAIN])
        print('Scene Folder: %s' % self.directory)

        #Set texture directory name
        self.textures_folder = os.path.join(self.directory, "textures")
        #create geometry export directory
        geometry_folder = os.path.join(self.directory, "meshes")
        if not os.path.isdir(geometry_folder):
            os.mkdir(geometry_folder)

        self.split_files = split_files
        #TODO: splitting in different files does not work, fix that
        if split_files:
            fragments_folder = os.path.join(self.directory, "fragments")
            if not os.path.isdir(fragments_folder):
                os.mkdir(fragments_folder)

            self.file_names.append('fragments/%s-materials.xml' % base_name)
            self.files.append(open(os.path.join(self.directory, self.file_names[Files.MATS]), 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.write_header(Files.MATS, '# Materials File')

            self.file_names.append('fragments/%s-geometry.xml' % base_name)
            self.files.append(open(os.path.join(self.directory, self.file_names[Files.GEOM]), 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.write_header(Files.GEOM, '# Geometry File')

            self.file_names.append('fragments/%s-emitters.xml' % base_name)
            self.files.append(open(os.path.join(self.directory, self.file_names[Files.EMIT]), 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.write_header(Files.EMIT, '# Emitters File')

            self.file_names.append('fragments/%s-render.xml' % base_name)
            self.files.append(open(os.path.join(self.directory, self.file_names[Files.CAMS]), 'w', encoding='utf-8', newline="\n"))
            self.file_tabs.append(0)
            self.file_stack.append([])
            self.write_header(Files.CAMS, '# Cameras and Render Parameters File')

        self.set_output_file(Files.MAIN)

    def set_output_file(self, file):
        '''
        file                int

        Switch next output to the given file index

        Returns None
        '''

        self.current_file = file

    def write_comment(self, comment, file=None):
        if not file:
            file = self.current_file
        self.wf(file, '\n')
        self.wf(file, '<!-- %s -->\n' % comment)
        self.wf(file, '\n')

    def write_header(self, file, comment=None):
        self.wf(file, '<?xml version="1.0" encoding="utf-8"?>\n')
        if comment:
            self.write_comment(comment, file)

    def open_element(self, name, attributes={}, file=None):
        if file is not None:
            self.set_output_file(file)

        self.wf(self.current_file, '<%s' % name, self.file_tabs[self.current_file])

        for (k, v) in attributes.items():
            self.wf(self.current_file, ' %s=\"%s\"' % (k, v.replace('"', '')))

        self.wf(self.current_file, '>\n')

        # Indent
        self.file_tabs[self.current_file] = self.file_tabs[self.current_file] + 1
        self.file_stack[self.current_file].append(name)

    def close_element(self, file=None):
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

    def preprocess_scene(self, scene_dict):
        '''
        Reorder and format the scene dict before writing it to file.
        Separate the dict into different category-specific subdicts.
        If not splitting files, merge them in the end.
        '''

        if self.split_files:
            for dic in self.scene_data[1:]:
                dic.update([('type','scene')])

        for key, value in scene_dict.items():
            if key == 'type':
                continue #ignore 'scene' tag

            if isinstance(value, dict):#should always be the case
                item_type = value['type']

                plugin = self.get_plugin_tag(item_type)
                if plugin:
                    if plugin == 'emitter':
                        self.data_add(key, value, Files.EMIT)
                    elif plugin == 'shape':
                        if 'emitter' in value.keys(): #emitter nested in a shape (area light)
                            self.data_add(key, value, Files.EMIT)
                        else:
                            self.data_add(key ,value, Files.GEOM)
                    elif plugin == 'bsdf':
                        self.data_add(key, value, Files.MATS)
                    else: #the rest is sensor, integrator and other render stuff
                        self.data_add(key, value, Files.CAMS)
                else:
                    self.data_add(key, value, Files.MAIN)
            else:
                raise NotImplementedError("Unsupported item: %s:%s" % (key,value))


        #add defaults to MAIN file
        #self.add_comment("These arguments can be set via command line: -Dargname=value")
        #for i, default in enumerate(self.defaults.values()):
        #    self.data_add("__def__%d" % i, {'type': 'default', 'value':default})

        # Fill the main file either with includes or with the ordered XML tags.
        self.add_comment("Camera and Rendering Parameters")
        if self.split_files:
            self.add_include(Files.CAMS)
        else:
            self.scene_data[Files.MAIN].update(self.scene_data[Files.CAMS])

        self.add_comment("Materials")
        if self.split_files:
            self.add_include(Files.MATS)
        else:
            self.scene_data[Files.MAIN].update(self.scene_data[Files.MATS])

        self.add_comment("Emitters")
        #re order the plugins such that we read first the emitters, then the materials, and finally the meshes
        if self.split_files:
            self.add_include(Files.EMIT)
        else:
            self.scene_data[Files.MAIN].update(self.scene_data[Files.EMIT])

        self.add_comment("Shapes")
        if self.split_files:
            self.add_include(Files.GEOM)
        else:
            self.scene_data[Files.MAIN].update(self.scene_data[Files.GEOM])

        self.set_output_file(Files.MAIN)

    def get_plugin_tag(self, plugin_type):
        from mitsuba.core import PluginManager
        from mitsuba import variant
        try:
            if not any(plugin_type in x for x in [mitsuba_props, mitsuba_tags]):
                pmgr = PluginManager.instance()
                class_ =  pmgr.get_plugin_class(plugin_type, variant()).parent()
                while class_.alias() == class_.name():
                    class_ = class_.parent()
                return class_.alias()
            else:
                return None
        except RuntimeError: #not a plugin, but a property
            return None

    def format_spectrum(self, entry):
        '''
        format rgb or spectrum tags to the proper XML output.
        '''
        entry_type = entry['type']
        del entry['type']
        if entry_type == 'rgb':
            if len(entry.keys()) != 2 or not entry.get('value') or not isinstance(entry['value'], list) or len(entry['value']) != 3:
                raise ValueError("Invalid entry of type rgb: %s" % entry)
            else:
                entry['value'] = "%f %f %f" % tuple(entry['value'])

        elif entry_type == 'spectrum':
            if len(entry.keys()) != 2:
                raise ValueError("Dict of type 'spectrum': %s has to many entries!" % entry)
            if 'filename' in entry:
                if self.directory in entry['filename']:
                    entry['filename'] = os.path.relpath(entry['filename'], self.directory)
            elif 'value' in entry:
                spval = entry['value']
                if isinstance(spval, float):
                    #uniform spectrum
                    entry['value'] = "%f" % spval
                elif isinstance(spval, list):
                    #list of wavelengths
                    try:
                        entry['value'] = ', '.join(["%f:%f" % (x[0],x[1]) for x in spval])
                    except IndexError:
                        raise ValueError("Invalid entry in 'spectrum' wavelength list: %s" % spval)
                else:
                    raise ValueError("Invalid value type in 'spectrum' dict: %s" % spval)
            else:
                raise ValueError("Invalid key in 'spectrum' dict: %s" % entry)

        return entry_type, entry

    def pmgr_create(self, mts_dict=None, args={}):
        '''
        This method writes a given dict to file.
        It mimics mitsuba's load_dict method.
        '''
        from mitsuba.core import Transform4f

        if mts_dict is None or not isinstance(mts_dict, dict) or len(mts_dict) == 0 or 'type' not in mts_dict:
            return

        param_dict = mts_dict.copy()
        plugin_type = param_dict.pop('type')
        plugin = self.get_plugin_tag(plugin_type)

        if plugin:
            args['type'] = plugin_type
        else:
            plugin = plugin_type

        if plugin == 'scene':
            args['version'] = '2.0.0'

        elif plugin == 'comment':
            self.write_comment(param_dict['value'])
            return

        elif plugin in mitsuba_props:
            args.update(param_dict)
            param_dict = {}

            if plugin == 'ref' and 'id' in args and args['id'] not in self.exported_ids:
                print('************** Reference ID - %s - exported before referencing **************' % (args['id']))
                return

            elif plugin in {'matrix', 'lookat', 'scale', 'rotate', 'translate', 'include', 'default'}:
                del args['name']

        else:
            if args['name'][:7] != '__elm__' and self.file_stack[self.current_file][-1] == 'scene':
                # assume that top-level entries with non-default keys have ids
                args['id'] = args['name']

            if plugin != plugin_type and plugin != 'texture':
                del args['name']#plugins except textures don't need their inherited name

            if 'name' in param_dict:
                args['name'] = param_dict['name']
                del param_dict['name']

            if 'id' in param_dict:
                args['id'] = param_dict.pop('id')

            if 'id' in args:
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
            self.open_element(plugin, args)

            for param, value in param_dict.items():

                if isinstance(value, dict) and 'type' in value:
                    if value['type'] in ['rgb', 'spectrum']:
                        value['name'] = param
                        name, args = self.format_spectrum(value)
                        self.element(name, args)
                    else:
                        self.pmgr_create(value, {'name': param})

                elif isinstance(value, list):
                    #cast to point
                    if len(value) == 3:
                        args = {'name': param, 'x' : value[0] , 'y' :  value[1] , 'z' :  value[2]}
                        self.element('point', args)
                    else:
                        raise ValueError("Expected 3 values for a point. Got %d instead." % len(value))

                elif isinstance(value, Transform4f):
                    # in which plugin are we adding a transform?
                    parent_plugin = self.file_stack[self.current_file][-1]
                    if parent_plugin == 'sensor':
                        #decompose into rotation and translation
                        self.pmgr_create(self.decompose_transform(value), {'name': param})
                    else:
                        #simply write the matrix to file
                        self.pmgr_create(self.transform_matrix(value), {'name': param})

                elif isinstance(value, str):
                    if os.path.exists(value) and self.directory in value:
                        value = os.path.relpath(value, self.directory) #simplify path
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

            self.close_element()

        elif len(param_dict) == 0:
            self.element(plugin, args)

        else:
            print('************** Plugin not supported: %s **************' % plugin_type)
            print(param_dict)

    def configure(self, scene_dict):
        '''
        Special handling of configure API.
        '''
        self.preprocess_scene(scene_dict) # Re order elements

        if self.split_files:
            for file in [Files.MAIN, Files.CAMS, Files.MATS, Files.GEOM, Files.EMIT]:
                self.set_output_file(file)
                self.pmgr_create(self.scene_data[file])
        else:
            self.pmgr_create(self.scene_data[Files.MAIN])

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

    def transform_matrix(self, transform):
        '''
        Converts a mitsuba Transform4f into a dict entry
        '''

        value = " ".join(["%f" % x for x in transform.matrix.numpy().flatten()])

        params = {
            'type': 'transform',
            'matrix': {
                'type': 'matrix',
                'value': value,
            }
        }
        return params

    def decompose_transform(self, transform, export_scale = False):
        '''
        Export a transform as a combination of rotation, scale and translation.
        This helps manually modifying the transform after export (for cameras for instance)
        '''
        from mathutils import Matrix #TODO don't use blender here
        #convert Mitsuba mat to blender mat
        transform = Matrix(transform.matrix.numpy())

        params = {
            'type': 'transform'
        }

        rot = transform.to_euler('XYZ')
        tr = transform.to_translation()
        sc = transform.to_scale()

        params['rotate_x'] = {
            'type': 'rotate',
            'x': '1',
            'angle': rot[0] * 180 / pi
        }
        params['rotate_y'] = {
            'type': 'rotate',
            'y': '1',
            'angle': rot[1] * 180 / pi
        }
        params['rotate_z'] = {
            'type': 'rotate',
            'z': '1',
            'angle': rot[2] * 180 / pi
        }
        params['translate'] = {
            'type': 'translate',
            'value': "%f %f %f" % tuple(tr)
        }
        if export_scale:
            params['scale'] = { #TODO: remove this for cameras
                'type': 'scale',
                'value': "%f %f %f" % tuple(sc)
            }

        return params
