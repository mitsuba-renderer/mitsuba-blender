def register():
    from . import (materials, textures, transforms, sockets)
    sockets.register()
    transforms.register()
    textures.register()
    materials.register()

def unregister():
    from . import (materials, textures, transforms, sockets)
    materials.unregister()
    textures.unregister()
    transforms.unregister()
    sockets.unregister()
