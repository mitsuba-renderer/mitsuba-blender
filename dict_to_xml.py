from collections import OrderedDict
import numpy as np
import os
from shutil import copy2
import math

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

    def __init__(self, path, split_files=False):
        from mitsuba.core import PluginManager
        self.pmgr = PluginManager.instance()
        self.split_files = split_files
        self.scene_data = [OrderedDict([('type','scene')]), #MAIN
                      OrderedDict(), #MATS
                      OrderedDict(), #GEOM
                      OrderedDict(), #EMIT
                      OrderedDict()] #CAMS
        self.com_count = 0 #counter for comment ids
        self.exported_ids = set()
        self.copy_count = {'tex': 0, 'mesh': 0, 'spectrum': 0}#counters for giving unique names to copied files
        self.copied_paths = {}
        self.files = []
        self.file_names = [] #relative paths to the fragment files
        self.file_tabs = []
        self.file_stack = []
        self.current_file = Files.MAIN
        self.directory = ''
        self.set_filename(path)

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

    def set_filename(self, name):
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
        if self.split_files:
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

        #TODO: splitting in different files does not work, fix that
        if self.split_files:
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

    def get_plugin_tag(self, plugin_type):
        from mitsuba import variant
        try:
            class_ =  self.pmgr.get_plugin_class(plugin_type, variant()).parent()
            while class_.alias() == class_.name():
                class_ = class_.parent()
            return class_.alias()
        except RuntimeError: #not a plugin, but a property
            return None

    def current_tag(self):
        return self.file_stack[self.current_file][-1]

    def configure_defaults(self, scene_dict):
        '''
        Traverse the scene graph and look for properties in the defaults dict.
        For such properties, store their value in a default tag and replace the value by $name in the prop.
        '''
        for key, value in scene_dict.items():
            if isinstance(value, dict):
                self.configure_defaults(value)
            elif key in self.defaults:
                if '$%s'%self.defaults[key] in self.scene_data[Files.MAIN]:
                    print("****** Already exported default for : %s ******" % key)
                    continue
                params = {
                    'type': 'default',
                    'name': self.defaults[key],
                    'value': value
                }
                self.data_add('$%s'%self.defaults[key], params)
                if isinstance(value, int):
                    scene_dict[key] = {'type': 'integer'}
                elif isinstance(value, float):
                    scene_dict[key] = {'type': 'float'}
                elif isinstance(value, str):
                    scene_dict[key] = {'type': 'string'}
                elif isinstance(value, bool):
                    scene_dict[key] = {'type': 'boolean'}
                else:
                    raise ValueError("Unsupported default type: %s" % value)
                #TODO: for now, the only supported defaults are ints, so that works. This may not always be the case though
                if 'name' not in scene_dict[key]:
                    scene_dict[key]['name'] = key
                scene_dict[key]['value'] = '$%s' % self.defaults[key]

    def preprocess_scene(self, scene_dict):
        '''
        Add default properties.
        Reorder the scene dict before writing it to file.
        Separate the dict into different category-specific subdicts.
        If not splitting files, merge them in the end.
        '''

        if self.split_files:
            for dic in self.scene_data[1:]:
                dic.update([('type','scene')])

        if 'type' not in scene_dict:
            raise ValueError("Missing key: 'type'!")
        if scene_dict['type'] != 'scene': #we try to save a plugin, not a scene
            self.data_add('plugin', scene_dict, Files.MAIN) # in this case, don't bother with multiple files
            return

        # add defaults to MAIN file
        self.add_comment("Defaults, these can be set via the command line: -Darg=value")
        self.configure_defaults(scene_dict)
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
                raise ValueError("Unsupported item: %s:%s" % (key,value))


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

    def format_spectrum(self, entry, entry_type):
        '''
        format rgb or spectrum tags to the proper XML output.

        Params
        ------

        entry: the dict containing the spectrum
        entry_type: either 'spectrum' or 'rgb'
        '''
        from mitsuba.core import Color3f
        if entry_type == 'rgb':
            if len(entry.keys()) != 2 or not entry.get('value') or not any(isinstance(entry['value'], x) for x in [list, Color3f, np.ndarray]) or len(entry['value']) != 3:
                raise ValueError("Invalid entry of type rgb: %s" % entry)
            else:
                entry['value'] = "%f %f %f" % tuple(entry['value'])

        elif entry_type == 'spectrum':
            if len(entry.keys()) != 2:
                raise ValueError("Dict of type 'spectrum': %s has to many entries!" % entry)
            if 'filename' in entry:
                entry['filename'] = self.format_path(entry['filename'], 'spectrum')
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

    def format_path(self, filepath, tag):
        '''
        Given a filepath, either copy it in the scene folder (in the corresponding directory)
        or convert it to a relative path.

        Params
        ------

        filepath: the path to the given file
        tag: the tag this path property belongs to in (shape, texture, spectrum)
        '''
        #TODO: centralize subdir names somewhere
        subfolders = {'texture': 'textures', 'emitter': 'textures', 'shape': 'meshes', 'spectrum': 'spectra'}
        prefixes = {'texture': 'tex', 'emitter':'tex', 'shape': 'mesh', 'spectrum': 'spectrum'}

        if tag not in subfolders:
            raise ValueError("Unsupported tag for a filename: %s" % tag)
        abs_path = os.path.join(self.directory, subfolders[tag])
        if abs_path in filepath: # The file is at the proper place already
            return os.path.relpath(filepath, self.directory)
        else: # We need to copy the file in the scene directory
            if filepath in self.copied_paths: # file was already copied, don't copy it again
                return self.copied_paths[filepath]
            if not os.path.isdir(abs_path):
                os.mkdir(abs_path)
            _, ext = os.path.splitext(filepath)
            target_path = os.path.join(abs_path, "%s-%d%s" % (prefixes[tag], self.copy_count[prefixes[tag]], ext))
            self.copy_count[prefixes[tag]] += 1
            copy2(filepath, target_path)
            rel_path = os.path.relpath(target_path, self.directory)
            self.copied_paths[filepath] = rel_path
            return rel_path

    def write_dict(self, data):
        from mitsuba.core import Transform4f, Point3f

        if 'type' in data:#scene tag
            self.open_element(data.pop('type'), {'version': '2.0.0'})

        for key, value in data.items():
            if isinstance(value, dict):
                try:
                    value_type = value.pop('type')
                except KeyError:
                    raise ValueError("Missing key 'type'!")
                if value_type in {'rgb', 'spectrum'}:
                    value['name'] = key
                    name, args = self.format_spectrum(value, value_type)
                    self.element(name, args)
                elif value_type == 'comment':
                    self.write_comment(value['value'])
                elif self.get_plugin_tag(value_type):#plugin
                    tag = self.get_plugin_tag(value_type)
                    args = {'type': value_type}
                    if tag == 'texture' and self.current_tag() != 'scene':
                        args['name'] = key
                    if 'id' in value:
                        args['id'] = value.pop('id')
                    elif key[:7] != '__elm__' and self.current_tag() == 'scene':
                        args['id'] = key #top level keys are IDs, lower level ones are param names
                    if 'id' in args:
                        if args['id'] in self.exported_ids:
                            raise ValueError("Id: %s is already used!" % args['id'])
                        self.exported_ids.add(args['id'])
                    if len(value) > 0: #open a tag if there is still stuff to write
                        self.open_element(tag, args)
                        self.write_dict(value)
                        self.close_element()
                    else:
                        self.element(tag, args) #write dict in one line (e.g. integrator)
                #elif value_type in {'scale', 'rotate', 'translate', 'matrix', 'ref', 'default', 'include', 'integer', 'string', 'boolean', 'float'}:
                else:
                    if value_type == 'ref':
                        if 'name' not in value:
                            value['name'] = key
                        if value['id'] not in self.exported_ids:
                            raise ValueError("Id: %s referenced before export." % value['id'])
                    self.element(value_type, value)
            elif isinstance(value, str):
                if os.path.exists(value):
                    # copy path if necessary and convert it to relative
                    value = self.format_path(value, self.current_tag())
                self.element('string', {'name':key, 'value': '%s' % value})
            elif isinstance(value, bool):
                self.element('boolean', {'name':key, 'value': str(value).lower()})
            elif isinstance(value, int):
                self.element('integer', {'name':key, 'value': '%d' % value})
            elif isinstance(value, float):
                self.element('float', {'name':key, 'value': '%f' % value})
            elif any(isinstance(value, x) for x in [list, Point3f, np.ndarray]):
                #cast to point
                if len(value) == 3:
                    args = {'name': key, 'x' : value[0] , 'y' :  value[1] , 'z' :  value[2]}
                    self.element('point', args)
                else:
                    raise ValueError("Expected 3 values for a point. Got %d instead." % len(value))
            elif isinstance(value, Transform4f):
                # in which plugin are we adding a transform?
                parent_plugin = self.current_tag()
                if parent_plugin == 'sensor':
                    #decompose into rotation and translation
                    params = self.decompose_transform(value)
                else:
                    #simply write the matrix
                    params = self.transform_matrix(value)
                self.open_element('transform', {'name': key})
                self.write_dict(params)
                self.close_element()
            else:
                raise ValueError("Unsupported entry: (%s,%s)" % (key,value))

        if len(self.file_stack[self.current_file]) == 1:
            #close scene tag
            self.close_element()

    def configure(self, scene_dict):
        '''
        Special handling of configure API.
        '''
        self.preprocess_scene(scene_dict.copy()) # Re order elements
        #TODO: open files only here
        if self.split_files:
            for file in [Files.MAIN, Files.CAMS, Files.MATS, Files.GEOM, Files.EMIT]:
                self.set_output_file(file)
                self.write_dict(self.scene_data[file])
        else:
            self.write_dict(self.scene_data[Files.MAIN])

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
        transform = transform.matrix.numpy()

        params = {}

        tr = transform[:3,3]
        scale = [np.linalg.norm(transform[:3,j]) for j in range(3)]
        rot_mat = transform[:3, :3]
        for j in range(3):
            rot_mat[:3,j] *= 1.0 / scale[j]
        rot = mat_to_euler(rot_mat)

        params['rotate_x'] = {
            'type': 'rotate',
            'x': '1',
            'angle': rot[0] * 180 / np.pi
        }
        params['rotate_y'] = {
            'type': 'rotate',
            'y': '1',
            'angle': rot[1] * 180 / np.pi
        }
        params['rotate_z'] = {
            'type': 'rotate',
            'z': '1',
            'angle': rot[2] * 180 / np.pi
        }
        params['translate'] = {
            'type': 'translate',
            'value': "%f %f %f" % tuple(tr)
        }
        if export_scale:
            params['scale'] = { #TODO: remove this for cameras
                'type': 'scale',
                'value': "%f %f %f" % tuple(scale)
            }

        return params

def mat_to_euler(mat):
    '''
    Inspired from a paper by Gregory G. Slabaugh
    https://www.gregslabaugh.net/publications/euler.pdf
    '''
    sin_theta = mat[2,0]
    theta = - math.asin(sin_theta)
    cos_theta = math.cos(theta)
    if cos_theta > 1e-6:
        psi = math.atan2(mat[2,1]/cos_theta, mat[2,2]/cos_theta)
        phi = math.atan2(mat[1,0]/cos_theta, mat[0,0]/cos_theta)
    else:
        phi = 0
        if mat[2,0] + 1 < 1e-6:
            theta = math.pi / 2.0
            psi = math.atan2(mat[0,1], mat[0,2])
        else:
            theta = - math.pi / 2.0
            psi = math.atan2(-mat[0,1], -mat[0,2])
    return psi, theta, phi