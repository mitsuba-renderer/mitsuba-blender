import os

class MitsubaSceneImportContext:
    ''' Define a context for the Mitsuba scene importer '''
    def __init__(self, bl_context, bl_scene, bl_collection, filepath, mi_state, axis_matrix):
        self.bl_context = bl_context
        self.bl_scene = bl_scene
        self.bl_collection = bl_collection
        self.filepath = filepath
        self.directory, _ = os.path.split(self.filepath)
        self.mi_state = mi_state
        self.axis_matrix = axis_matrix
        self.axis_matrix_inv = axis_matrix.inverted()
        self.bl_data_cache = {} # Mapping of Mitsuba node IDs to Blender data types
        self.processed_nodes = set()

    def log(self, message, level='INFO'):
        '''
        Log something using mitsuba's logging API

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
            'ERROR': LogLevel.Error,
            'TRACE': LogLevel.Trace
            }
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

