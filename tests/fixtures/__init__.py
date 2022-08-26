import bpy

import pytest
import numpy as np

import os

################################
##  ResourceResolver fixture  ##
################################

class ResourceResolver:
    def __init__(self, function_path, function_name):
        self.root = os.path.dirname(function_path)
        self.function_name = function_name

    def get_absolute_resource_path(self, relative_path):
        return os.path.join(self.root, relative_path)

    def ensure_resource_dir(self, relative_dir):
        absolute_dir = self.get_absolute_resource_path(relative_dir)
        os.makedirs(absolute_dir, exist_ok=True)
        return absolute_dir

    def ensure_output_dir(self):
        return self.ensure_resource_dir(f'out/{self.function_name}')

@pytest.fixture
def resource_resolver(request):
    return ResourceResolver(request.path, request.node.name.split('[')[0])

##################################
##  MitsubaSceneParser fixture  ##
##################################

class MitsubaPropsWrapper:
    def __init__(self, props):
        self.props = props

    def __repr__(self):
        return str(self.props)

    def get_props_by_name(self, plugin_name):
        for _, props in self.props:
            if props.plugin_name() == plugin_name:
                return props
        return None

    def get_props_by_id(self, plugin_id):
        for _, props in self.props:
            if props.id() == plugin_id:
                return props
        return None

class MitsubaSceneParser:
    def load_xml(self, scene_file):
        import mitsuba
        props = mitsuba.xml_to_props(scene_file)
        return MitsubaPropsWrapper(props)

@pytest.fixture
def mitsuba_scene_parser():
    return MitsubaSceneParser()

####################################
##  MitsubaSceneRenderer fixture  ##
####################################

class MitsubaSceneRenderer:

    def _bitmap_extract(self, bmp, require_variance=True):
        from mitsuba import Bitmap, Struct
        """Extract different channels from moment integrator AOVs"""
        # AVOs from the moment integrator are in XYZ (float32)
        split = bmp.split()
        if len(split) == 1:
            if require_variance:
                raise RuntimeError(
                    'Could not extract variance image from bitmap. '
                    'Did you wrap the integrator into a `moment` integrator?\n{}'.format(bmp))
            b_root = split[0][1]
            if b_root.channel_count() >= 3 and b_root.pixel_format() != Bitmap.PixelFormat.XYZ:
                b_root = b_root.convert(Bitmap.PixelFormat.XYZ, Struct.Type.Float32, False)
            return np.array(b_root, copy=True), None
        else:
            img = np.array(split[1][1], copy=False)
            img_m2 = np.array(split[2][1], copy=False)
            return img, img_m2 - img * img

    def render_scene(self, scene_file, **kwargs):
        from mitsuba import load_file

        scene = load_file(scene_file, **kwargs)
        scene.integrator().render(scene, seed=0, develop=False)

        bmp = scene.sensors()[0].film().bitmap(raw=False)
        img, var_img = self._bitmap_extract(bmp)

        return img, var_img

@pytest.fixture
def mitsuba_scene_renderer():
    return MitsubaSceneRenderer()

###################################
##  MitsubaRenderTester fixture  ##
###################################

