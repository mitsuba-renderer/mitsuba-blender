"""
Usage:
path/to/blender --background --python path/to/mitsuba-blender/tests/extended_addon_tests/test_importer_yml.py
"""

import bpy
import os
import sys
import unittest
import tempfile
import shutil
import math
import numpy as np

# Add the mitsuba-blender directory to the path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import importlib
utils = importlib.import_module("mitsuba-blender.io.importer_yml.utils")

class TestImporterYML(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_config.yml")
        
        # Clear existing scene
        bpy.ops.wm.read_factory_settings(use_empty=True)
        
        # Ensure Real Sky addon is enabled for tests that use it
        try:
            bpy.ops.preferences.addon_enable(module="real-sky-main")
        except Exception:
            try:
                bpy.ops.preferences.addon_enable(module="real-sky") 
            except Exception:
                pass
                
        self.scene = bpy.context.scene

    def tearDown(self):
        # Cleanup temporary directory
        shutil.rmtree(self.test_dir)

    def create_dummy_file(self, filename, content=""):
        path = os.path.join(self.test_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def create_dummy_image(self, filename):
        path = os.path.join(self.test_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Create a minimal valid PNG file
        import struct
        width = 1
        height = 1
        # PNG signature
        data = b'\x89PNG\r\n\x1a\n'
        # IHDR chunk
        data += b'\x00\x00\x00\rIHDR'
        data += struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
        data += b'\x90wS\xde' # CRC
        # IDAT chunk (empty)
        data += b'\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe'
        data += b'\xdc\xccY\xe7' # CRC
        # IEND chunk
        data += b'\x00\x00\x00\x00IEND\xaeB`\x82'
        
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_resolve_relative_filepaths(self):
        """Test path resolution utility"""
        data = {
            "key1": "value1",
            "texture": {
                "filepath": "./textures/diffuse.png",
                "other": "value"
            },
            "list": [
                {"filepath": "../models/mesh.obj"},
                {"filepath": "/absolute/path/file.txt"}
            ]
        }
        
        base_dir = "/tmp/base"
        utils.resolve_relative_filepaths(data, base_dir)
        
        expected_texture = os.path.abspath(os.path.join(base_dir, "./textures/diffuse.png"))
        expected_mesh = os.path.abspath(os.path.join(base_dir, "../models/mesh.obj"))
        
        self.assertEqual(data["texture"]["filepath"], expected_texture)
        self.assertEqual(data["list"][0]["filepath"], expected_mesh)
        self.assertEqual(data["list"][1]["filepath"], "/absolute/path/file.txt") # Absolute paths should be untouched (or normalized)

    def test_setup_render(self):
        """Test render settings application"""
        cfg = {
            "render": {
                "resolution_x": 640,
                "resolution_y": 480
            }
        }
        utils.setup_render(self.scene, cfg)
        self.assertEqual(self.scene.render.resolution_x, 640)
        self.assertEqual(self.scene.render.resolution_y, 480)

    def test_setup_cameras(self):
        """Test camera creation and properties"""
        cfg = {
            "camera": [
                {
                    "name": "TestCam1",
                    "location": [1, 2, 3],
                    "rotation": [0.1, 0.2, 0.3],
                    "optimizable": True
                },
                {
                    "name": "TestCam2",
                    "location": [4, 5, 6],
                    "rotation": [0.4, 0.5, 0.6],
                    "optimizable": False
                }
            ]
        }
        utils.setup_cameras(self.scene, cfg)
        
        cam1 = bpy.data.objects.get("TestCam1")
        cam2 = bpy.data.objects.get("TestCam2")
        
        self.assertIsNotNone(cam1)
        self.assertIsNotNone(cam2)
        
        # Check properties
        self.assertTrue(np.allclose(cam1.location, [1, 2, 3]))
        self.assertTrue(np.allclose(cam1.rotation_euler, [0.1, 0.2, 0.3]))
        self.assertEqual(cam1.get("optimizable"), True)
        
        self.assertTrue(np.allclose(cam2.location, [4, 5, 6]))
        self.assertEqual(cam2.get("optimizable"), False)

    def test_setup_background_envmap(self):
        """Test environment map background setup"""
        env_path = self.create_dummy_image("envmap.exr")
        cfg = {
            "background": {
                "envmap": {
                    "filepath": env_path,
                    "strength": 2.5
                }
            }
        }
        
        # Ensure world exists
        if not self.scene.world:
            self.scene.world = bpy.data.worlds.new("World")
            
        utils.setup_background(self.scene, cfg)
        
        world = self.scene.world
        self.assertTrue(world.use_nodes)
        
        # Find nodes
        nodes = world.node_tree.nodes
        env_node = None
        bg_node = None
        
        for node in nodes:
            if node.type == 'TEX_ENVIRONMENT':
                env_node = node
            elif node.type == 'BACKGROUND':
                bg_node = node
                
        self.assertIsNotNone(env_node)
        self.assertIsNotNone(bg_node)
        
        # Check properties
        self.assertEqual(bg_node.inputs['Strength'].default_value, 2.5)
        # Check if image is loaded (filepath might be absolute/relative depending on blender)
        self.assertTrue(env_node.image.filepath.endswith("envmap.exr"))

    def test_create_primitive_object(self):
        """Test creating a primitive object with material"""
        cfg = {
            "objects": [
                {
                    "type": "PRIMITIVE",
                    "shape": "CUBE",
                    "location": [1, 0, 0],
                    "size": 2.0,
                    "material": {
                        "name": "TestMat",
                        "diffuse_color": [1, 0, 0, 1]
                    }
                }
            ]
        }
        
        utils.setup_objects(self.scene, cfg)
        
        # Check object
        cube = bpy.data.objects.get("Cube") # Blender default name for primitive
        if not cube:
             # Try finding by type if name differs
             for obj in bpy.data.objects:
                 if obj.type == 'MESH':
                     cube = obj
                     break
        
        self.assertIsNotNone(cube)
        self.assertTrue(np.allclose(cube.location, [1, 0, 0]))
        
        # Check material
        self.assertTrue(len(cube.data.materials) > 0)
        mat = cube.data.materials[0]
        self.assertEqual(mat.name, "TestMat")
        self.assertTrue(np.allclose(mat.diffuse_color, [1, 0, 0, 1]))

    def test_create_textured_material(self):
        """Test creating a material with texture"""
        tex_path = self.create_dummy_image("texture.png")
        mat_cfg = {
            "name": "TexturedMat",
            "shader": "BSDF",
            "texture": {
                "type": "IMAGE",
                "filepath": tex_path,
                "optimizable": True
            }
        }
        
        mat = utils.create_material(mat_cfg)
        
        self.assertIsNotNone(mat)
        self.assertTrue(mat.use_nodes)
        
        # Check nodes
        nodes = mat.node_tree.nodes
        tex_node = None
        for node in nodes:
            if node.type == 'TEX_IMAGE':
                tex_node = node
                break
        
        self.assertIsNotNone(tex_node)
        self.assertTrue(tex_node.image.filepath.endswith("texture.png"))
        self.assertEqual(mat.get("optimizable"), True)

    def test_end_to_end(self):
        """End-to-end test of the full pipeline"""
        # Create resources
        tex_path = self.create_dummy_image("texture.png")
        
        # Config
        config_data = {
            "render": {"resolution_x": 100, "resolution_y": 100},
            "camera": [{"name": "MainCam", "location": [0, -10, 0], "rotation": [1.57, 0, 0]}],
            "background": {
                "dynamic_lighting": {
                    "sun": {
                        "north_direction": 0,
                        "month": 1,
                        "day": 1,
                        "time": 12.00,
                        "latitude": 45
                    },
                    "sky": {
                        "method": "Real Sky",
                        "altitude": 1,
                        "turbidity": 22,
                        "albedo": 30
                    },
                    "clouds": {
                        "cirrus": {
                            "use": True,
                            "wind_direction": 0,
                            "location": 0.00,
                            "coverage": 50,
                            "density": 100
                        }
                    }
                }
            },
            "lights": [{"type": "SUN", "name": "Sun", "location": [0, 0, 10], "energy": 5.0}],
            "objects": [
                {
                    "type": "PRIMITIVE", 
                    "shape": "SPHERE", 
                    "location": [0, 0, 0],
                    "material": {
                        "name": "SphereMat",
                        "shader": "BSDF",
                        "texture": {"type": "IMAGE", "filepath": tex_path}
                    }
                }
            ]
        }
        
        # Helper to convert path to absolute before saving (mimics load_config behavior)
        if "objects" in config_data:
             config_data["objects"][0]["material"]["texture"]["filepath"] = tex_path

        # Run pipeline steps
        utils.reset_viewport_settings(self.scene)
        utils.setup_render(self.scene, config_data)
        utils.setup_cameras(self.scene, config_data)
        utils.setup_background(self.scene, config_data)
        utils.setup_lights(self.scene, config_data)
        utils.setup_objects(self.scene, config_data)
        
        # Assertions
        self.assertEqual(self.scene.render.resolution_x, 100)
        self.assertIsNotNone(bpy.data.objects.get("MainCam"))
        self.assertIsNotNone(bpy.data.objects.get("Sun"))
        
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.name == "Sphere": # Sphere is a mesh
                self.assertIsNotNone(obj)
                self.assertEqual(obj.data.materials[0].name, "SphereMat", f"Sphere materials: {[mat.name for mat in obj.data.materials]}")
                break        
        
        # Check RealSky settings
        self.assertTrue(hasattr(self.scene, 'sky_settings'), "Real Sky settings not found, ensure Real Sky addon is enabled for this test.")
        self.assertTrue(self.scene.sky_settings.enabled)
        self.assertAlmostEqual(self.scene.sky_settings.time, 12.00)
        self.assertAlmostEqual(self.scene.sky_settings.latitude, math.radians(45))


if __name__ == '__main__':
    # Use a custom test runner or just call unittest.main if running inside blender
    # When running inside Blender, we need to be careful about argv
    try:
        argv = sys.argv
        sys.argv = sys.argv[:1] # Keep only the script name to avoid unittest parsing blender args
        unittest.main(exit=False)
    finally:
        sys.argv = argv
