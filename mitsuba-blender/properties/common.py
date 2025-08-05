import bpy
from bpy.props import *
from bpy.types import PropertyGroup, Operator

import os, json
with open(os.path.join(os.path.dirname(__file__), "integrators.json")) as file:
    integrator_data = json.load(file)
with open(os.path.join(os.path.dirname(__file__), "samplers.json")) as file:
    sampler_data = json.load(file)
with open(os.path.join(os.path.dirname(__file__), "rfilters.json")) as file:
    rfilter_data = json.load(file)

def create_plugin_props(name, arg_dict, depth=1, prefix=""):
    '''
    Dynamically create a PropertyGroup for a given plugin defined in arg_dict.
    This allows us to avoid manually creating classes for each plugin (e.g. integrator, BSDF, etc.)

    name: the name of the plugin
    arg_dict: the labels, description and properties defined in the JSON plugin files
    depth: Recursion depth (for nested plugins, e.g. Stokes integrator) We only allow a certain amount of nesting, to avoid infinite definition of properties
    prefix: Prefix to use to declare a class with a unique name
    '''
    prefix += name.title().replace('.', '_')
    plugin_props = type("%sProps" % prefix, (PropertyGroup, ), {
        "args": arg_dict
    })
    bpy.utils.register_class(plugin_props)
    custom_draw = set() # List of parameter names that need to call their own draw function (nested plugins)
    props_draw  = set() # List of parameters to draw normally, using layout.prop()
    if 'parameters' in arg_dict:
        for param_name, param_dict in arg_dict['parameters'].items():
            param_type = param_dict['type']
            label = param_dict['label']
            description = param_dict['description'] if 'description' in param_dict else ''
            if 'advanced' in param_dict and param_dict['advanced']:
                continue # TODO
            if param_type == 'integer':
                props_draw.add(param_name)
                setattr(plugin_props, param_name, IntProperty(
                    name = label,
                    description = description,
                    default = param_dict.get('default', 0),
                    soft_min = param_dict.get('min', -2**31),
                    soft_max = param_dict.get('max', 2**31-1)
                ))
            elif param_type == 'boolean':
                props_draw.add(param_name)
                setattr(plugin_props, param_name, BoolProperty(
                    name = label,
                    description = description,
                    default = param_dict.get('default', False)
                ))
            elif param_type == 'float':
                props_draw.add(param_name)
                setattr(plugin_props, param_name, FloatProperty(
                    name = label,
                    description = description,
                    default = param_dict.get('default', 0.0),
                ))
            elif param_type == 'string':
                items = param_dict['items']
                props_draw.add(param_name)
                setattr(plugin_props, param_name, EnumProperty(
                    name = label,
                    items=[(a, a, a) for a in items],
                    default = param_dict['default'],
                ))
            # Nested plugin
            elif param_type == 'integrator' or param_type == 'list' and param_dict['values_type'] == 'integrator':
                enum_integrators = []
                # Nested Property group encapsulating the nested integrators
                nested_props_name = "%sNestedIntProps" % prefix
                nested_props = type(nested_props_name, (PropertyGroup, ), {})
                bpy.utils.register_class(nested_props)
                # Property group containint one property group per integrator
                int_props = type("%sIntegratorProps" % prefix, (PropertyGroup, ), {})
                bpy.utils.register_class(int_props)
                for int_name, int_params in integrator_data.items():
                    is_nested = False
                    if 'parameters' in int_params:
                        for param in int_params['parameters'].values():
                            if param['type'] == 'integrator' or param.get('values_type', '') == 'integrator':
                                is_nested = True
                                break
                    if not is_nested or is_nested and depth <= 2:
                        setattr(int_props, int_name, PointerProperty(
                            name = label,
                            description = description,
                            type = create_plugin_props(int_name, int_params, depth=depth+1, prefix=prefix)
                        ))
                        enum_integrators.append((int_name, int_params['label'], int_params['description']))

                setattr(nested_props, "active_integrator", EnumProperty(
                    name = "Integrator",
                    items = enum_integrators
                ))
                setattr(nested_props, "available_integrators", PointerProperty(
                    type = int_props
                ))

                if param_type == 'integrator':
                    def draw_int(self, layout):
                        layout = layout.box()
                        layout.prop(self, "active_integrator")
                        getattr(self.available_integrators, self.active_integrator).draw(layout)
                    setattr(nested_props, "draw", draw_int)
                    setattr(plugin_props, param_name, PointerProperty(
                        name = label,
                        description = description,
                        type = nested_props
                    ))
                else: # List of integrators
                    # In this case, we store the list in a Collection Property and nest it in a PropertyGroup, to add a custom draw method
                    collection_name = "%sIntCollectionProps" % prefix
                    collection_props = type(collection_name, (PropertyGroup, ), {
                        '__annotations__' : {
                            'collection' : CollectionProperty(
                                name = label,
                                description = description,
                                type = nested_props
                            ),
                            'selection' : IntProperty(
                                name = "Selected Integrator",
                                default = 0
                            ),
                            'count' : IntProperty(default=0) # Count of created instances, to give unique names
                        }
                    })
                    def new(self, name="Integrator"):
                        new_int = self.collection.add()
                        if self.count == 0:
                            new_int.name = name
                        else: # Avoid duplicate names
                            zero_count = len(str(self.count))
                            new_int.name = "%s_%s%d" % (name, '0'*(3-zero_count), self.count)
                        self.count += 1
                    setattr(collection_props, "new", new)
                    bpy.utils.register_class(collection_props)
                    def find_class(self, context):
                        '''
                        Look for the given class in the mitsuba settings
                        '''
                        settings = getattr(context.scene.mitsuba_engine.available_integrators, context.scene.mitsuba_engine.active_integrator)
                        while True:
                            for param in dir(settings):
                                prop = getattr(settings, param)
                                prop_type = type(prop).__name__
                                if 'IntCollection' in prop_type:
                                    if self.class_name == prop_type:
                                        return prop
                                    else:
                                        selection = prop.collection[prop.selection] # Currently selected integrator in the list
                                        settings = getattr(selection.available_integrators, selection.active_integrator)
                                        break # Go to the next depth in the param tree
                                elif 'NestedInt' in prop_type:
                                    settings = getattr(prop.available_integrators, prop.active_integrator)
                                    break # Go to the next depth in the param tree

                    def execute(self, context):
                        '''
                        add/remove an integrator
                        '''
                        if self.action == 'ADD':
                            settings = self.find_class(context)
                            settings.new()
                        else: # 'REMOVE
                            settings = self.find_class(context)
                            settings.collection.remove(settings.selection)
                            settings.selection = max(settings.selection-1, 0)
                        return {'FINISHED'}
                    # Custom operator to add an integrator
                    custom_name = "OT%s" % prefix
                    custom_id = "custom_ot.%s" % custom_name.lower()
                    custom_operator = type(custom_name, (Operator, ), {
                        'bl_label' : custom_name,
                        'bl_idname' : custom_id,
                        'bl_description' : "Add/Remove an integrator.",
                        'class_name' : collection_name,
                        '__annotations__' : {
                            'action' : EnumProperty(items=(
                                ('ADD', "Add", ""),
                                ('REMOVE', "Remove", "")
                            ))},
                        'find_class' : find_class,
                        'execute' : execute
                    })
                    bpy.utils.register_class(custom_operator)

                    def draw_coll(self, layout):
                        # TODO: add the option to hide this
                        layout.label(text = "Integrators List", icon='VIEW_CAMERA')
                        layout.template_list("UI_UL_list", "UL%s"%prefix, self, "collection", self, "selection", rows=4)
                        split = layout.split()
                        split.operator(custom_id, icon='ADD', text="").action = 'ADD'
                        split.operator(custom_id, icon='REMOVE', text="").action = 'REMOVE'
                        if len(self.collection) > self.selection:
                            layout.label(text="Integrator Settings", icon='TOOL_SETTINGS')
                            layout = layout.box()
                            # Nested integrator to display
                            integrator = self.collection[self.selection]
                            layout.prop(integrator, "active_integrator")
                            getattr(integrator.available_integrators, integrator.active_integrator).draw(layout)
                    setattr(collection_props, "draw", draw_coll)
                    setattr(plugin_props, param_name, PointerProperty(
                        name = label,
                        description = description,
                        type = collection_props))
                custom_draw.add(param_name)

            elif param_type == 'list':
                list_type = param_dict['values_type']
                if list_type == 'string':
                    choices = param_dict['choices']
                    for choice, label in choices.items():
                        props_draw.add(choice)
                        setattr(plugin_props, choice, BoolProperty(
                            name = label
                        ))
            else:
                raise NotImplementedError("Unsupported attribute type: %s in plugin '%s'" % (param_type, name))

    def draw(self, layout):
        if 'parameters' in arg_dict:
            for param_name in props_draw:
                layout.prop(self, param_name)
            for param_name in custom_draw:
                getattr(self, param_name).draw(layout)
    setattr(plugin_props, "draw", draw)

    def to_dict(self):
        '''
        Function that converts the plugin into a dict that can be loaded or savec by mitsuba's API
        '''
        plugin_params = { 'type' : name }
        if 'parameters' in self.args:
            for param_name, param in self.args['parameters'].items():
                if param['type'] in ('boolean', 'float', 'integer', 'string'):
                    plugin_params[param_name] = getattr(self, param_name)
                elif param_type == 'integrator':
                    prop = getattr(self, param_name)
                    plugin_params[param_name] = getattr(prop.available_integrators, prop.active_integrator).to_dict()
                elif param_type == 'list':
                    list_type = param['values_type']
                    if list_type == 'integrator':
                        for integrator in self.integrators.collection:
                            plugin_params[integrator.name] = getattr(integrator.available_integrators, integrator.active_integrator).to_dict()
                    elif list_type == 'string':
                        selected_items = []
                        for choice in param['choices']:
                            if getattr(self, choice):
                                selected_items.append("%s:%s" % (choice, choice)) #For AOVs, paris have same name and type
                        plugin_params[param_name] = ','.join(selected_items)
        return plugin_params
    setattr(plugin_props, "to_dict", to_dict)

    return plugin_props