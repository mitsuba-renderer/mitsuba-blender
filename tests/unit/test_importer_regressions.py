"""Regression tests for importer crashes inherited from PR #137."""

import bpy
import numpy as np


def _write_png(path, size=4):
    image = bpy.data.images.new('png-writer', size, size, alpha=True)
    values = np.linspace(0.0, 1.0, size * size * 4, dtype=np.float32)
    image.pixels.foreach_set(values)
    image.filepath_raw = str(path)
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)


def _write_ply(path):
    path.write_text('''ply
format ascii 1.0
element vertex 3
property float x
property float y
property float z
element face 1
property list uchar int vertex_indices
end_header
0 0 0
1 0 0
0 1 0
3 0 1 2
''')


def _import_xml(tmp_path, xml_body):
    xml = f'<scene version="3.0.0">\n{xml_body}\n</scene>'
    scene_file = tmp_path / 'scene.xml'
    scene_file.write_text(xml)
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == {'FINISHED'}


def _mesh_materials():
    return [obj.active_material for obj in bpy.data.objects
            if obj.type == 'MESH' and obj.active_material is not None]


def _find_nodes(bl_mat, bl_idname):
    return [node for node in bl_mat.node_tree.nodes if node.bl_idname == bl_idname]


def test_area_emitter_float_radiance(mi_addon, fresh_scene, tmp_path):
    # A non-Color radiance used to leave 'radiance'/'strength' unbound
    _import_xml(tmp_path, '''
        <shape type="rectangle">
            <emitter type="area"><float name="radiance" value="5.0"/></emitter>
            <bsdf type="diffuse"/>
        </shape>''')

    mats = _mesh_materials()
    assert len(mats) == 1
    emission_nodes = _find_nodes(mats[0], 'ShaderNodeEmission')
    assert len(emission_nodes) == 1
    assert emission_nodes[0].inputs['Strength'].default_value == 5.0
    assert tuple(emission_nodes[0].inputs['Color'].default_value)[:3] == (1.0, 1.0, 1.0)


def test_mask_with_default_diffuse_child(mi_addon, fresh_scene, tmp_path):
    # The mask fast path called get_texture('reflectance') on a diffuse
    # child without an explicit reflectance, which crashes
    _import_xml(tmp_path, '''
        <bsdf type="mask" id="mat-masked">
            <float name="opacity" value="0.5"/>
            <bsdf type="diffuse"/>
        </bsdf>
        <shape type="rectangle">
            <ref id="mat-masked"/>
        </shape>''')

    mats = _mesh_materials()
    assert len(mats) == 1
    # The default 0.5 reflectance is not black, so the material is a mix
    # of a transparent and a diffuse BSDF
    assert len(_find_nodes(mats[0], 'ShaderNodeMixShader')) == 1
    assert len(_find_nodes(mats[0], 'ShaderNodeBsdfTransparent')) == 1


def test_mask_opacity_not_mutated(mi_addon, fresh_scene, tmp_path):
    # Inverting the opacity in place mutated the parser state, so a second
    # conversion of the same material saw an already-inverted value. The
    # emissive shape bypasses the material cache and triggers a reconversion.
    _import_xml(tmp_path, '''
        <bsdf type="mask" id="mat-masked">
            <rgb name="opacity" value="0.3 0.3 0.3"/>
            <bsdf type="diffuse"><rgb name="reflectance" value="0 0 0"/></bsdf>
        </bsdf>
        <shape type="rectangle">
            <ref id="mat-masked"/>
        </shape>
        <shape type="rectangle">
            <ref id="mat-masked"/>
            <emitter type="area"><rgb name="radiance" value="1 1 1"/></emitter>
        </shape>''')

    mats = _mesh_materials()
    assert len(mats) == 2
    for mat in mats:
        transparent_nodes = _find_nodes(mat, 'ShaderNodeBsdfTransparent')
        assert len(transparent_nodes) == 1
        color = tuple(transparent_nodes[0].inputs['Color'].default_value)[:3]
        assert all(abs(c - 0.7) < 1e-5 for c in color)


def test_emitter_shape_without_bsdf(mi_addon, fresh_scene, tmp_path):
    # A shape with an emitter but no BSDF used to lose its emitter. The
    # cube cannot become a Blender light, so it keeps an emissive material.
    _import_xml(tmp_path, '''
        <shape type="cube">
            <emitter type="area"><rgb name="radiance" value="2 2 2"/></emitter>
        </shape>''')

    mats = _mesh_materials()
    assert len(mats) == 1
    emission_nodes = _find_nodes(mats[0], 'ShaderNodeEmission')
    assert len(emission_nodes) == 1
    assert emission_nodes[0].inputs['Strength'].default_value == 2.0


