"""Tests for the Mitsuba texture and normal/bump map importers."""

import bpy
import numpy as np
import pytest


def write_png(path, size=4):
    image = bpy.data.images.new('png-writer', size, size, alpha=True)
    values = np.linspace(0.0, 1.0, size * size * 4, dtype=np.float32)
    image.pixels.foreach_set(values)
    image.filepath_raw = str(path)
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)


def import_xml(tmp_path, xml_body):
    xml = f'<scene version="3.0.0">\n{xml_body}\n</scene>'
    scene_file = tmp_path / 'scene.xml'
    scene_file.write_text(xml)
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}


def imported_material(name):
    b_mat = bpy.data.materials[name]
    surface = b_mat.node_tree.get_output_node('CYCLES').inputs['Surface']
    assert surface.is_linked
    return b_mat, surface.links[0].from_node


def source_node(socket):
    assert socket.is_linked
    return socket.links[0].from_node


def diffuse_with_reflectance(tmp_path, texture_xml, mat_id='mat-tex'):
    import_xml(tmp_path, f'''
        <shape type="sphere">
            <bsdf type="diffuse" id="{mat_id}">
                {texture_xml}
            </bsdf>
        </shape>''')
    _, node = imported_material(mat_id)
    assert node.bl_idname == 'ShaderNodeBsdfDiffuse'
    return node


##############
##  Bitmap  ##
##############

def test_import_bitmap(mi_addon, fresh_scene, tmp_path):
    write_png(tmp_path / 'tex.png')
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="bitmap" name="reflectance">
            <string name="filename" value="tex.png"/>
            <boolean name="raw" value="true"/>
            <string name="wrap_mode" value="clamp"/>
            <string name="filter_type" value="nearest"/>
        </texture>''')

    tex = source_node(diffuse.inputs['Color'])
    assert tex.bl_idname == 'ShaderNodeTexImage'
    assert tuple(tex.image.size) == (4, 4)
    assert tex.image.colorspace_settings.name == 'Non-Color'
    assert tex.extension == 'EXTEND'
    assert tex.interpolation == 'Closest'
    # The mapping node carries the differing image row convention
    mapping = source_node(tex.inputs['Vector'])
    assert tuple(mapping.inputs['Location'].default_value) == \
        pytest.approx((0.0, 1.0, 0.0))
    assert tuple(mapping.inputs['Scale'].default_value) == \
        pytest.approx((1.0, -1.0, 1.0))


def test_import_bitmap_missing_file(mi_addon, fresh_scene, tmp_path):
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="bitmap" name="reflectance">
            <string name="filename" value="not-there.png"/>
        </texture>''')

    # The missing texture falls back to the default reflectance
    assert not diffuse.inputs['Color'].is_linked
    assert tuple(diffuse.inputs['Color'].default_value) == \
        pytest.approx((0.8, 0.8, 0.8, 1.0))


def test_import_bitmap_to_uv(mi_addon, fresh_scene, tmp_path):
    # The Mapping node composes the to_uv transform with the mirrored v axis
    write_png(tmp_path / 'tex.png')
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="bitmap" name="reflectance">
            <string name="filename" value="tex.png"/>
            <transform name="to_uv"><scale x="2" y="2"/></transform>
        </texture>''')

    tex = source_node(diffuse.inputs['Color'])
    mapping = source_node(tex.inputs['Vector'])
    assert mapping.bl_idname == 'ShaderNodeMapping'
    assert tuple(mapping.inputs['Location'].default_value) == \
        pytest.approx((0.0, 1.0, 0.0))
    assert tuple(mapping.inputs['Scale'].default_value) == \
        pytest.approx((2.0, -2.0, 1.0))
    coords = source_node(mapping.inputs['Vector'])
    assert coords.bl_idname == 'ShaderNodeTexCoord'


def test_import_bitmap_mirroring_to_uv(mi_addon, fresh_scene, tmp_path):
    # A to_uv that already mirrors v cancels against the row convention, so
    # no Mapping node is needed at all
    write_png(tmp_path / 'tex.png')
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="bitmap" name="reflectance">
            <string name="filename" value="tex.png"/>
            <transform name="to_uv">
                <matrix value="1 0 0 0 -1 1 0 0 1"/>
            </transform>
        </texture>''')

    tex = source_node(diffuse.inputs['Color'])
    assert not tex.inputs['Vector'].is_linked


def test_import_bitmap_is_cached(mi_addon, fresh_scene, tmp_path):
    write_png(tmp_path / 'tex.png')
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="bumpmap" id="mat-cache">
                <texture type="bitmap">
                    <string name="filename" value="tex.png"/>
                </texture>
                <bsdf type="diffuse">
                    <texture type="bitmap" name="reflectance">
                        <string name="filename" value="tex.png"/>
                    </texture>
                </bsdf>
            </bsdf>
        </shape>''')

    b_mat, _ = imported_material('mat-cache')
    tex_nodes = [n for n in b_mat.node_tree.nodes
                 if n.bl_idname == 'ShaderNodeTexImage']
    assert len(tex_nodes) == 2
    assert tex_nodes[0].image is tex_nodes[1].image
    assert len([i for i in bpy.data.images
                if i.name.startswith('tex')]) == 1


####################
##  Checkerboard  ##
####################

def test_import_checkerboard(mi_addon, fresh_scene, tmp_path):
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="checkerboard" name="reflectance">
            <rgb name="color0" value="0 0 1"/>
            <rgb name="color1" value="1 0 0"/>
            <transform name="to_uv"><scale x="2" y="2"/></transform>
        </texture>''')

    checker = source_node(diffuse.inputs['Color'])
    assert checker.bl_idname == 'ShaderNodeTexChecker'
    assert tuple(checker.inputs['Color1'].default_value) == \
        pytest.approx((0.0, 0.0, 1.0, 1.0))
    assert tuple(checker.inputs['Color2'].default_value) == \
        pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert checker.inputs['Scale'].default_value == pytest.approx(4.0)
    assert not checker.inputs['Vector'].is_linked


