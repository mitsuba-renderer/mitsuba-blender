from collections import OrderedDict

from mathutils import Matrix

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

class ExportContext:
    '''
    Export Context
    '''

    def __init__(self):
        self.scene_data = OrderedDict([('type','scene')])
        self.warnings = [] # Messages of WARN or ERROR level, for reporting after the export
        self.counter = 0 # Counter to create unique IDs.
        self.exported_mats = ExportedMaterialsCache()
        self.export_ids = False # Export Object IDs in the XML file
        self.render = False # Render mode keeps instantiated Mitsuba objects in the dict
        self.bsdf_objects = {} # Instantiated BSDFs, by material id (render mode)
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
        if mts_dict is None:
            return False
        if isinstance(mts_dict, dict) and (len(mts_dict) == 0 or 'type' not in mts_dict):
            return False

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

        return True

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
        from mitsuba import ScalarTransform4f
        if len(matrix) == 4:
            mat = self.axis_mat @ matrix
        else: #3x3
            mat = matrix.to_4x4()
        return ScalarTransform4f(list([list(x) for x in mat]))
