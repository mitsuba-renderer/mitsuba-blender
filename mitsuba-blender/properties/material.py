import bpy
from bpy.types import PropertyGroup
from bpy.props import PointerProperty, EnumProperty, FloatProperty

class MitsubaMaterialProps(PropertyGroup):
    '''
    Custom properties for Mitsuba materials
    '''
    node_tree: PointerProperty(name='Node Tree', type=bpy.types.NodeTree)

    @classmethod
    def register(cls):
        bpy.types.Material.mitsuba = PointerProperty(
            name='Mitsuba Material Settings',
            description='Mitsuba material settings',
            type=cls,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Material.mitsuba
