"""Utils for parsing configuration files and setting up Blender scenes."""

import bpy
import os


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


def setup_render(scene, cfg):
    """Set up render settings based on configuration."""
    scene.render.resolution_x = cfg["render"]["resolution_x"]
    scene.render.resolution_y = cfg["render"]["resolution_y"]


def setup_cameras(scene, cfg):
    """Set up camera based on configuration."""
    for cam_cfg in cfg.get("camera", []):
        bpy.ops.object.camera_add()
        cam = bpy.context.active_object

        cam.location = cam_cfg["location"]
        cam.rotation_euler = cam_cfg["rotation_euler"]
        if "name" in cam_cfg:
            cam.name = cam_cfg["name"]
            cam.data.name = cam_cfg["name"]
        if "optimizable" in cam_cfg:
            cam["optimizable"] = cam_cfg["optimizable"]
        else:
            cam["optimizable"] = True # default to allowing optimization with this viewpoint


def setup_background(scene, config):
    """Set up environment background based on configuration."""
    if "background" in config and "envmap" in config["background"]:
        bg_cfg = config["background"]

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

        if "envmap" in bg_cfg:
            env = nodes.new(type="ShaderNodeTexEnvironment")
            env.image = bpy.data.images.load(bg_cfg["envmap"]["filepath"])
            links.new(env.outputs["Color"], bg.inputs["Color"])

        if "strength" in bg_cfg:
            bg.inputs["Strength"].default_value = bg_cfg["strength"]
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
            if "optimizable" in mat_cfg["texture"]:
                mat["optimizable"] = mat_cfg["texture"]["optimizable"]
            else:
                mat["optimizable"] = False
    else:
        raise ValueError(f"Unknown material configuration: {mat_cfg}")

    return mat


def setup_objects(scene, cfg):
    """Add objects to the scene based on configuration."""
    for obj_cfg in cfg.get("objects", []):
        if obj_cfg["type"] == "PRIMITIVE":
            if obj_cfg["shape"] == "CUBE":
                bpy.ops.mesh.primitive_cube_add(
                    size=obj_cfg.get("size", 1.0),
                    location=obj_cfg.get("location", (0, 0, 0)),
                    rotation=obj_cfg.get("rotation", (0, 0, 0)),
                    # scale=obj_cfg.get("scale", (0, 0, 0)),
                )
            elif obj_cfg["shape"] == "SPHERE":
                bpy.ops.mesh.primitive_uv_sphere_add(
                    radius=obj_cfg.get("radius", 1.0),
                    location=obj_cfg.get("location", (0, 0, 0)),
                    rotation=obj_cfg.get("rotation", (0, 0, 0)),
                    # scale=obj_cfg.get("scale", (0, 0, 0)),
                )
            else:
                raise ValueError(f"Unknown shape type {obj_cfg['shape']}, expected one of CUBE, SPHERE.")
            #TODO: add other primitives: total available are
            # primitive_circle_add()
            # primitive_cone_add()
            # primitive_cube_add() -- done
            # primitive_cube_add_gizmo()
            # primitive_cylinder_add()
            # primitive_grid_add()
            # primitive_ico_sphere_add()
            # primitive_monkey_add()
            # primitive_plane_add()
            # primitive_torus_add()
            # primitive_uv_sphere_add() -- done

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

        # Adjust pose and scaling for non-primitive objects
        obj = bpy.context.active_object
        if obj_cfg["type"] != "PRIMITIVE":
            if "location" in obj_cfg:
                obj.location = obj_cfg["location"]
            if "rotation_euler" in obj_cfg:
                obj.rotation_euler = obj_cfg["rotation_euler"]
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
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.smart_project()
            bpy.ops.object.mode_set(mode='OBJECT')
