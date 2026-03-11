import os
import math
import re
from collections import defaultdict

if "bpy" in locals():
    import importlib
    if "export_context" in locals():
        importlib.reload(export_context)
    if "materials" in locals():
        importlib.reload(materials)
    if "geometry" in locals():
        importlib.reload(geometry)
    if "lights" in locals():
        importlib.reload(lights)
    if "camera" in locals():
        importlib.reload(camera)

import bpy

from . import export_context
from . import materials
from . import geometry
from . import lights
from . import camera

def apply_fog_dome(input_xml, output_xml, target_visibility=0.2):
    import mitsuba
    print(f"Evaluating scene geometry: {input_xml} ...")
    
    # Determine scene bounds
    scene = mitsuba.load_file(input_xml)
    bbox = scene.bbox()
    
    # scene.bbox() only includes meshes. We must manually expand it to include 
    # all camera positions so they are never left outside the fog sphere.
    for sensor in scene.sensors():
        transform = sensor.world_transform()
        
        # Handle both static Transform4f and AnimatedTransform objects
        if hasattr(transform, 'eval'):
            transform = transform.eval(0.0)
            
        cam_pos = transform.translation()
        bbox.expand(cam_pos)

    # Calculate fog dome based on bbox with safety margin to ensure all geometry is fully enclosed
    center = (bbox.max + bbox.min) / 2.0
    dx = bbox.max.x - center.x
    dy = bbox.max.y - center.y
    dz = bbox.max.z - center.z
    radius = math.sqrt(dx**2 + dy**2 + dz**2) * 1.05 
    
    # Calculate scale-invariant density using Beer-Lambert law
    fog_scale = -math.log(target_visibility) / radius
    
    print(f"Calculated Bounding Sphere Center: ({center.x:.2f}, {center.y:.2f}, {center.z:.2f})")
    print(f"Calculated Bounding Sphere Radius: {radius:.2f}")

    # Inject fog into the XML scene description
    with open(input_xml, 'r') as file:
        xml_content = file.read()

    # Swap the integrator to volpath
    xml_content = re.sub(
        r'<integrator\s+type="[^"]+"', 
        '<integrator type="volpath"', 
        xml_content, 
        count=1
    )

    # Inject <ref id="fog"/> into every sensor block
    ref_tag = '\n        <ref id="fog"/>\n    ' # finds the closing </sensor> tag and prepends the reference.
    xml_content = re.sub(r'(</sensor>)', rf'{ref_tag}\1', xml_content)

    fog_xml = f"""
<medium type="homogeneous" id="fog">
        <rgb name="sigma_t" value="1.0, 1.0, 1.0"/>
        <rgb name="albedo" value="0.9, 0.9, 0.9"/>
        <float name="scale" value="{fog_scale:.6f}"/>
        <phase type="hg">
            <float name="g" value="0.5"/>
        </phase>
    </medium>

    <shape type="sphere">
        <point name="center" x="{center.x:.6f}" y="{center.y:.6f}" z="{center.z:.6f}"/>
        <float name="radius" value="{radius:.6f}"/>
        <ref name="interior" id="fog"/>
        <bsdf type="null"/>
    </shape>
"""
    
    # Append the fog XML right before the closing scene tag
    if "</scene>" in xml_content:
        xml_content = xml_content.replace("</scene>", fog_xml + "</scene>")
    else:
        raise ValueError("Could not find closing </scene> tag in the input XML.")

    # Save output
    with open(output_xml, 'w') as file:
        file.write(xml_content)
        
    print(f"Successfully generated fog-enabled scene: {output_xml}")


