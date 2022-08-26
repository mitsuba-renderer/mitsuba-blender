import bpy
from bpy.props import PointerProperty, EnumProperty, BoolProperty
from ..base import MitsubaNode

class MitsubaNodeBitmapTexture(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba bitmap texture
    '''
    bl_idname = 'MitsubaNodeBitmapTexture'
    bl_label = 'Bitmap Texture'
    bl_width_default = 200

    image: PointerProperty(name="Image", type=bpy.types.Image)

    filter_type_enum_items = (
        ('bilinear', 'Bilinear', '', 0),
        ('nearest', 'Nearest', '', 1),
    )
    filter_type: EnumProperty(items=filter_type_enum_items, name='Filter Type', default='bilinear')

    wrap_mode_enum_items = (
        ('repeat', 'Repeat', '', 0),
        ('mirror', 'Mirror', '', 1),
        ('clamp', 'Clamp', '', 0),
    )
    wrap_mode: EnumProperty(items=wrap_mode_enum_items, name='Wrap Mode', default='repeat')

    raw: BoolProperty(name='Raw', default=False)

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocket2DTransform', 'Transform')

        self.outputs.new('MitsubaSocketColorTexture', 'Color')

    def draw_label(self):
        return self.image.name if self.image else self.bl_label

    def draw_buttons(self, context, layout):
        layout.template_ID(self, 'image', open='image.open', new='image.new')

        col = layout.column()
        col.active = self.image is not None

        row = col.row()
        row.prop(self, 'raw')

        col.prop(self, 'filter_type', text='')
        col.prop(self, 'wrap_mode', text='')
            
        if self.image:
            col.prop(self.image, 'source', text='')

            if self.image.source in { 'MOVIE', 'TILED' }:
                col.label(text="Unsupported Source!", icon='X')

    def to_dict(self, export_context):
        params = { 'type': 'bitmap' }
        if self.image is not None:
            params['filename'] = export_context.export_texture(self.image)
        else:
            export_context.log('Bitmap node does not have a selected image to export', 'ERROR')
            return None
        params['filter_type'] = self.filter_type
        params['wrap_mode'] = self.wrap_mode
        params['raw'] = self.raw
        transform = self.inputs['Transform'].to_dict(export_context)
        if transform is not None:
            params['to_uv'] = transform
        return params
