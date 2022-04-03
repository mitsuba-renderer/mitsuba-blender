from collections import OrderedDict
import os

class MitsubaScenePropertiesIterator:
    """ Iterator for Mitsuba properties. Implement filtering based on object class type """
    def __init__(self, props, cls_filter: str = ''):
        self._objects = list(props.objects.items())
        self._cls_filter = cls_filter
        self._index = 0

    def __iter__(self):
        return self

    def __next__(self):
        # If a filter is set, skip entries that don't match the specified class type
        if self._cls_filter != '':
            while self._index < len(self._objects) and self._objects[self._index][1][0] != self._cls_filter:
                self._index += 1

        if self._index < len(self._objects):
            id, (cls, prop) = self._objects[self._index]
            self._index += 1
            return cls, prop

        raise StopIteration

class MitsubaSceneProperties:
    """ Container for loaded Mitsuba scene properties """
    def __init__(self, props):
        self.objects = OrderedDict()
        for (class_, prop) in props:
            self.objects[prop.id()] = (class_, prop)

    def __len__(self):
        return len(self.objects)

    def __iter__(self):
        return MitsubaScenePropertiesIterator(self)

    def with_class(self, cls):
        return MitsubaScenePropertiesIterator(self, cls_filter=cls)

    def get_with_id(self, id):
        """ Get the property of an object with a certain id """
        if id in self.objects:
            return self.objects[id]
        return None

class MitsubaSceneImportContext:
    """ Define a context for the Mitsuba scene importer """
    def __init__(self, bl_context, bl_scene, bl_collection, filepath, mi_props, axis_matrix):
        self.bl_context = bl_context
        self.bl_scene = bl_scene
        self.bl_collection = bl_collection
        self.filepath = filepath
        self.directory, _ = os.path.split(self.filepath)
        self.mi_props = mi_props
        self.axis_matrix = axis_matrix
        self.axis_matrix_inv = axis_matrix.inverted()
        self.bl_materials = {}

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

    def register_bl_material(self, id, bl_mat):
        if id in self.bl_materials:
            self.log(f'Material "{id}" is already registered.', 'ERROR')
        else:
            self.bl_materials[id] = bl_mat

    def get_bl_material(self, id):
        if id not in self.bl_materials:
            self.log(f'Unknown material "{id}".', 'ERROR')
            return None
        return self.bl_materials[id]
