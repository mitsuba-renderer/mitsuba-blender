import os

class MitsubaSceneImportContext:
    ''' Define a context for the Mitsuba scene importer '''
    def __init__(self, bl_scene, bl_collection, filepath, mi_state, axis_matrix,
                 import_render_settings=False):
        self.bl_scene = bl_scene
        self.bl_collection = bl_collection
        self.filepath = filepath
        self.directory, _ = os.path.split(self.filepath)
        self.mi_state = mi_state
        # The parser's search paths, plus the scene directory as a last resort
        # since states built from a dictionary do not know about it
        import mitsuba as mi
        self.resolver = mi.FileResolver(mi_state.resolver)
        self.resolver.append(self.directory)
        self.axis_matrix = axis_matrix
        self.import_render_settings = import_render_settings
        self.axis_matrix_inv = axis_matrix.inverted()
        self.bl_material_cache = {} # Mapping of Mitsuba node IDs to Blender materials
        self.bl_texture_cache = {} # Mapping of Mitsuba node IDs to Blender textures
        self.warnings = [] # Messages of WARN or ERROR level, for the operator report

    def log(self, message, level='INFO'):
        '''
        Log an importer message. WARN and ERROR messages are collected in
        self.warnings so the import operator can report them. ERROR does
        not route to Mitsuba's logger, which raises at that level: an
        unsupported piece of content must never abort the whole import.

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
            'TRACE': LogLevel.Trace
            }
        if level in ('WARN', 'ERROR'):
            self.warnings.append(message)
        if level == 'ERROR':
            print(f'ERROR: {message}')
            return
        if level not in log_level:
            raise ValueError("Invalid logging level '%s'!" % level)
        Log(log_level[level], message)

    def mi_space_to_bl_space(self, matrix):
        return self.axis_matrix_inv @ matrix

    def resolve_scene_relative_path(self, path):
        '''Resolve a filename with the scene's search paths. Returns None when
        the file does not exist; the caller reports the failure.'''
        resolved = str(self.resolver.resolve(path))
        return resolved if os.path.exists(resolved) else None

