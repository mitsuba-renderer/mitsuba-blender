import pytest
import numpy as np
import bpy

import os

################################
##  ResourceResolver fixture  ##
################################

class ResourceResolver:
    def __init__(self):
        self.root = os.path.join(os.getcwd(), 'tests/res')

    def get_absolute_resource_path(self, relative_path):
        return os.path.join(self.root, relative_path)

    def ensure_resource_dir(self, relative_dir):
        absolute_dir = self.get_absolute_resource_path(relative_dir)
        os.makedirs(absolute_dir, exist_ok=True)
        return absolute_dir
    
    def get_out_path(self):
        return os.path.join(self.root, 'out')
    
    def get_renders_path(self):
        return os.path.join(self.root, 'renders')
    
    def get_scenes_path(self):
        return os.path.join(self.root, 'scenes')

@pytest.fixture
def resource_resolver():
    return ResourceResolver()

##################################
##  MitsubaSceneParser fixture  ##
##################################

class MitsubaSceneParser:
    def __init__(self):
        self.props = None

    def load_xml(self, scene_file):
        import mitsuba as mi

        config = mi.parser.ParserConfig(mi.variant())
        mi_state = mi.parser.parse_file(config, scene_file)
        mi.parser.transform_all(config, mi_state)
        self.state = mi_state

    def get_props_by_name(self, plugin_name):
        for node in self.state.nodes:
            if node.props.plugin_name() == plugin_name:
                return node.props
        return None

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
            # Check which split contains moments - it may not be the first one after root
            m2_index = 1 if split[1][0].startswith('m2_') else 2
            img = np.array(split[m2_index][1], copy=False)
            img_m2 = np.array(split[m2_index][1], copy=False)
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
        """Convert an XYZ image to RGB"""
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


###############################
##  BlenderExporter fixture  ##
###############################

roughness = 'Roughness'
color = 'Color'
strength = 'Strength'
distrib = 'distribution'
node_name = 'name'
beckmann = 'BECKMANN'
'''
Describe the properties of every shader node supported by the Blender Exporter fixture
'''
blender_materials = {
            'glass': {
                node_name: 'ShaderNodeBsdfGlass',
                color: (0, 0, 1, 1),
                distrib: beckmann,
            },
            'glass_r0.5': {
                node_name: 'ShaderNodeBsdfGlass',
                color: (0, 0, 1, 1),
                roughness: 0.5,
                distrib: beckmann,
            },
            'glass_r1': {
                node_name: 'ShaderNodeBsdfGlass',
                color: (0, 0, 1, 1),
                roughness: 1,
                distrib: beckmann,
            },
            'diffuse': {
                node_name: 'ShaderNodeBsdfDiffuse',
                color: (1, 0, 0, 1),
            },
            'diffuse_r0.5': {
                node_name: 'ShaderNodeBsdfDiffuse',
                color: (1, 0, 0, 1),
                roughness: 0.5
            },
            'diffuse_r1': {
                node_name: 'ShaderNodeBsdfDiffuse',
                color: (1, 0, 0, 1),
                roughness: 1
            },
            'emission': {
                node_name: 'ShaderNodeEmission',
                color: (0.390444, 1, 0.358339, 1), 
            },
            'emission_str5': {
                node_name: 'ShaderNodeEmission',
                color: (0.390444, 1, 0.358339, 1), 
                strength: 5.0,
            },
            'emission_str10': {
                node_name: 'ShaderNodeEmission',
                color: (0.390444, 1, 0.358339, 1), 
                strength: 10.0,
            },
            'glossy_r0': {
                node_name: 'ShaderNodeBsdfGlossy',
                color: (0.5, 0.5, 0.5, 1),
                roughness: 0,
                distrib: beckmann
            },
            'glossy_r0.5': {
                node_name: 'ShaderNodeBsdfGlossy',
                color: (0.5, 0.5, 0.5, 1),
                roughness: 0.5,
                distrib: beckmann,
            },
            'glossy_r1': {
                node_name: 'ShaderNodeBsdfGlossy',
                color: (0.5, 0.5, 0.5, 1),
                roughness: 1,
                distrib: beckmann
            },
        }

class BlenderExporter:
    def __init__(self, resource_resolver: ResourceResolver):
        self.resolver = resource_resolver
    
    def setup_blender(self, scene, max_bounce=5, samples=64, resolution=(1280, 720)):
        '''
        Open a scene in Blender and setup the world, scene and cycle parameters expected by the tests

        Parameters
        ----------
        scene : str
            The name of the scene to open, must be saved in the folder tests/res/scenes/blender
        
        max_bounce : int, opt
            Maximum number of ray bounces, default is 5

        samples : int, opt
            Number of sample per pixel, default is 64

        resolution : (int, int), opt
            Resolution of the renders, default is (1280, 720)
        '''
        # Open test scene in blender
        ref_bl_scene = f'{self.resolver.get_scenes_path()}/blender/{scene}'
        bpy.ops.wm.open_mainfile(filepath=ref_bl_scene)

        # Set cycle parameters
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.cycles.device = 'CPU'
        bpy.context.scene.cycles.max_bounces = max_bounce
        bpy.context.scene.cycles.samples = samples
        bpy.context.scene.cycles.use_denoising = False
        bpy.context.scene.render.resolution_x = resolution[0]
        bpy.context.scene.render.resolution_y = resolution[1]
        bpy.data.worlds["World"].node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)

    def set_material(self, name):
        '''
        Create a new material inside blender that is based on a shader node with the propreties 
        described by the entry name in the dictionary blender_materials

        Parameters
        ----------
        name : str
            The name of the shader node to set
        '''
        # Get properties of material
        if name not in blender_materials:
            return False
        
        props = blender_materials[name]

        # Create material and enable shader nodes 
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.node_tree.nodes.clear()
        
        # Add nodes and link them
        outputMat = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
        shader_node = mat.node_tree.nodes.new(props[node_name])
        mat.node_tree.links.new(shader_node.outputs[0], outputMat.inputs[0])

        # Perform specific scene modification if needed
        if props[node_name] == 'ShaderNodeEmission':
            bpy.data.objects['Light'].hide_render = True

        # Set shader node properties accordingly
        for p, v in props.items():
            if p == node_name:
                continue
            elif p == distrib:
                shader_node.distribution = v
            else:
                shader_node.inputs[p].default_value = v 

        for obj in bpy.data.collections['objects'].objects:
            obj.active_material = mat
        return True
    
    def render_and_export(self, ref_render, ref_export):
        '''
        Renders the scene currently set inside blender with cycle and export said scene to mitsuba xml

        Parameters
        ----------
        ref_renders : str
            Path of the directory where to store cycle's render
        
        ref_export : str
            Path of the directory where to store exported scene  
        '''
        bpy.context.scene.render.filepath = ref_render
        bpy.context.scene.render.image_settings.color_mode = 'RGB'
        assert bpy.ops.export_scene.mitsuba(filepath=ref_export) == {"FINISHED"}
        assert bpy.ops.render.render(write_still=True) == {"FINISHED"}

@pytest.fixture
def blender_exporter(resource_resolver):
    return BlenderExporter(resource_resolver)