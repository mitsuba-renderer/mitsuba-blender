import os
from collections import OrderedDict

from mathutils import Matrix

class ExportContext:
    '''
    Export Context
    '''

    # Subfolders of the export directory receiving textures and LUTs
    TEXTURES_FOLDER = 'textures'
    LUTS_FOLDER = 'luts'
    # Every exported mesh and hair particle system is appended to one of
    # these ``.packed`` containers next to the scene file, and the shapes
    # reference their entry by index
    PACKED_NAME = 'meshes.packed'
    CURVES_PACKED_NAME = 'curves.packed'

    def __init__(self):
        self.scene_data = OrderedDict([('type','scene')])
        self.warnings = [] # Messages of WARN or ERROR level, for reporting after the export
        self.counter = 0 # Counter to create unique IDs.
        # Materials with both a BSDF and an emitter, as
        # {mat_id: {'bsdf': bsdf_id, 'emitter': emitter_dict}}; shapes
        # using them need two references
        self.exported_mats = {}
        # Material id -> id of its variant for shapes that only camera rays see
        self.primary_materials = {}
        # BSDF id -> id of its wrapper for shapes that shadow rays ignore
        self.shadowless_materials = {}
        # (owner name, output name) of the Light Path outputs reported as
        # replaced by a constant
        self.light_path_warnings = set()
        # Value of the Geometry node's Backfacing output while a material
        # is converted once per side; None outside of that
        self.backfacing = None
        # Wrap meshes whose material displaces in the displace shape
        # (see convert.export.materials.displacement)
        self.export_displacement = True
        # Material name -> its displacement dict, or None
        self.displacements = {}
        self.export_ids = False # Export Object IDs in the XML file
        # Let Blender split the polygons of a mesh instead of Mitsuba,
        # whose fan triangulation is much faster but fills concave polygons
        self.blender_triangulation = False
        # Shared .packed containers of the exported meshes and curves, and
        # their entry counts
        self.packed_file = None
        self.packed_count = 0
        self.curves_file = None
        self.curves_count = 0
        # Blender lights with a radius, keyed by visibility class; each
        # class becomes one cycles_lights shape (see finalize_lights)
        self.cycles_lights = OrderedDict()
        # Parsed IES profiles by source file or text block, None for
        # profiles that failed to load (see convert.export.lights)
        self.ies_profiles = {}
        # All the args defined below are set in the Converter
        self.directory = ''
        self.axis_mat = Matrix() # Coordinate shift
        self.deg = None # Dependency graph
        self.strict = True

    def _open_container(self, name):
        import mitsuba as mi
        if self.directory:
            os.makedirs(self.directory, exist_ok=True)
        return mi.PackedFile(os.path.join(self.directory, name))

    def add_packed_mesh(self, mi_mesh):
        '''Append a mesh to the scene's shared .packed container, returning
        the entry index that a shape entry references it by.'''
        if self.packed_file is None:
            self.packed_file = self._open_container(self.PACKED_NAME)
        mi_mesh.write_packed(self.packed_file)
        self.packed_count += 1
        return self.packed_count - 1

    def add_packed_curves(self, name, points, offsets):
        '''Append a curve entry to the scene's curve container, returning
        the entry index that a curve shape references it by.

        ``points`` is a float32 array of shape (P, 4) holding the position
        and radius of every control point, and ``offsets`` a uint32 array
        with the first control point index of each curve followed by P. The
        entry layout is documented in the Mitsuba file format reference.
        '''
        import struct
        if self.curves_file is None:
            self.curves_file = self._open_container(self.CURVES_PACKED_NAME)
        pf = self.curves_file
        pf.begin(name)
        pf.stream().write(b'CURV' + struct.pack('<III', 1, len(offsets) - 1,
                                                len(points)))
        pf.write_array(offsets.tobytes())
        pf.write_array(points.tobytes())
        self.curves_count += 1
        return self.curves_count - 1

    def finalize_packed(self):
        '''Close the shared containers, which writes the dictionary that
        the plugins need to locate an entry.'''
        for attr in ('packed_file', 'curves_file'):
            pf = getattr(self, attr)
            if pf is not None:
                pf.close()
                setattr(self, attr, None)

    def packed_filename(self):
        '''Relative path that the mesh shape entries reference.'''
        return self.PACKED_NAME

    def curves_filename(self):
        '''Relative path that the curve shape entries reference.'''
        return self.CURVES_PACKED_NAME

    def add_cycles_light(self, params):
        '''Queue one light of the cycles_lights shape (a dict with the
        entries p, r, power, for spots dir, angle and blend, and for lights
        with an IES profile frame and ies, the latter a dict with the
        entries table, columns and range).'''
        visibility = params.get('visibility', 'all')
        self.cycles_lights.setdefault(visibility, []).append(params)

    def finalize_lights(self):
        '''Add the queued lights to the scene dict as one cycles_lights
        shape per visibility class, numbering their properties. Lights of
        a shape that use the same IES table share one profile entry.'''
        for visibility, lights in self.cycles_lights.items():
            shape = {'type': 'cycles_lights'}
            if visibility != 'all':
                shape['visibility'] = visibility
            profiles = OrderedDict()
            for i, light in enumerate(lights):
                for key in ('p', 'r', 'power', 'dir', 'angle', 'blend',
                            'frame'):
                    if key in light:
                        shape[f'{key}{i}'] = light[key]
                if 'ies' in light:
                    ies = light['ies']
                    key = (ies['table'], ies['columns'], ies['range'])
                    shape[f'profile{i}'] = profiles.setdefault(key,
                                                               len(profiles))
            for k, (table, columns, bounds) in enumerate(profiles):
                shape[f'ies{k}'] = table
                shape[f'ies_columns{k}'] = columns
                shape[f'ies_range{k}'] = bounds
            name = f'emit-cycles_lights-{visibility}' if self.export_ids else ''
            self.data_add(shape, name=name)
        self.cycles_lights.clear()

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
        Function to add new elements to the scene dict. The element is a
        plugin dict. If a name is provided it will be used as the key of
        the element. Otherwise the Id of the element is used if it exists
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
