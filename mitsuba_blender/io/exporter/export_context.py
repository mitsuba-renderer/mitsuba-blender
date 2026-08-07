import os
from collections import OrderedDict

from mathutils import Matrix

class ExportContext:
    '''
    Export Context
    '''

    # Subfolders of the export directory receiving meshes and textures
    MESHES_FOLDER = 'meshes'
    TEXTURES_FOLDER = 'textures'
    # Every exported mesh is appended to this one file, and the shapes
    # reference their sub-mesh by index
    SERIALIZED_NAME = 'meshes.serialized'

    def __init__(self):
        self.scene_data = OrderedDict([('type','scene')])
        self.warnings = [] # Messages of WARN or ERROR level, for reporting after the export
        self.counter = 0 # Counter to create unique IDs.
        # Materials with both a BSDF and an emitter, as
        # {mat_id: {'bsdf': bsdf_id, 'emitter': emitter_dict}}; shapes
        # using them need two references
        self.exported_mats = {}
        self.export_ids = False # Export Object IDs in the XML file
        self.render = False # Render mode keeps instantiated Mitsuba objects in the dict
        self.bsdf_objects = {} # Instantiated BSDFs, by material id (render mode)
        # Let Blender split the polygons of a mesh instead of Mitsuba
        self.blender_triangulation = False
        # Shared .serialized output and the file offset of each sub-mesh
        self.serialized_stream = None
        self.serialized_offsets = []
        # All the args defined below are set in the Converter
        self.directory = ''
        self.axis_mat = Matrix() # Coordinate shift
        self.deg = None # Dependency graph

    def add_serialized_mesh(self, mi_mesh):
        '''Append a mesh to the scene's shared .serialized file, returning
        the sub-mesh index that a shape entry references it by.'''
        import mitsuba as mi
        if self.serialized_stream is None:
            folder = os.path.join(self.directory, self.MESHES_FOLDER)
            os.makedirs(folder, exist_ok=True)
            self.serialized_stream = mi.FileStream(
                os.path.join(folder, self.SERIALIZED_NAME),
                mi.FileStream.ETruncReadWrite)
        self.serialized_offsets.append(self.serialized_stream.tell())
        mi_mesh.write_serialized(self.serialized_stream)
        return len(self.serialized_offsets) - 1

    def finalize_serialized(self):
        '''Close the shared file with the end-of-file dictionary that lets
        the serialized plugin seek to a sub-mesh: one uint64 offset per
        mesh, followed by their count.'''
        if self.serialized_stream is None:
            return
        import mitsuba as mi
        stream = self.serialized_stream
        stream.set_byte_order(mi.FileStream.ELittleEndian)
        for offset in self.serialized_offsets:
            stream.write_uint64(offset)
        stream.write_uint32(len(self.serialized_offsets))
        stream.close()
        self.serialized_stream = None

    def serialized_filename(self):
        '''Relative path that the shape entries reference.'''
        return f'{self.MESHES_FOLDER}/{self.SERIALIZED_NAME}'

    def sanitize(self, name):
        '''
        Sanitize a name to be used in the scene dict.
        The parser class of Mitsuba does not accept dots in the names.
        '''
        return name.replace('.', '_')

    def create_ref(self, name):
        '''
        Create a reference dict pointing to the given name,
        after sanitizing it.
        '''
        return {
            'type': 'ref',
            'id': self.sanitize(name)
        }

    def data_add(self, mts_dict, name=''):
        '''
        Function to add new elements to the scene dict. The element is either
        a plugin dict or an already instantiated Mitsuba object (render mode).
        If a name is provided it will be used as the key of the element.
        Otherwise the Id of the element is used if it exists
        or a new key is generated incrementally.
        '''
        if mts_dict is None or (isinstance(mts_dict, dict)
                                and 'type' not in mts_dict):
            self.log('Skipping scene dict entry "%s" without a plugin '
                     'type: %r' % (name, mts_dict), 'WARN')
            return

        if not name:
            if isinstance(mts_dict, dict) and 'id' in mts_dict:
                name = mts_dict['id']
                #remove the corresponding entry
                del mts_dict['id']
            else:
                name = 'elm__%i' % self.counter

        # Sanitize name
        self.scene_data.update([(self.sanitize(name), mts_dict)])
        self.counter += 1

    def data_get(self, name):
        return self.scene_data.get(self.sanitize(name))

    def log(self, message, level='INFO'):
        '''
        Log something using mitsuba's logging API. Messages of WARN or
        ERROR level are also collected in self.warnings so they can be
        reported once the export has finished.

        Params
        ------

        message: What to write
        level: Level of logging
        '''
        from mitsuba import Log, LogLevel
        if level in ('WARN', 'ERROR'):
            self.warnings.append(message)
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

    def spectrum(self, value):
        '''
        Format a float or RGB(A) value as an rgb spectrum for the scene
        dict. An alpha component is dropped.
        '''
        if isinstance(value, (float, int)):
            return {'type': 'rgb', 'value': float(value)}
        value = list(value)
        if len(value) in (3, 4) and \
                all(isinstance(x, (float, int)) for x in value):
            return {'type': 'rgb', 'value': value[:3]}
        raise ValueError('Expected a float or a 3/4-component sequence, '
                         'got: %s' % (value,))

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
