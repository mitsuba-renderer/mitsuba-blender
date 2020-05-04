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

    def save_mesh(self, export_ctx, b_mesh, file_path, mat_nr):
        from mitsuba.render import Mesh
        from mitsuba.core import FileStream, Matrix4f
        #create a mitsuba mesh
        b_mesh.data.calc_loop_triangles()#compute the triangle tesselation
        if mat_nr == -1:
            name = b_mesh.name_full
            mat_nr=0#default value for blender
        else:
            name = "%s-%d" %(b_mesh.name_full, mat_nr)
        loop_tri_count = len(b_mesh.data.loop_triangles)
        if loop_tri_count == 0:
            warnings.warn("Mesh: {} has no faces. Skipping.".format(name), Warning)
            return

        if not b_mesh.data.uv_layers:
            uv_ptr = 0#nullptr
        else:
            if len(b_mesh.data.uv_layers) > 1:
                print("Mesh: '%s' has multiple UV layers. Mitsuba only supports one. Exporting the one set active for render."%name)
            for uv_layer in b_mesh.data.uv_layers:
                if uv_layer.active_render:#if there is only 1 UV layer, it is always active
                    uv_ptr = uv_layer.data[0].as_pointer()
                    break

        if not b_mesh.data.vertex_colors:
            col_ptr = 0#nullptr
        else:
            if len(b_mesh.data.vertex_colors) > 1:
                print("Mesh: '%s' has multiple vertex color layers. Mitsuba only supports one. Exporting the one set active for render."%name)
            for color_layer in b_mesh.data.vertex_colors:
                if color_layer.active_render:#if there is only 1 UV layer, it is always active
                    col_ptr = color_layer.data[0].as_pointer()
                    break

        loop_tri_ptr = b_mesh.data.loop_triangles[0].as_pointer()
        loop_ptr = b_mesh.data.loops[0].as_pointer()
        poly_ptr = b_mesh.data.polygons[0].as_pointer()
        vert_ptr = b_mesh.data.vertices[0].as_pointer()
        vert_count = len(b_mesh.data.vertices)#TODO: maybe avoid calling len()
        #apply coordinate change
        to_world = export_ctx.transform_matrix(b_mesh.matrix_world)
        m_mesh = Mesh(name, loop_tri_count, loop_tri_ptr, loop_ptr,
                        vert_count, vert_ptr, poly_ptr,
                        uv_ptr, col_ptr, mat_nr, to_world)
        if m_mesh.face_count() > 0:#only save complete meshes
            mesh_fs = FileStream(file_path, FileStream.ETruncReadWrite)
            m_mesh.write_ply(mesh_fs)#save as binary ply
            mesh_fs.close()
            self.add_exported_mesh(b_mesh.name_full, mat_nr)
            return True
        return False

    def export_mesh_mat(self, mesh_instance, export_ctx, mat_nr):
        #object export
        b_mesh = mesh_instance.object
        if b_mesh.is_instancer and not b_mesh.show_instancer_for_render:
            return#don't export hidden mesh

        if mat_nr == -1:
            name = b_mesh.name_full
        else:
            name = "%s-%d" %(b_mesh.name_full, mat_nr)

        relative_path = os.path.join("meshes", "%s.ply" % name)
        abs_path = os.path.join(export_ctx.directory, relative_path)

        if not mesh_instance.is_instance or b_mesh.name_full not in self.exported_meshes.keys() or mat_nr not in self.exported_meshes[b_mesh.name_full]:
            #save the mesh once, if it's not an instance, or if it's an instance and the original object was not exported
            if self.save_mesh(export_ctx, b_mesh, abs_path, mat_nr) and mat_nr >= 0:
                export_material(export_ctx, b_mesh.data.materials[mat_nr])

        if mesh_instance.is_instance or not b_mesh.parent or not b_mesh.parent.is_instancer:
            #we only write a shape plugin if an object is *not* an instance emitter, i.e. either an instance or an original object
            if mat_nr!=-1 and mat_nr not in self.exported_meshes[b_mesh.name_full]:
                return
            params = {'type':'ply'}
            params['filename'] = abs_path
            if(mesh_instance.is_instance):
                #instance, load referenced object saved before with another transform matrix
                original_transform = export_ctx.axis_mat @ b_mesh.matrix_world
                # remove the instancer object transform, apply the instance transform and shift coordinates
                params['to_world'] = export_ctx.transform_matrix(mesh_instance.matrix_world @ original_transform.inverted())
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
                mat_id = b_mesh.data.materials[mat_nr].name
                if export_ctx.exported_mats.has_mat(mat_id):#add one emitter *and* one bsdf
                    mixed_mat = export_ctx.exported_mats.mats[mat_id]
                    params['bsdf'] = {'type':'ref', 'id':mixed_mat['bsdf']}
                    params['emitter'] = mixed_mat['emitter']
                else:
                    params['bsdf'] = {'type':'ref', 'id':mat_id}

            export_ctx.data_add(params)

    def export_mesh(self, mesh_instance, export_ctx):
        mat_count = len(mesh_instance.object.data.materials)
        valid_mats=0
        for mat_nr in range(mat_count):
            if mesh_instance.object.data.materials[mat_nr] is not None:
                valid_mats += 1
                self.export_mesh_mat(mesh_instance, export_ctx, mat_nr)
        if valid_mats == 0: #no material, or no valid material
            self.export_mesh_mat(mesh_instance, export_ctx, -1)

        '''
        To avoid clutter in the XML file, we rename the mesh file if it has only one material.
        That way, we avoid having a bunch of 'Mesh-0.ply' in the file.
        '''
        name = mesh_instance.object.name
        nb_mats = len(self.exported_meshes[name])
        if nb_mats == 1:
            mat_id = self.exported_meshes[name][0]
            new_name = os.path.join("meshes", "%s.ply" % name)
            old_name = os.path.join("meshes", "%s-%d.ply" % (name, mat_id))

            old_path = os.path.join(export_ctx.directory, old_name)
            new_path = os.path.join(export_ctx.directory, new_name)

            # we can't check if the file exists already as it may be an old file with the same name,
            # so we do it like this:
            try:
                os.rename(old_path, new_path)
            except FileNotFoundError: #the mesh was already renamed
                pass

            #only rename in the XML if the object is not an instancer (instancers are not saved in the XML file)
            if mesh_instance.is_instance or not mesh_instance.object.parent or not mesh_instance.object.parent.is_instancer:
                last_key = next(reversed(export_ctx.scene_data)) # get the last added key
                assert(export_ctx.scene_data[last_key]['type'] == 'ply')
                export_ctx.scene_data[last_key]['filename'] = new_path