def test_conductor_with_textured_property(mi_addon, fresh_scene, tmp_path):
    # Copying a ResolvedReference property into the reflectance-probing
    # load_dict call followed a dangling parser-state index and killed
    # the whole Blender session with a segfault
    _write_png(tmp_path / 'tex.png')
    _import_xml(tmp_path, '''
        <shape type="rectangle">
            <bsdf type="roughconductor" id="mat-cond">
                <texture type="bitmap" name="specular_reflectance">
                    <string name="filename" value="tex.png"/>
                </texture>
            </bsdf>
        </shape>''')

    mats = _mesh_materials()
    assert len(mats) == 1
    assert len(_find_nodes(mats[0], 'ShaderNodeBsdfAnisotropic')) == 1


def test_area_emitter_rectangle_becomes_light(mi_addon, fresh_scene,
                                              tmp_path):
    import math

    _import_xml(tmp_path, '''
        <shape type="rectangle">
            <emitter type="area"><rgb name="radiance" value="2 2 2"/></emitter>
        </shape>''')

    bl_lights = [obj for obj in bpy.data.objects if obj.type == 'LIGHT']
    assert len(bl_lights) == 1
    data = bl_lights[0].data
    assert data.type == 'AREA'
    assert data.shape == 'RECTANGLE'
    # A Mitsuba rectangle spans [-1, 1]: power = radiance * pi * area
    assert abs(data.energy - 2.0 * math.pi * 4.0) < 1e-3
    assert not _mesh_materials()


def _path_tag_scene(tmp_path):
    '''A scene whose shape, texture and envmap files live in a directory
    that only a <path> tag makes visible.'''
    assets = tmp_path / 'assets'
    assets.mkdir()
    _write_ply(assets / 'tri.ply')
    _write_png(assets / 'tex.png')
    return '''
        <path value="assets"/>
        <shape type="ply">
            <string name="filename" value="tri.ply"/>
            <bsdf type="diffuse">
                <texture type="bitmap" name="reflectance">
                    <string name="filename" value="tex.png"/>
                </texture>
            </bsdf>
        </shape>
        <emitter type="envmap">
            <string name="filename" value="tex.png"/>
        </emitter>'''


def test_path_tag_does_not_leak_into_file_resolver(mi_addon, fresh_scene,
                                                   tmp_path):
    # parse_file prepends <path> directories to the session-global file
    # resolver; without a save/restore they polluted later exports/renders
    import mitsuba as mi
    body = _path_tag_scene(tmp_path)
    before = [str(p) for p in mi.file_resolver()]
    _import_xml(tmp_path, body)
    assert [str(p) for p in mi.file_resolver()] == before


def test_path_tag_directories_resolve_filenames(mi_addon, fresh_scene,
                                                tmp_path):
    # Filenames were joined against the XML directory only, so files that
    # relied on a <path> directory came back as empty placeholders,
    # missing textures and an error-colored world
    _import_xml(tmp_path, _path_tag_scene(tmp_path))

    meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
    assert len(meshes) == 1
    assert len(meshes[0].data.vertices) == 3

    mats = _mesh_materials()
    assert len(mats) == 1
    tex_nodes = _find_nodes(mats[0], 'ShaderNodeTexImage')
    assert len(tex_nodes) == 1
    assert tex_nodes[0].image is not None

    world_nodes = [node for node in bpy.context.scene.world.node_tree.nodes
                   if node.bl_idname == 'ShaderNodeTexEnvironment']
    assert len(world_nodes) == 1
    assert world_nodes[0].image is not None


def test_import_emissive_under_spectral_variant(mi_addon, fresh_scene,
                                                tmp_path):
    # Splitting radiance into color/strength went through
    # get_emissive_texture, which instantiates a plugin from the current
    # variant; under a spectral variant that is not an
    # SRGBReflectanceSpectrum and a bare AssertionError broke the import
    import mitsuba as mi
    import pytest
    if 'scalar_spectral' not in mi.variants():
        pytest.skip('scalar_spectral variant not available')
    variant_before = mi.variant()
    mi.set_variant('scalar_spectral')
    try:
        _import_xml(tmp_path, '''
            <shape type="cube">
                <emitter type="area"><rgb name="radiance" value="2 2 2"/></emitter>
                <bsdf type="diffuse"/>
            </shape>''')

        mats = _mesh_materials()
        assert len(mats) == 1
        emission_nodes = _find_nodes(mats[0], 'ShaderNodeEmission')
        assert len(emission_nodes) == 1
        assert emission_nodes[0].inputs['Strength'].default_value == 2.0
    finally:
        mi.set_variant(variant_before)