class MitsubaRenderTester:
    def __init__(self, mitsuba_scene_renderer):
        self.scene_renderer = mitsuba_scene_renderer

    def z_test(self, mean, sample_count, reference, reference_var):
        import drjit as dr
        from drjit.scalar import ArrayXf as Float
        """Implementation of the Z-test statistical test"""
        # Sanitize the variance images
        reference_var = np.maximum(reference_var, 1e-4)

        # Compute Z statistic
        z_stat = np.abs(mean - reference) * np.sqrt(sample_count / reference_var)

        # Cumulative distribution function of the standard normal distribution
        def stdnormal_cdf(x):
            shape = x.shape
            cdf = (1.0 - dr.erf(-Float(x.flatten()) / dr.sqrt(2.0))) * 0.5
            return np.array(cdf).reshape(shape)

        # Compute p-value
        p_value = 2.0 * (1.0 - stdnormal_cdf(z_stat))

        return p_value

    def xyz_to_rgb_bmp(self, arr):
        ''' Convert an XYZ image to RGB '''
        from mitsuba import Bitmap, Struct
        xyz_bmp = Bitmap(arr, Bitmap.PixelFormat.XYZ)
        return xyz_bmp.convert(Bitmap.PixelFormat.RGB, Struct.Type.Float32, False)

    def compare_scenes(self, xml_ref, xml_out, spp, resolution, output_dir, significance_level=0.01):
        from mitsuba import Bitmap

        pixel_count = resolution[0] * resolution[1]
        ref_img, ref_img_var = self.scene_renderer.render_scene(xml_ref, spp=spp, resx=resolution[0], resy=resolution[1])
        img, _ = self.scene_renderer.render_scene(xml_out, spp=spp, resx=resolution[0], resy=resolution[1])

        p_value = self.z_test(img, spp, ref_img, ref_img_var)

        # Apply the Sidak correction term, since we'll be conducting multiple independent
        # hypothesis tests. This accounts for the fact that the probability of a failure
        # increases quickly when several hypothesis tests are run in sequence.
        alpha = 1.0 - (1.0 - significance_level) ** (1.0 / pixel_count)

        success = (p_value > alpha)

        ref_img_bmp = self.xyz_to_rgb_bmp(ref_img)
        img_bmp = self.xyz_to_rgb_bmp(img)
        err_bmp = 0.02 * np.array(img_bmp)
        err_bmp[~success] = 1.0
        err_bmp = Bitmap(err_bmp)
        
        ref_img_bmp.write(os.path.join(output_dir, 'ref.exr'))
        img_bmp.write(os.path.join(output_dir, 'out.exr'))
        err_bmp.write(os.path.join(output_dir, 'err.exr'))

        return np.count_nonzero(success) / 3 >= 0.9975 * pixel_count

@pytest.fixture
def mitsuba_scene_ztest(mitsuba_scene_renderer):
    return MitsubaRenderTester(mitsuba_scene_renderer)

###################################
##  MitsubaParserTester fixture  ##
###################################

class MitsubaParserTester:
    def __init__(self, resolver, parser):
        self.resolver = resolver
        self.parser = parser

    def _check_plugin(self, ref_props, output_props, plugin_name):
        from mitsuba import Properties, traverse

        ref_plugin_props = ref_props.get_props_by_name(plugin_name)
        assert ref_plugin_props
        output_plugin_props = output_props.get_props_by_name(plugin_name)
        assert output_plugin_props

        for ref_plugin_prop_name in ref_plugin_props.property_names():
            ref_plugin_prop = ref_plugin_props.get(ref_plugin_prop_name)
            ref_plugin_prop_type = ref_plugin_props.type(ref_plugin_prop_name)

            if ref_plugin_prop_type == Properties.Type.NamedReference:
                ref_other_plugin_props = ref_props.get_props_by_id(ref_plugin_prop)
                self._check_plugin(ref_props, output_props, ref_other_plugin_props.plugin_name())
            elif ref_plugin_prop_type == Properties.Type.Object:
                assert output_plugin_props.has_property(ref_plugin_prop_name)
                output_plugin_prop = output_plugin_props.get(ref_plugin_prop_name)
                ref_plugin_prop_params = traverse(ref_plugin_prop)
                output_plugin_prop_params = traverse(output_plugin_prop)
                for (key, value) in ref_plugin_prop_params.items():
                    assert key in output_plugin_prop_params
                    assert value == output_plugin_prop_params[key]
            else:
                assert output_plugin_props.has_property(ref_plugin_prop_name)
                output_plugin_prop = output_plugin_props.get(ref_plugin_prop_name)
                if ref_plugin_prop != output_plugin_prop:
                    print(ref_plugin_prop)
                    print(output_plugin_prop)
                assert ref_plugin_prop == output_plugin_prop

    def check_scene_plugin(self, scene_file, plugin_name):
        ref_scene_file = self.resolver.get_absolute_resource_path(scene_file)
        ref_scene_name, _ = os.path.splitext(os.path.basename(ref_scene_file))
        test_output_dir = self.resolver.ensure_output_dir()
        output_scene_file = os.path.join(test_output_dir, f'{ref_scene_name}_out.xml')

        assert bpy.ops.mitsuba.scene_import(filepath=ref_scene_file, create_cycles_node_tree=False) == {'FINISHED'}
        assert bpy.ops.mitsuba.scene_export(filepath=output_scene_file, ignore_background=True) == {'FINISHED'}

        ref_props = self.parser.load_xml(ref_scene_file)
        output_props = self.parser.load_xml(output_scene_file)
        
        self._check_plugin(ref_props, output_props, plugin_name)

@pytest.fixture
def mitsuba_parser_tester(resource_resolver, mitsuba_scene_parser):
    return MitsubaParserTester(resource_resolver, mitsuba_scene_parser)
