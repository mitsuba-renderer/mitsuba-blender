'''Group-boundary resolution: the cases that distinguish a correct
instance-path fix from one that only works at depth zero.'''

import importlib
import sys

import bpy
import pytest


@pytest.fixture(scope='session')
def eval_mod(mi_addon):
    return importlib.import_module(
        f'{mi_addon}.convert.export.materials._eval')


@pytest.fixture(scope='session')
def registry(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.materials')


@pytest.fixture
def export_ctx(mi_addon, tmp_path):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    ctx = sys.modules[mi_addon].io.exporter.export_context.ExportContext()
    ctx.directory = str(tmp_path)
    return ctx

def _float_group(name, factor=3.0):
    '''A node group computing Amount * factor, as a reusable tree.'''
    tree = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    tree.interface.new_socket('Amount', in_out='INPUT',
                              socket_type='NodeSocketFloat')
    tree.interface.new_socket('Result', in_out='OUTPUT',
                              socket_type='NodeSocketFloat')
    g_in = tree.nodes.new('NodeGroupInput')
    g_out = tree.nodes.new('NodeGroupOutput')
    math = tree.nodes.new('ShaderNodeMath')
    math.operation = 'MULTIPLY'
    math.inputs[1].default_value = factor
    tree.links.new(g_in.outputs['Amount'], math.inputs[0])
    tree.links.new(math.outputs['Value'], g_out.inputs['Result'])
    return tree


def _instance(tree, node_tree, amount):
    '''A group node in `node_tree` using `tree`, with Amount set.'''
    node = node_tree.nodes.new('ShaderNodeGroup')
    node.node_tree = tree
    node.inputs['Amount'].default_value = amount
    return node


def _material():
    b_mat = bpy.data.materials.new('GroupTest')
    b_mat.use_nodes = True
    return b_mat, b_mat.node_tree


def test_shared_tree_resolves_per_instance(fresh_scene, export_ctx, eval_mod):
    '''Two group nodes sharing one tree with different arguments. The inner
    GROUP_INPUT node is the same object for both, so nothing but the group
    instance path can tell the two apart.'''
    b_mat, tree = _material()
    group = _float_group('Shared')
    a = _instance(group, tree, 2.0)
    b = _instance(group, tree, 5.0)

    add = tree.nodes.new('ShaderNodeMath')
    add.operation = 'ADD'
    tree.links.new(a.outputs['Result'], add.inputs[0])
    tree.links.new(b.outputs['Result'], add.inputs[1])

    emission = tree.nodes.new('ShaderNodeEmission')
    tree.links.new(add.outputs['Value'], emission.inputs['Strength'])

    result = eval_mod.resolve(export_ctx, emission.inputs['Strength'])
    assert isinstance(result, eval_mod.Constant)
    assert result.value == pytest.approx(21.0)   # 2*3 + 5*3


def test_nested_groups_unwind_in_order(fresh_scene, export_ctx, eval_mod):
    '''A group inside a group: two pushes, two pops, landing back in the
    root tree at the right socket.'''
    b_mat, tree = _material()
    inner = _float_group('Inner', factor=3.0)

    outer = bpy.data.node_groups.new('Outer', 'ShaderNodeTree')
    outer.interface.new_socket('Amount', in_out='INPUT',
                               socket_type='NodeSocketFloat')
    outer.interface.new_socket('Result', in_out='OUTPUT',
                               socket_type='NodeSocketFloat')
    o_in = outer.nodes.new('NodeGroupInput')
    o_out = outer.nodes.new('NodeGroupOutput')
    inner_node = outer.nodes.new('ShaderNodeGroup')
    inner_node.node_tree = inner
    outer.links.new(o_in.outputs['Amount'], inner_node.inputs['Amount'])
    outer.links.new(inner_node.outputs['Result'], o_out.inputs['Result'])

    outer_node = _instance(outer, tree, 0.0)
    value = tree.nodes.new('ShaderNodeValue')
    value.outputs['Value'].default_value = 2.0
    tree.links.new(value.outputs['Value'], outer_node.inputs['Amount'])

    emission = tree.nodes.new('ShaderNodeEmission')
    tree.links.new(outer_node.outputs['Result'],
                   emission.inputs['Strength'])

    result = eval_mod.resolve(export_ctx, emission.inputs['Strength'])
    assert isinstance(result, eval_mod.Constant)
    assert result.value == pytest.approx(6.0)


def test_shader_socket_crosses_group_boundary(fresh_scene, export_ctx,
                                              registry):
    '''A group with a Shader-type interface: the Add Shader converter is
    reached inside the group and must trace one of its inputs back out to
    the Diffuse node in the root tree.'''
    b_mat, tree = _material()
    group = bpy.data.node_groups.new('ShaderGroup', 'ShaderNodeTree')
    group.interface.new_socket('Shader', in_out='INPUT',
                               socket_type='NodeSocketShader')
    group.interface.new_socket('Shader', in_out='OUTPUT',
                               socket_type='NodeSocketShader')
    g_in = group.nodes.new('NodeGroupInput')
    g_out = group.nodes.new('NodeGroupOutput')
    add = group.nodes.new('ShaderNodeAddShader')
    emission = group.nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (1.0, 0.0, 0.0, 1.0)
    emission.inputs['Strength'].default_value = 4.0
    group.links.new(g_in.outputs['Shader'], add.inputs[0])
    group.links.new(emission.outputs['Emission'], add.inputs[1])
    group.links.new(add.outputs['Shader'], g_out.inputs['Shader'])

    group_node = tree.nodes.new('ShaderNodeGroup')
    group_node.node_tree = group
    diffuse = tree.nodes.new('ShaderNodeBsdfDiffuse')
    tree.links.new(diffuse.outputs['BSDF'], group_node.inputs['Shader'])

    output = tree.get_output_node('CYCLES')
    for link in list(output.inputs['Surface'].links):
        tree.links.remove(link)
    tree.links.new(group_node.outputs['Shader'], output.inputs['Surface'])

    result = registry.convert_material(export_ctx, b_mat)
    # The BSDF came from outside the group, the emitter from inside
    assert result['bsdf'] is not None
    assert result['bsdf'] != registry.FALLBACK_BSDF
    assert result['emitter'] is not None
    assert result['emitter']['type'] == 'area'