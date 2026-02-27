"""
Usage:
path/to/blender --background --python path/to/mitsuba-blender/tests/extended_addon_tests/test_exporter.py
"""

import bpy
import os
import sys
import unittest
import tempfile
import shutil
import yaml
import math
import xml.etree.ElementTree as ET

# Add the mitsuba-blender directory to the path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

class TestMitsubaExporterExtended(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for export output
        self.test_dir = tempfile.mkdtemp()
        self.export_path = os.path.join(self.test_dir, "scene.xml")
        
        # Clear existing scene
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene

        # Register the exporter operator if not already registered
        try:
            # Try standard pref enable first - this is the cleanest way
            bpy.ops.preferences.addon_enable(module="mitsuba-blender")
        except Exception as e:
            print(f"Standard addon enablement failed: {e}")
            # Force registration of the IO module classes explicitly
            try:
                import importlib
                import importlib.util
                
                # Path to the io/__init__.py file
                repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                io_init_path = os.path.join(repo_root, "mitsuba-blender", "io", "__init__.py")
                
                # Load the module specification
                spec = importlib.util.spec_from_file_location("mitsuba_blender_io_manual", io_init_path)
                if spec and spec.loader:
                    io_module = importlib.util.module_from_spec(spec)
                    sys.modules["mitsuba_blender_io_manual"] = io_module
                    spec.loader.exec_module(io_module)
                    
                    # Register the classes defined in this module
                    if hasattr(io_module, "register"):
                        try:
                            io_module.register()
                            print("Force registered mitsuba_blender_io_manual module.")
                        except ValueError:
                            pass # Already registered
                        except Exception as e_reg:
                            print(f"Registration error: {e_reg}")

            except Exception as e2:
                print(f"Manual registration attempt failed: {e2}")

        # Ensure Real Sky addon is enabled for tests that use it
        try:
            bpy.ops.preferences.addon_enable(module="real-sky-main")
        except Exception:
            try:
                bpy.ops.preferences.addon_enable(module="real-sky") 
            except Exception:
                pass

    def tearDown(self):
        # Cleanup temporary directory
        shutil.rmtree(self.test_dir)

    def _run_export(self, use_selection=False):
        """Helper to run the export operator."""
        # Ensure we are in object mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')
            
        return bpy.ops.export_scene.mitsuba_optimization(
            filepath=self.export_path,
            use_selection=use_selection,
            hdri_resolution="2048",
            hdri_samples=1
        )

    def test_standard_scene_export(self):
        """
        Test 1: Standard Scene Export (Baseline)
        Verify basic export functionality, auxiliary files, and optimizable defaults.
        """
        # Setup Scene
        bpy.ops.object.camera_add(location=(0, -10, 0), rotation=(math.radians(90), 0, 0))
        cam = bpy.context.view_layer.objects.active
        cam.name = "Camera"
        cam["optimizable"] = True 

        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        cube = bpy.context.view_layer.objects.active
        cube.name = "Cube"
        
        bpy.ops.object.light_add(type='POINT', location=(5, 5, 5))

        self._run_export()

        # Assertions
        # 1. Verify scene.xml created
        self.assertTrue(os.path.exists(self.export_path), "scene.xml was not created")

        # 2. Verify auxiliary_outputs.yml created (implied by mitsuba_optimization operator)
        aux_path = os.path.join(self.test_dir, "auxiliary_outputs.yml")
        self.assertTrue(os.path.exists(aux_path), "auxiliary_outputs.yml was not created")

        # 3. Verify no baked_envmap.exr (Real Sky is off)
        baked_map = os.path.join(self.test_dir, "baked_envmap.exr")
        self.assertFalse(os.path.exists(baked_map), "baked_envmap.exr should not exist for standard scene")

        # 4. Check optimizable parameter export in auxiliary_outputs.yml
        with open(aux_path, 'r') as f:
            aux_data = yaml.safe_load(f)
        
        # We expect Camera to be in 'sensor_indices_for_optimization'. 
        # The exporter adds indices of cameras that are optimizable.
        # Since we only have 1 camera and it is optimizable, index should be 0.
        self.assertIn("sensor_indices_for_optimization", aux_data)
        self.assertIn(0, aux_data["sensor_indices_for_optimization"])

    def test_realsky_baking_export(self):
        """
        Test 2: Real Sky Baking & Exposure Logic
        Verify baking trigger, exposure correction, and object visibility restoration.
        """
        if not hasattr(self.scene, "sky_settings"):
            print("Skipping Real Sky test: Addon not available")
            return

        self.scene.sky_settings.enabled = True
        
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        cube = bpy.context.view_layer.objects.active
        cube.name = "GeometryCube"

        bpy.ops.object.camera_add(location=(0, -10, 0))

        self._run_export()

        # Assertions
        # 1. Check baked_envmap.exr exists
        baked_map = os.path.join(self.test_dir, "baked_envmap.exr")
        self.assertTrue(os.path.exists(baked_map), "baked_envmap.exr was not generated")

        # 2. Check XML references this map and has correct exposure info
        tree = ET.parse(self.export_path)
        root = tree.getroot()
        
        # Find emitter type=envmap
        env_emitter = None
        for emitter in root.findall("emitter"):
            if emitter.get("type") == "envmap":
                env_emitter = emitter
                break
        
        self.assertIsNotNone(env_emitter, "Environment map emitter not found in XML")
        
        # Check filename
        filename_node = env_emitter.find("string[@name='filename']")
        self.assertIsNotNone(filename_node)
        self.assertTrue("baked_envmap.exr" in filename_node.get("value"))

        # Check exposure/scale
        scale_node = env_emitter.find("float[@name='scale']")
        self.assertIsNotNone(scale_node)
        val = float(scale_node.get("value"))
        self.assertAlmostEqual(val, 1.0 / (2.0 ** 6), delta=0.1)

        # 3. Cleanup verification: GeometryCube must be visible
        cube_obj = bpy.data.objects.get("GeometryCube")
        self.assertFalse(cube_obj.hide_viewport, "Object was not unhidden after export")
        self.assertFalse(cube_obj.hide_render, "Object render visibility not restored")

    def test_auxiliary_data_integrity(self):
        """
        Test 3: Auxiliary Data Integrity
        Verify scene_config.yml / auxiliary_outputs.yml content.
        """
        # Setup
        # Camera 1: Optimizable
        bpy.ops.object.camera_add(location=(1, 1, 1))
        cam1 = bpy.context.view_layer.objects.active
        cam1.name = "CamOpt"
        cam1["optimizable"] = True
        
        # Camera 2: Not Optimizable
        bpy.ops.object.camera_add(location=(2, 2, 2))
        cam2 = bpy.context.view_layer.objects.active
        cam2.name = "CamStatic"
        cam2["optimizable"] = False

        # Object 1: Textured Material, Optimizable
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.view_layer.objects.active
        
        mat = bpy.data.materials.new(name="MatOpt")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
        
        # Create dummy texture
        tex_path = os.path.join(self.test_dir, "tex.png")
        with open(tex_path, 'wb') as f: f.write(b'dummy')
        img = bpy.data.images.new("Tex", 1, 1)
        img.filepath = tex_path
        tex.image = img
        
        mat.node_tree.links.new(tex.outputs[0], bsdf.inputs[0])
        
        # Set property on Material
        mat["optimizable"] = True
        obj.data.materials.append(mat)

        # Run Export
        self._run_export()

        # Assertions
        aux_path = os.path.join(self.test_dir, "auxiliary_outputs.yml")
        with open(aux_path, 'r') as f:
            aux_data = yaml.safe_load(f)

        # Check sensors exist
        indices = aux_data.get("sensor_indices_for_optimization", [])
        self.assertTrue(len(indices) > 0, "No optimizable cameras found")
        
        # Check textures exist
        tex_opt = aux_data.get("texture_optimization", [])
        self.assertTrue(len(tex_opt) > 0, "No optimizable textures found")

    def test_empty_state_handling(self):
        """
        Test 4: Empty/Invalid State Handling
        Verify graceful exit or error when scene is empty.
        """
        # Scene is empty (setup clears it)
        
        try:
            res = self._run_export()
            # If it finishes, it returns {'FINISHED'}
            self.assertIn('FINISHED', res)
        except Exception as e:
            # If it raises strict error, that might be intended behavior,
            # but usually we want to avoid hard crashes.
            # Currently checking if it survives.
            self.fail(f"Export crashed on empty scene: {e}")
            
        # Verify XML exists (even if empty geometry)
        self.assertTrue(os.path.exists(self.export_path))
        
        # Verify it has no sensors
        tree = ET.parse(self.export_path)
        root = tree.getroot()
        self.assertEqual(len(root.findall("sensor")), 0)

if __name__ == '__main__':
    # When running inside Blender, we need to be careful about argv
    try:
        argv = sys.argv
        # Keep only the script name to avoid unittest parsing blender args
        if "--" in sys.argv:
            sys.argv = sys.argv[sys.argv.index("--") + 1:]
        else:
             sys.argv = sys.argv[:1]
             
        unittest.main(exit=False)
    finally:
        sys.argv = argv
