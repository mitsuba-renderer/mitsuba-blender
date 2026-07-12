'''Blender version compatibility layer.

This is the only module allowed to inspect bpy.app.version. Whenever a
Blender release renames an API that the addon uses, the branch belongs
here, with a fallback for the oldest supported release (4.2 LTS).
'''
