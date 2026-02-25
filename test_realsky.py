import bpy

def is_realsky_enabled(scene):
    return hasattr(scene, 'sky_settings') and scene.sky_settings.enabled

def get_realsky_objects():
    names = ["Sun", "cirrus", "cirrocumulus", "altostratus", "altostratus_mist", "altostratus_billboard", "cumulus", "cumulus_mist", "cumulus_billboard"]
    return [bpy.data.objects.get(name) for name in names if bpy.data.objects.get(name) is not None]

print("RealSky enabled:", is_realsky_enabled(bpy.context.scene))
