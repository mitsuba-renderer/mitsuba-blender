"""Utils for parsing configuration files and setting up Blender scenes."""

import bpy
import os
import math


def resolve_relative_filepaths(data, base_dir):
    """
    Recursively resolve any 'filepath' keys in a nested dict
    to absolute paths relative to base_dir.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "filepath" and isinstance(value, str):
                # Make relative to YAML directory
                abs_path = os.path.normpath(os.path.join(base_dir, value))
                data[key] = abs_path
            else:
                resolve_relative_filepaths(value, base_dir)
    elif isinstance(data, list):
        for item in data:
            resolve_relative_filepaths(item, base_dir)


def load_config(path="scene_config.yml"):
    """Load configuration from a YAML file."""
    import yaml
    base_dir = os.path.dirname(os.path.abspath(path))
    with open(path, "r") as f:
        config_data = yaml.safe_load(f)

    resolve_relative_filepaths(config_data, base_dir)

    return config_data


def reset_viewport_settings(scene):
    """Reset viewport settings to default values."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.clip_end = 1000.0
                        
    if hasattr(scene, 'sky_settings'):
        scene.sky_settings.enabled = False


def setup_render(scene, cfg):
    """Set up render settings based on configuration."""
    if "render" in cfg and cfg["render"]:
        render_cfg = cfg["render"]
        scene.render.resolution_x = render_cfg.get("resolution_x", 1920)
        scene.render.resolution_y = render_cfg.get("resolution_y", 1080)
        #TODO: add samples 

def setup_fog(scene, cfg):
    """Set up fog based on configuration. Fog will not be added until export as it is a mitsuba-only function."""
    if "fog" in cfg and cfg["fog"]:
        fog_cfg = cfg["fog"]
        scene['fog_target_visibility'] = fog_cfg.get("target_visibility", 0.2)

def setup_cameras(scene, cfg):
    """Set up camera based on configuration."""
    for cam_cfg in cfg.get("camera", []):
        bpy.ops.object.camera_add()
        cam = bpy.context.view_layer.objects.active

        cam.location = cam_cfg["location"]
        cam.rotation_euler = cam_cfg["rotation"]
        if "name" in cam_cfg:
            cam.name = cam_cfg["name"]
            cam.data.name = cam_cfg["name"]
        if "optimizable" in cam_cfg:
            cam["optimizable"] = cam_cfg["optimizable"]
        else:
            cam["optimizable"] = True # default to allowing optimization with this viewpoint


