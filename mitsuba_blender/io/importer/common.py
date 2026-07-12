import os

class MitsubaSceneImportContext:
    ''' Define a context for the Mitsuba scene importer '''
    def __init__(self, bl_context, bl_scene, bl_collection, filepath, mi_state, axis_matrix,
                 import_render_settings=False):
        self.bl_context = bl_context
        self.bl_scene = bl_scene
        self.bl_collection = bl_collection
        self.filepath = filepath
        self.directory, _ = os.path.split(self.filepath)
        self.mi_state = mi_state
        self.axis_matrix = axis_matrix
        self.import_render_settings = import_render_settings
        self.axis_matrix_inv = axis_matrix.inverted()
        self.bl_material_cache = {} # Mapping of Mitsuba node IDs to Blender materials
        self.bl_texture_cache = {} # Mapping of Mitsuba node IDs to Blender textures
        self.processed_nodes = set()
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

    def bl_space_to_mi_space(self, matrix):
        return self.axis_matrix @ matrix

    def mi_space_to_bl_space(self, matrix):
        return self.axis_matrix_inv @ matrix

    def resolve_scene_relative_path(self, path):
        abs_path = os.path.join(self.directory, path)
        if not os.path.exists(abs_path):
            self.log(f'Cannot resolve scene relative path "{path}".', 'ERROR')
            return None
        return abs_path