def test_import_checkerboard_general_to_uv(mi_addon, fresh_scene, tmp_path):
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="checkerboard" name="reflectance">
            <transform name="to_uv"><scale x="1.5" y="1.5"/></transform>
        </texture>''')

    # An isotropic, unshifted pattern needs no Mapping node at all
    checker = source_node(diffuse.inputs['Color'])
    assert checker.inputs['Scale'].default_value == pytest.approx(3.0)
    assert not checker.inputs['Vector'].is_linked


#############
##  Scale  ##
#############

def test_import_scale_texture(mi_addon, fresh_scene, tmp_path):
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="scale" name="reflectance">
            <texture type="checkerboard" name="texture"/>
            <float name="scale" value="0.5"/>
        </texture>''')

    mix = source_node(diffuse.inputs['Color'])
    assert mix.bl_idname == 'ShaderNodeMix'
    assert mix.blend_type == 'MULTIPLY'
    factor = next(s for s in mix.inputs if s.identifier == 'Factor_Float')
    assert factor.default_value == pytest.approx(1.0)
    b_color = next(s for s in mix.inputs if s.identifier == 'B_Color')
    assert tuple(b_color.default_value) == \
        pytest.approx((0.5, 0.5, 0.5, 1.0))
    a_color = next(s for s in mix.inputs if s.identifier == 'A_Color')
    assert source_node(a_color).bl_idname == 'ShaderNodeTexChecker'


######################
##  Mesh attribute  ##
######################

def test_import_mesh_attribute(mi_addon, fresh_scene, tmp_path):
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="mesh_attribute" name="reflectance">
            <string name="name" value="vertex_Col"/>
        </texture>''')

    color = source_node(diffuse.inputs['Color'])
    assert color.bl_idname == 'ShaderNodeVertexColor'
    assert color.layer_name == 'Col'


def test_import_mesh_attribute_generic(mi_addon, fresh_scene, tmp_path):
    diffuse = diffuse_with_reflectance(tmp_path, '''
        <texture type="mesh_attribute" name="reflectance">
            <string name="name" value="temperature"/>
        </texture>''')

    attribute = source_node(diffuse.inputs['Color'])
    assert attribute.bl_idname == 'ShaderNodeAttribute'
    assert attribute.attribute_name == 'temperature'


############################
##  Normal and bump maps  ##
############################

def test_import_normalmap(mi_addon, fresh_scene, tmp_path):
    write_png(tmp_path / 'normal.png')
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="normalmap" id="mat-nm">
                <texture type="bitmap" name="normalmap">
                    <string name="filename" value="normal.png"/>
                    <boolean name="raw" value="true"/>
                </texture>
                <bsdf type="diffuse"/>
            </bsdf>
        </shape>''')

    _, diffuse = imported_material('mat-nm')
    assert diffuse.bl_idname == 'ShaderNodeBsdfDiffuse'
    normal_map = source_node(diffuse.inputs['Normal'])
    assert normal_map.bl_idname == 'ShaderNodeNormalMap'
    tex = source_node(normal_map.inputs['Color'])
    assert tex.bl_idname == 'ShaderNodeTexImage'
    assert tex.image.colorspace_settings.name == 'Non-Color'


def test_import_bumpmap(mi_addon, fresh_scene, tmp_path):
    write_png(tmp_path / 'height.png')
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="bumpmap" id="mat-bump">
                <texture type="bitmap">
                    <string name="filename" value="height.png"/>
                    <boolean name="raw" value="true"/>
                </texture>
                <float name="scale" value="0.6"/>
                <bsdf type="diffuse"/>
            </bsdf>
        </shape>''')

    _, diffuse = imported_material('mat-bump')
    bump = source_node(diffuse.inputs['Normal'])
    assert bump.bl_idname == 'ShaderNodeBump'
    assert bump.inputs['Distance'].default_value == pytest.approx(0.6)
    assert source_node(bump.inputs['Height']).bl_idname == \
        'ShaderNodeTexImage'


def test_import_bumpmap_over_normalmap(mi_addon, fresh_scene, tmp_path):
    write_png(tmp_path / 'normal.png')
    write_png(tmp_path / 'height.png')
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="bumpmap" id="mat-chain">
                <texture type="bitmap">
                    <string name="filename" value="height.png"/>
                </texture>
                <bsdf type="normalmap">
                    <texture type="bitmap" name="normalmap">
                        <string name="filename" value="normal.png"/>
                        <boolean name="raw" value="true"/>
                    </texture>
                    <bsdf type="diffuse"/>
                </bsdf>
            </bsdf>
        </shape>''')

    _, diffuse = imported_material('mat-chain')
    bump = source_node(diffuse.inputs['Normal'])
    assert bump.bl_idname == 'ShaderNodeBump'
    normal_map = source_node(bump.inputs['Normal'])
    assert normal_map.bl_idname == 'ShaderNodeNormalMap'