def setup_background(scene, config):
    def setup_viewport_for_clouds(clouds_settings, view_3d_area, cloud_type):
        if view_3d_area: # Trick the add-on into running as if we clicked inside the 3D Viewport
            with bpy.context.temp_override(area=view_3d_area):
                if cloud_type == "cirrus":
                    clouds_settings.cirrus = True
                elif cloud_type == "cirrocumulus":
                    clouds_settings.cirrocumulus = True
                elif cloud_type == "altostratus":
                    clouds_settings.altostratus = True
                elif cloud_type == "cumulus":
                    clouds_settings.cumulus = True
        else: # Fallback in case there is no UI open
            if cloud_type == "cirrus":
                clouds_settings.cirrus = True
            elif cloud_type == "cirrocumulus":
                clouds_settings.cirrocumulus = True
            elif cloud_type == "altostratus":
                clouds_settings.altostratus = True
            elif cloud_type == "cumulus":
                clouds_settings.cumulus = True

    """Set up environment background based on configuration."""
    if "background" not in config:
        return
    bg_cfg = config["background"]
    if "dynamic_lighting" in config["background"]:
        # Ensure Real Sky addon is enabled if possible
        if not hasattr(bpy.context.scene, "sky_settings"):
            try:
                bpy.ops.preferences.addon_enable(module="real-sky-main")
            except Exception:
                try:
                    bpy.ops.preferences.addon_enable(module="real-sky")
                except Exception:
                    print("Warning: Real Sky addon not found or could not be enabled. Dynamic lighting setup may fail.")

        # Cleanup
        # Remove old Real Sky worlds to prevent append collisions
        for w in bpy.data.worlds:
            if "Real Sky" in w.name:
                bpy.data.worlds.remove(w)
                
        # Remove old Sun objects globally to prevent naming collisions
        for obj in bpy.data.objects:
            if obj.name.startswith("Sun") and obj.type == 'LIGHT':
                bpy.data.objects.remove(obj, do_unlink=True)
                
        for light in bpy.data.lights:
            if light.name.startswith("Sun"):
                bpy.data.lights.remove(light)
        
        bpy.context.scene.sky_settings.enabled = True
        sky_settings = bpy.context.scene.sky_settings

        lighting_cfg = bg_cfg["dynamic_lighting"]

        # sun settings
        sun_cfg = lighting_cfg.get("sun", {})
        sky_settings.direction = math.radians(sun_cfg.get("north_direction", 0))
        sky_settings.time = sun_cfg.get("time", 12.0)
        sky_settings.month = sun_cfg.get("month", 1)
        sky_settings.day31 = sun_cfg.get("day", 1)
        sky_settings.latitude = math.radians(sun_cfg.get("latitude", 45.0)) # 45 degrees in radians
        
        # sky settings
        sky_cfg = lighting_cfg.get("sky", {})
        sky_settings.sky_method = sky_cfg.get("sky_method", "Real Sky")
        sky_settings.altitude = sky_cfg.get("altitude", 1.0)
        sky_settings.turbidity = sky_cfg.get("turbidity", 22) # percent
        sky_settings.albedo = sky_cfg.get("albedo", 30.0) # percent

        # clouds settings
        if "clouds" in lighting_cfg:
            # need to use cycles render engine for dynamic clouds to work
            clouds_settings = bpy.context.scene.clouds_settings
            cloud_cfg = lighting_cfg["clouds"]
            scene.render.engine = 'CYCLES'

            # Find an open 3D Viewport in the UI
            view_3d_area = None
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        view_3d_area = area
                        break
                if view_3d_area:
                    break
            if "cirrus" in cloud_cfg and cloud_cfg["cirrus"]["use"]:
                setup_viewport_for_clouds(clouds_settings, view_3d_area, "cirrus")
                clouds_settings.cirrus_direction = math.radians(cloud_cfg["cirrus"].get("wind_direction", 0.0)) # wind, degrees
                clouds_settings.cirrus_location = cloud_cfg["cirrus"].get("location", 0.0)
                clouds_settings.cirrus_coverage = cloud_cfg["cirrus"].get("coverage", 50) # percent
                clouds_settings.cirrus_density = cloud_cfg["cirrus"].get("density", 100) # percent

                        
            if "cirrocumulus" in cloud_cfg and cloud_cfg["cirrocumulus"]["use"]:
                setup_viewport_for_clouds(clouds_settings, view_3d_area, "cirrocumulus")
                clouds_settings.cirrocumulus_direction = math.radians(cloud_cfg["cirrocumulus"].get("wind_direction", 0.0)) # wind, degrees
                clouds_settings.cirrocumulus_location = cloud_cfg["cirrocumulus"].get("location", 0.0)
                clouds_settings.cirrocumulus_coverage = cloud_cfg["cirrocumulus"].get("coverage", 50) # percent
                clouds_settings.cirrocumulus_density = cloud_cfg["cirrocumulus"].get("density", 100) # percent

            if "altostratus" in cloud_cfg and cloud_cfg["altostratus"]["use"]:
                setup_viewport_for_clouds(clouds_settings, view_3d_area, "altostratus")
                if "method" in cloud_cfg["altostratus"]:
                    if cloud_cfg["altostratus"]["method"] == "Volume":
                        clouds_settings.altostratus_mist = cloud_cfg["altostratus"].get("mist", True)
                    elif cloud_cfg["altostratus"]["method"] == "Billboard":
                        clouds_settings.altostratus_billboard_res = cloud_cfg["altostratus"].get("billboard_res", "Low")
                    else:
                        raise ValueError(f"Unknown altostratus method {cloud_cfg['altostratus']['method']}, expected one of 'Volume', 'Billboard'.")
                clouds_settings.altostratus_direction = math.radians(cloud_cfg["altostratus"].get("wind_direction", 0.0)) # wind, degrees
                clouds_settings.altostratus_location = cloud_cfg["altostratus"].get("location", 0.0)
                clouds_settings.altostratus_coverage = cloud_cfg["altostratus"].get("coverage", 50) # percent
                clouds_settings.altostratus_density = cloud_cfg["altostratus"].get("density", 50) # percent

            if "cumulus" in cloud_cfg and cloud_cfg["cumulus"]["use"]:
                setup_viewport_for_clouds(clouds_settings, view_3d_area, "cumulus")
                if "method" in cloud_cfg["cumulus"]:
                    if cloud_cfg["cumulus"]["method"] == "Volume":
                        clouds_settings.cumulus_mist = cloud_cfg["cumulus"].get("mist", True)
                    elif cloud_cfg["cumulus"]["method"] == "Billboard":
                        clouds_settings.cumulus_billboard_res = cloud_cfg["cumulus"].get("billboard_res", "Low")
                    else:
                        raise ValueError(f"Unknown cumulus method {cloud_cfg['cumulus']['method']}, expected one of 'Volume', 'Billboard'.")
                clouds_settings.cumulus_direction = math.radians(cloud_cfg["cumulus"].get("wind_direction", 0.0)) # wind, degrees
                clouds_settings.cumulus_location = cloud_cfg["cumulus"].get("location", 0.0)
                clouds_settings.cumulus_coverage = cloud_cfg["cumulus"].get("coverage", 50) # percent
                clouds_settings.cumulus_density = cloud_cfg["cumulus"].get("density", 50) # percent

        # Make clouds visible in viewpoint
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.clip_end = 800000

        # Extend the clipping distance for all cameras so the clouds render
        for cam in bpy.data.cameras:
            cam.clip_end = 800000

        # Force a scene update
        bpy.context.view_layer.update()

    elif "envmap" in config["background"]:
        if not scene.world:
            scene.world = bpy.data.worlds.new("World")
        world = scene.world
        # world = bpy.data.worlds["World"]
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links

        nodes.clear()
        output = nodes.new(type="ShaderNodeOutputWorld")
        bg = nodes.new(type="ShaderNodeBackground")

        env = nodes.new(type="ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(bg_cfg["envmap"]["filepath"])
        links.new(env.outputs["Color"], bg.inputs["Color"])

        bg.inputs["Strength"].default_value = bg_cfg["envmap"].get("strength", 1.0)
        links.new(bg.outputs["Background"], output.inputs["Surface"])


def setup_lights(scene, cfg):
    """Add lights to the scene based on configuration."""
    for light_cfg in cfg.get("lights", []):
        light_data = bpy.data.lights.new(light_cfg["name"], light_cfg["type"])
        light_obj = bpy.data.objects.new(light_cfg["name"], light_data)
        light_obj.location = light_cfg["location"]
        light_data.energy = light_cfg["energy"]
        scene.collection.objects.link(light_obj)


def create_material(mat_cfg):
    """Add material properties to objects based on configuration."""
    name = mat_cfg["name"]

    # If exists, reuse instead of creating duplicates
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)

    if "diffuse_color" in mat_cfg: ## solid color
        mat.diffuse_color = mat_cfg["diffuse_color"]

    elif mat_cfg.get("shader") == "BSDF": ## principled shader
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Clear all existing nodes
        for node in list(nodes):
            nodes.remove(node)

        # Create necessary nodes
        output = nodes.new(type="ShaderNodeOutputMaterial")
        output.location = (400, 0)

        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

        # If we have a texture
        if "texture" in mat_cfg and mat_cfg["texture"]["type"] == "IMAGE":
            tex_image = nodes.new(type="ShaderNodeTexImage")
            tex_image.location = (-400, 0)
            tex_image.image = bpy.data.images.load(mat_cfg["texture"]["filepath"])
            tex_image.image.colorspace_settings.name = mat_cfg["texture"].get("colorspace", "sRGB") # default to sRGB

            links.new(tex_image.outputs["Color"], bsdf.inputs["Base Color"])
            mat["optimizable"] = mat_cfg["texture"].get("optimizable", False)
    else:
        raise ValueError(f"Unknown material configuration: {mat_cfg}")

    return mat


