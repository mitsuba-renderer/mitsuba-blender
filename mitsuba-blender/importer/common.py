from enum import Enum
from collections import OrderedDict
import os

class BlenderNodeType(Enum):
    NONE = 0,
    SCENE = 1,
    OBJECT = 2,
    MATERIAL = 3,
    PROPERTIES = 4,
    WORLD = 5,
    IMAGE = 6,

class BlenderNode:
    ''' Define a Blender data node.
    These nodes store an intermediate representation of the imported
    Blender data.
    '''
    def __init__(self, type=BlenderNodeType.NONE, id=''):
        self.id = id
        self.parent = None
        self.children = []
        self.type = type

    def __repr__(self):
        r = f'BlenderNode({self.id}) [\n'
        for child in self.children:
            r += f'{child}\n'
        r += ']'
        return r

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

class BlenderSceneNode(BlenderNode):
    ''' Define a Blender node containing scene data '''
    def __init__(self, id=''):
        super(BlenderSceneNode, self).__init__(type=BlenderNodeType.SCENE, id=id)

    def __repr__(self):
        r = f'BlenderSceneNode({self.id}) [\n'
        for child in self.children:
            r += f'{child}\n'
        r += ']'
        return r

class BlenderMaterialNode(BlenderNode):
    ''' Define a Blender node containing material data '''
    def __init__(self, id=''):
        super(BlenderMaterialNode, self).__init__(type=BlenderNodeType.MATERIAL, id=id)
        self.bl_mat = None

    def __repr__(self):
        r = f'BlenderMaterialNode({self.id}) [\n'
        for child in self.children:
            r += f'{child}\n'
        r += ']'
        return r

class BlenderWorldNode(BlenderNode):
    ''' Define a Blender node containing world data '''
    def __init__(self, id=''):
        super(BlenderWorldNode, self).__init__(type=BlenderNodeType.WORLD, id=id)
        self.bl_world = None

    def __repr__(self):
        r = f'BlenderWorldNode({self.id}) [\n'
        for child in self.children:
            r += f'{child}\n'
        r += ']'
        return r

class BlenderImageNode(BlenderNode):
    ''' Define a Blender node containing image data '''
    def __init__(self, id=''):
        super(BlenderImageNode, self).__init__(type=BlenderNodeType.IMAGE, id=id)
        self.bl_image = None
        self.mi_props = None

    def __repr__(self):
        r = f'BlenderImageNode({self.id}) [\n'
        for child in self.children:
            r += f'{child}\n'
        r += ']'
        return r

class BlenderObjectNodeType(Enum):
    SHAPE = 0,
    CAMERA = 1,
    LIGHT = 2,

class BlenderObjectNode(BlenderNode):
    ''' Define a Blender data node containing Blender object data '''
    def __init__(self, id=''):
        super(BlenderObjectNode, self).__init__(type=BlenderNodeType.OBJECT, id=id)
        self.obj_type = None
        self.bl_data = None
        self.world_matrix = None

    def __repr__(self):
        r = f'BlenderObjectNode({self.id}, {self.obj_type}) [\n'
        for child in self.children:
            r += f'{child}\n'
        r += ']'
        return r

    def is_object_type(self, type: BlenderObjectNodeType):
        return self.obj_type == type

class BlenderPropertiesNodeType(Enum):
    FILM = 0,
    INTEGRATOR = 1,
    RFILTER = 2,
    SAMPLER = 3,

class BlenderPropertiesNode(BlenderNode):
    ''' Define a Blender data node containing Mitsuba properties.
    These properties will be parsed as part of the scene's post-processing stage.
    '''
    def __init__(self, id=''):
        super(BlenderPropertiesNode, self).__init__(type=BlenderNodeType.PROPERTIES, id=id)
        self.prop_type = None
        self.mi_props = None

    def __repr__(self):
        r = f'BlenderPropertiesNode({self.id}, {self.prop_type}) [\n'
        for child in self.children:
            r += f'{child}\n'
        r += ']'
        return r

def create_blender_node(node_type=BlenderNodeType.NONE, id=''):
    if node_type == BlenderNodeType.NONE:
        return BlenderNode(id=id)
    elif node_type == BlenderNodeType.SCENE:
        return BlenderSceneNode(id=id)
    elif node_type == BlenderNodeType.MATERIAL:
        return BlenderMaterialNode(id=id)
    elif node_type == BlenderNodeType.OBJECT:
        return BlenderObjectNode(id=id)
    elif node_type == BlenderNodeType.PROPERTIES:
        return BlenderPropertiesNode(id=id)
    elif node_type == BlenderNodeType.WORLD:
        return BlenderWorldNode(id=id)
    elif node_type == BlenderNodeType.IMAGE:
        return BlenderImageNode(id=id)
    else:
        return None

class MitsubaScenePropertiesIterator:
    """ Iterator for Mitsuba properties. Implement filtering based on object class type """
    def __init__(self, props):
        self._objects = list(props.objects.items())
        self._index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._index < len(self._objects):
            _, (cls, prop) = self._objects[self._index]
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

    def get_with_id(self, id: str):
        ''' Get the property of an object with a certain id '''
        if id not in self.objects:
            return (None, None)
        return self.objects[id]

    def get_with_id_and_class(self, id: str, cls: str):
        ''' Get the property of an object with a certain id and class type '''
        if id not in self.objects:
            return None
        cls_, props = self.objects[id]
        if cls_ != cls:
            return None
        return props

    def get_first_of_class(self, cls):
        ''' Get the first properties in the object list that if of a certain class '''
        for (id, (class_, prop)) in self.objects.items():
            if cls == class_:
                return (id, prop)
        return (None, None)

class MitsubaSceneImportContext:
    ''' Define a context for the Mitsuba scene importer '''
    def __init__(self, bl_context, bl_scene, bl_collection, filepath, mi_scene_props, axis_matrix, with_cycles_nodes):
        self.bl_context = bl_context
        self.bl_scene = bl_scene
        self.bl_collection = bl_collection
        self.filepath = filepath
        self.directory, _ = os.path.split(self.filepath)
        self.mi_scene_props = mi_scene_props
        self.axis_matrix = axis_matrix
        self.axis_matrix_inv = axis_matrix.inverted()
        self.with_cycles_nodes = with_cycles_nodes
        self.bl_material_cache = {}
        self.bl_image_cache = {}

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
        if id not in self.bl_material_cache:
            self.bl_material_cache[id] = bl_mat

    def get_bl_material(self, id):
        if id not in self.bl_material_cache:
            return None
        return self.bl_material_cache[id]

    def register_bl_image(self, id, bl_image):
        if id not in self.bl_image_cache:
            self.bl_image_cache[id] = bl_image

    def get_bl_image(self, id):
        if id not in self.bl_image_cache:
            return None
        return self.bl_image_cache[id]