class SceneConverter:
    '''
    Converts a blender scene to a Mitsuba-compatible dict.
    Either save it as an XML or load it as a scene.
    '''
    def __init__(self, render=False, include_auxiliary_output=False):
        self.export_ctx = export_context.ExportContext()
        self.use_selection = False # Only export selection
        self.ignore_background = True
        self.render = render

        self.include_auxiliary_output = include_auxiliary_output # Whether to include auxiliary outputs in the XML file
        self.auxiliary_output_dict = {
            "texture_optimization": set(),
            "sensor_indices_for_optimization": []
        }
        
    def set_path(self, name, split_files=False):
        from mitsuba.python.xml import WriteXML
        # Ideally, this should only be created if we want to write a scene.
        # For now we need it to save meshes and packed textures.
        # TODO: get rid of all writing to disk when creating the dict
        self.output_path = name
        if not self.render:
            self.xml_writer = WriteXML(name, self.export_ctx.subfolders,
                                       split_files=split_files)
        # Give the path to the export context, for saving meshes and files
        self.export_ctx.directory, _ = os.path.split(name)

    def scene_to_dict(self, depsgraph, window_manager):
        # Switch to object mode before exporting stuff, so everything is defined properly
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        #depsgraph = context.evaluated_depsgraph_get()
        self.export_ctx.deg = depsgraph

        b_scene = depsgraph.scene #TODO: what if there are multiple scenes?
        if b_scene.render.engine == 'MITSUBA':
            integrator = getattr(b_scene.mitsuba.available_integrators,b_scene.mitsuba.active_integrator).to_dict()
        else:
            integrator = {
                'type':'path',
                'max_depth': b_scene.cycles.max_bounces
            }
        self.export_ctx.data_add(integrator)

        materials.export_world(self.export_ctx, b_scene.world, self.ignore_background)

        # Establish list of particle objects
        particles = []
        for particle_sys in bpy.data.particles:
            if particle_sys.render_type == 'OBJECT':
                particles.append(particle_sys.instance_object.name)
            elif particle_sys.render_type == 'COLLECTION':
                for obj in particle_sys.instance_collection.objects:
                    particles.append(obj.name)

        progress_counter = 0
        camera_counter = 0
        # Main export loop
        for object_instance in depsgraph.object_instances:
            window_manager.progress_update(progress_counter)
            progress_counter += 1

            if self.use_selection:
                #skip if it's not selected or if it's an instance and the parent object is not selected
                if not object_instance.is_instance and not object_instance.object.original.select_get():
                    continue
                if (object_instance.is_instance and object_instance.object.parent
                    and not object_instance.object.parent.original.select_get()):
                    continue

            evaluated_obj = object_instance.object
            object_type = evaluated_obj.type
            #type: enum in [‘MESH’, ‘CURVE’, ‘SURFACE’, ‘META’, ‘FONT’, ‘ARMATURE’, ‘LATTICE’, ‘EMPTY’, ‘GPENCIL’, ‘CAMERA’, ‘LIGHT’, ‘SPEAKER’, ‘LIGHT_PROBE’], default ‘EMPTY’, (readonly)
            if evaluated_obj.hide_render or (object_instance.is_instance
                and evaluated_obj.parent and evaluated_obj.parent.original.hide_render):
                self.export_ctx.log("Object: {} is hidden for render. Ignoring it.".format(evaluated_obj.name), 'INFO')
                continue#ignore it since we don't want it rendered (TODO: hide_viewport)
            if object_type in {'MESH', 'FONT', 'SURFACE', 'META'}:
                if self.include_auxiliary_output:
                    geometry.export_object(object_instance, self.export_ctx, evaluated_obj.name in particles, self.auxiliary_output_dict["texture_optimization"])
                else:
                    geometry.export_object(object_instance, self.export_ctx, evaluated_obj.name in particles)
            elif object_type == 'CAMERA':
                # When rendering inside blender, export only the active camera # NOTE: what does this mean
                if (self.render and evaluated_obj.name_full == b_scene.camera.name_full) or not self.render:
                    if self.include_auxiliary_output:
                        camera.export_camera(object_instance, b_scene, self.export_ctx, self.auxiliary_output_dict["sensor_indices_for_optimization"], camera_counter)
                    else:
                        camera.export_camera(object_instance, b_scene, self.export_ctx)
                    camera_counter += 1
                    
                # TODO: add auxiliary output to export all cams
            elif object_type == 'LIGHT':
                lights.export_light(object_instance, self.export_ctx)
            else:
                self.export_ctx.log("Object: %s of type '%s' is not supported!" % (evaluated_obj.name_full, object_type), 'WARN')

    def dict_to_xml(self):
        self.xml_writer.process(self.export_ctx.scene_data)
        
        # Apply fog if configured
        b_scene = self.export_ctx.deg.scene
        if b_scene.get('fog_target_visibility') is not None:
            target_vis = b_scene['fog_target_visibility']
            apply_fog_dome(self.output_path, self.output_path, target_vis)

    def aux_dict_to_yml(self):
        import yaml
        aux_path = os.path.join(self.export_ctx.directory, "auxiliary_outputs.yml")
        # convert to standard dict
        self.auxiliary_output_dict = {k: list(v) if isinstance(v, set) else v for k, v in self.auxiliary_output_dict.items()}

        with open(aux_path, 'w') as f:
            yaml.dump(self.auxiliary_output_dict, f)

    def dict_to_scene(self):
        from mitsuba import load_dict
        return load_dict(self.export_ctx.scene_data)
