from .materials import export_material
from .file_api import Files
import os

class GeometryExporter:
    """
    Encapsulates mesh export methods, and keeps track of exported objects.
    This is necessary in order to export meshes with multiple materials.
    """
    def __init__(self):
        self.exported_meshes = {} # dict containing entries like mesh_name : [exported materials]

    def add_exported_mesh(self, name, mat_nr):
        if name in self.exported_meshes.keys():
            self.exported_meshes[name].append(mat_nr)
        else:
            self.exported_meshes.update({name:[mat_nr]})

    def save_mesh(self, export_ctx, b_mesh, matrix_world, b_name, file_path, mat_nr):
        '''
        This method creates a mitsuba mesh and save it as PLY.
        It constructs a dictionary containing the necessary info such as pointers to blender's data strucures
        and then loads the BlenderMesh plugin via load_dict.

        Params
        ------
        export_ctx: The export context.
        b_mesh: The blender mesh to export.
        matrix_world: The mesh's transform matrix.
        b_name: The name of the mesh in Blender
        file_path: The destination path to save the file to.
        mat_nr: The material ID to export.
        '''
        from mitsuba.core.xml import load_dict
        props = {'type': 'blender'}
        b_mesh.calc_normals()
        b_mesh.calc_loop_triangles() # Compute the triangle tesselation
        if mat_nr == -1:
            name = b_name
            mat_nr=0 # Default value for blender
        else:
            name = "%s-%s" %(b_name, b_mesh.materials[mat_nr].name)
        props['name'] = name
        loop_tri_count = len(b_mesh.loop_triangles)
        if loop_tri_count == 0:
            export_ctx.log("Mesh: {} has no faces. Skipping.".format(name), 'WARN')
            return
        props['loop_tri_count'] = loop_tri_count

        if len(b_mesh.uv_layers) > 1:
            export_ctx.log("Mesh: '%s' has multiple UV layers. Mitsuba only supports one. Exporting the one set active for render."%name, 'WARN')
        for uv_layer in b_mesh.uv_layers:
            if uv_layer.active_render: # If there is only 1 UV layer, it is always active
                props['uvs'] = uv_layer.data[0].as_pointer()
                break

        for color_layer in b_mesh.vertex_colors:
            props['vertex_%s' % color_layer.name] = color_layer.data[0].as_pointer()

        props['loop_tris'] = b_mesh.loop_triangles[0].as_pointer()
        props['loops'] = b_mesh.loops[0].as_pointer()
        props['polys'] = b_mesh.polygons[0].as_pointer()
        props['verts'] = b_mesh.vertices[0].as_pointer()
        props['vert_count'] = len(b_mesh.vertices)
        # Apply coordinate change
        props['to_world'] = export_ctx.transform_matrix(matrix_world)
        props['mat_nr'] = mat_nr
        m_mesh = load_dict(props)

        if m_mesh.face_count() > 0: # Only save complete meshes
            m_mesh.write_ply(file_path) # Save as binary ply
            self.add_exported_mesh(b_name, mat_nr)
            return True
        return False

    def export_object_mat(self, object_instance, export_ctx, mat_nr):
        #object export
        b_object = object_instance.object
        if b_object.is_instancer and not b_object.show_instancer_for_render:
            return#don't export hidden mesh

        if mat_nr == -1:
            name = b_object.name_full
        else:
            name = "%s-%s" %(b_object.name_full, b_object.data.materials[mat_nr].name)

        relative_path = os.path.join("meshes", "%s.ply" % name)
        abs_path = os.path.join(export_ctx.directory, relative_path)

        if not object_instance.is_instance or b_object.name_full not in self.exported_meshes.keys() or mat_nr not in self.exported_meshes[b_object.name_full]:
            #save the mesh once, if it's not an instance, or if it's an instance and the original object was not exported
            if b_object.type != 'MESH':
                b_mesh = b_object.to_mesh()
            else:
                b_mesh = b_object.data
            if self.save_mesh(export_ctx, b_mesh, b_object.matrix_world, b_object.name_full, abs_path, mat_nr) and mat_nr >= 0:
                export_material(export_ctx, b_object.data.materials[mat_nr])
            if b_object.type != 'MESH':
                b_object.to_mesh_clear()

        if object_instance.is_instance or not b_object.parent or not b_object.parent.is_instancer:
            #we only write a shape plugin if an object is *not* an instance emitter, i.e. either an instance or an original object
            if mat_nr!=-1 and mat_nr not in self.exported_meshes[b_object.name_full]:
                return
            params = {'type':'ply'}
            params['filename'] = abs_path
            if(object_instance.is_instance):
                #instance, load referenced object saved before with another transform matrix
                original_transform = export_ctx.axis_mat @ b_object.matrix_world
                # remove the instancer object transform, apply the instance transform and shift coordinates
                params['to_world'] = export_ctx.transform_matrix(object_instance.matrix_world @ original_transform.inverted())
            #TODO: this only exports the mesh as seen in the viewport, not as should be rendered

            if mat_nr == -1:#default bsdf
                if not export_ctx.data_get('default-bsdf'):#we only need to add one of this, but we may have multiple emitter materials
                    default_bsdf = {
                        'type': 'twosided',
                        'id': 'default-bsdf',
                        'bsdf': {'type':'diffuse'}
                    }
                    export_ctx.data_add(default_bsdf)
                params['bsdf'] = {'type':'ref', 'id':'default-bsdf'}
            else:
                mat_id = "mat-%s" % b_object.data.materials[mat_nr].name
                if export_ctx.exported_mats.has_mat(mat_id):#add one emitter *and* one bsdf
                    mixed_mat = export_ctx.exported_mats.mats[mat_id]
                    params['bsdf'] = {'type':'ref', 'id':mixed_mat['bsdf']}
                    params['emitter'] = mixed_mat['emitter']
                else:
                    params['bsdf'] = {'type':'ref', 'id':mat_id}
            if object_instance.is_instance or not export_ctx.export_ids:
                export_ctx.data_add(params)
            else:
                mesh_id = "mesh-%s" % b_object.name_full
                if mat_nr != -1:
                    mesh_id += "-%d" % mat_nr
                export_ctx.data_add(params, name=mesh_id)

    def export_object(self, object_instance, export_ctx):
        mat_count = len(object_instance.object.data.materials)
        valid_mats=0
        for mat_nr in range(mat_count):
            if object_instance.object.data.materials[mat_nr] is not None:
                valid_mats += 1
                self.export_object_mat(object_instance, export_ctx, mat_nr)
        if valid_mats == 0: #no material, or no valid material
            self.export_object_mat(object_instance, export_ctx, -1)

        '''
        To avoid clutter in the XML file, we rename the mesh file if it has only one material.
        That way, we avoid having a bunch of 'MyMesh-MyMaterial.ply' in the file.
        '''
        name = object_instance.object.name_full
        nb_mats = len(self.exported_meshes[name])
        if nb_mats == 1:
            mat_id = self.exported_meshes[name][0]
            new_name = os.path.join("meshes", "%s.ply" % name)
            old_name = os.path.join("meshes", "%s-%s.ply" % (name, object_instance.object.data.materials[mat_id].name))

            old_path = os.path.join(export_ctx.directory, old_name)
            new_path = os.path.join(export_ctx.directory, new_name)

            # we can't check if the file exists already as it may be an old file with the same name,
            # so we do it like this:
            try:
                os.rename(old_path, new_path)
            except FileNotFoundError: #the mesh was already renamed
                pass

            #only rename in the XML if the object is not an instancer (instancers are not saved in the XML file)
            if object_instance.is_instance or not object_instance.object.parent or not object_instance.object.parent.is_instancer:
                last_key = next(reversed(export_ctx.scene_data)) # get the last added key
                assert(export_ctx.scene_data[last_key]['type'] == 'ply')
                export_ctx.scene_data[last_key]['filename'] = new_path
                #also rename the ID, instances have no ID
                if not object_instance.is_instance and export_ctx.export_ids:
                    export_ctx.scene_data[last_key]['id'] = "mesh-%s" % object_instance.object.name_full