def setup_objects(scene, cfg):
    """Add objects to the scene based on configuration."""
    for obj_cfg in cfg.get("objects", []):
        common_defaults = {
            "size": obj_cfg.get("size", 2.0),
            "radius": obj_cfg.get("radius", 1.0),
            "align": obj_cfg.get("align", 'WORLD'),
            "location": obj_cfg.get("location", (0, 0, 0)),
            "rotation": obj_cfg.get("rotation", (0, 0, 0)),
            "scale": obj_cfg.get("scale", (1, 1, 1)),
        }
        if obj_cfg["type"] == "PRIMITIVE":
            if obj_cfg["shape"] == "SPHERE":
                bpy.ops.mesh.primitive_uv_sphere_add(
                    segments=obj_cfg.get("segments", 32),
                    ring_count=obj_cfg.get("ring_count", 16),
                    radius=common_defaults["radius"],
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                    scale=common_defaults["scale"],
                )
            elif obj_cfg["shape"] == "CIRCLE":
                bpy.ops.mesh.primitive_circle_add(
                    vertices=obj_cfg.get("vertices", 32),
                    radius=common_defaults["radius"],
                    fill_type=obj_cfg.get("fill_type", 'NOTHING'),
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                    scale=common_defaults["scale"],
                )
            elif obj_cfg["shape"] == "CONE":
                bpy.ops.mesh.primitive_cone_add(
                    vertices=obj_cfg.get("vertices", 32),
                    radius1=obj_cfg.get("radius1", 1.0),
                    radius2=obj_cfg.get("radius2", 0.0),
                    depth=obj_cfg.get("depth", 2.0),
                    end_fill_type=obj_cfg.get("end_fill_type", 'NGON'),
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                    scale=common_defaults["scale"],
                )
            elif obj_cfg["shape"] == "CYLINDER":
                bpy.ops.mesh.primitive_cylinder_add(
                    vertices=obj_cfg.get("vertices", 32),
                    radius=common_defaults["radius"],
                    depth=obj_cfg.get("depth", 2.0),
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                    scale=common_defaults["scale"],
                )
            elif obj_cfg["shape"] == "CUBE":
                bpy.ops.mesh.primitive_cube_add(
                    size=common_defaults["size"],
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                )
            elif obj_cfg["shape"] == "GRID":
                bpy.ops.mesh.primitive_grid_add(
                    x_subdivisions=obj_cfg.get("x_subdivisions", 10),
                    y_subdivisions=obj_cfg.get("y_subdivisions", 10),
                    size=common_defaults["size"],
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                    scale=common_defaults["scale"],
                )
            elif obj_cfg["shape"] == "ICO_SPHERE":
                bpy.ops.mesh.primitive_ico_sphere_add(
                    subdivisions=obj_cfg.get("subdivisions", 2),
                    radius=common_defaults["radius"],
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                    scale=common_defaults["scale"],
                )
            elif obj_cfg["shape"] == "MONKEY":
                bpy.ops.mesh.primitive_monkey_add(
                    size=common_defaults["size"],
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                    scale=common_defaults["scale"],
                )
            elif obj_cfg["shape"] == "PLANE":
                bpy.ops.mesh.primitive_plane_add(
                    size=common_defaults["size"],
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                    scale=common_defaults["scale"],
                )
            elif obj_cfg["shape"] == "TORUS":
                bpy.ops.mesh.primitive_torus_add(
                    major_segments=obj_cfg.get("major_segments", 48),
                    minor_segments=obj_cfg.get("minor_segments", 12),
                    major_radius=obj_cfg.get("major_radius", 1.0),
                    minor_radius=obj_cfg.get("minor_radius", 0.25),
                    abso_major_rad=obj_cfg.get("abso_major_rad", 1.25),
                    abso_minor_rad=obj_cfg.get("abso_minor_rad", 0.75),
                    mode=obj_cfg.get("mode", "MAJOR_MINOR"),
                    align=common_defaults["align"],
                    location=common_defaults["location"],
                    rotation=common_defaults["rotation"],
                )
            else:
                raise ValueError(f"Unknown shape type {obj_cfg['shape']}, expected one of CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE, MONKEY, ICO_SPHERE, GRID, CIRCLE.")

        elif obj_cfg["type"] == "MESH":
            mesh_filepath = obj_cfg["filepath"]
            file_ending = mesh_filepath.split(".")[-1]
            if file_ending == "obj":
                bpy.ops.wm.obj_import(filepath=mesh_filepath)
            elif file_ending == "stl":
                bpy.ops.wm.stl_import(filepath=mesh_filepath)
            elif file_ending == "ply":
                bpy.ops.wm.ply_import(filepath=mesh_filepath)
            elif file_ending == "fbx":
                # bpy.ops.wm.fbx_import(filepath=mesh_filepath)
                bpy.ops.import_scene.fbx(filepath=mesh_filepath)
            else:
                raise ValueError(f"Unknown file ending type {file_ending}, expected one of 'obj', 'stl', 'ply', 'fbx")

        # Adjust pose and scaling for non-primitive objects, e.g. meshes
        obj = bpy.context.view_layer.objects.active
        if obj_cfg["type"] != "PRIMITIVE":
            obj.location = common_defaults["location"]
            obj.rotation_euler = common_defaults["rotation"]
            # Scale: prefer explicit 3-element scale, else uniform `size` if provided
            if "scale" in obj_cfg:
                obj.scale = obj_cfg["scale"]
            elif "size" in obj_cfg:
                s = obj_cfg["size"]
                obj.scale = (s, s, s)

        if "name" in obj_cfg:
            obj.name = obj_cfg["name"]

        # Assign material
        if "material" in obj_cfg and obj.data is not None:
            mat = create_material(obj_cfg["material"])
            obj.data.materials.clear()
            obj.data.materials.append(mat)

            # ensure UV map exists
            mesh = obj.data
            if not mesh.uv_layers:
                # add uv layer
                mesh.uv_layers.new(name="UVMap")

            # unwrap automatically bitmap
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            
            # Use view_layer update to ensure context is ready
            bpy.context.view_layer.update()
            
            with bpy.context.temp_override(active_object=obj, selected_editable_objects=[obj], selected_objects=[obj]):
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.smart_project()
                bpy.ops.object.mode_set(mode='OBJECT')
