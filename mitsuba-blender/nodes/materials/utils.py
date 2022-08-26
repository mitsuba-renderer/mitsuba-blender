from bpy.props import BoolProperty, EnumProperty, FloatProperty

IOR_FLOAT_PRECISION = 5
IOR_PRESETS = (
    # (mitsuba_id, value, display_name)
    ('acetone', 1.36, 'Acetone'),
    ('acrylic glass', 1.49, 'Acrylic glass'),
    ('air', 1.00028, 'Air'),
    ('amber', 1.55, 'Amber'),
    ('benzene', 1.501, 'Benzene'),
    ('bk7', 1.5046, 'BK7'),
    ('bromine', 1.661, 'Bromine'),
    ('carbon dioxide', 1.00045, 'Carbon dioxide'),
    ('carbon tetrachloride', 1.461, 'Carbon tetrachloride'),
    ('diamond', 2.419, 'Diamond'),
    ('ethanol', 1.361, 'Ethanol'),
    ('fused quartz', 1.458, 'Fused quartz'),
    ('glycerol', 1.4729, 'Glycerol'),
    ('helium', 1.00004, 'Helium'),
    ('hydrogen', 1.00013, 'Hydrogen'),
    ('pet', 1.575, 'PET'),
    ('polypropylene', 1.49, 'Polypropylene'),
    ('pyrex', 1.470, 'Pyrex'),
    ('silicone oil', 1.52045, 'Silicone oil'),
    ('sodium chloride', 1.544, 'Sodium chloride'),
    ('vacuum', 1.0, 'Vacuum'),
    ('water', 1.3330, 'Water'),
    ('water ice', 1.31, 'Water ice'),
)

def _generate_ior_dict():
    dict = {}
    enum = [('custom', 'Custom', '', 0)]
    for i, (mitsuba_name, value, display_name) in enumerate(IOR_PRESETS):
        enum.append((mitsuba_name, display_name, '', i+1))
        dict[mitsuba_name] = value
    return enum, dict

class OnesidedIORPropertyHelper:
    '''
    Helper class for transmissive material with IOR properties
    '''
    eta_enum_items, eta_value_dict = _generate_ior_dict()

    def _update_eta_enum(self, enum_prop, value_prop, update_prop):
        enum_value = getattr(self, enum_prop)
        if enum_value != 'custom':
            # We don't perform the value update logic in that situation
            setattr(self, update_prop, False)
            setattr(self, value_prop, OnesidedIORPropertyHelper.eta_value_dict[enum_value])

    def _update_eta_value(self, enum_prop, value_prop, update_prop):
        if getattr(self, update_prop):
            setattr(self, enum_prop, 'custom')
        else:
            setattr(self, update_prop, True)
    
    eta_need_value_update: BoolProperty(default=True)
    eta_enum: EnumProperty(items=eta_enum_items, 
                                name='IOR Preset', 
                                update=lambda self, context: self._update_eta_enum('eta_enum', 'eta_value', 'eta_need_value_update'))
    eta_value: FloatProperty(name='IOR Value',
                                min=1, 
                                precision=IOR_FLOAT_PRECISION, 
                                update=lambda self, context: self._update_eta_value('eta_enum', 'eta_value', 'eta_need_value_update'))

    def draw_ior_props(self, context, layout):
        layout.label(text='IOR')
        split = layout.split(factor=0.5)
        split.prop(self, 'eta_enum', text='')
        split.prop(self, 'eta_value', text='')

    def write_ior_props_to_dict(self, dict, export_context):
        dict['eta'] = self.eta_value if self.eta_enum == 'custom' else self.eta_enum

class TwosidedIORPropertyHelper:
    '''
    Helper class for transmissive material with interior/exterior IOR properties
    '''
    ior_enum_items, ior_value_dict = _generate_ior_dict()

    def _update_ior_enum(self, enum_prop, value_prop, update_prop):
        enum_value = getattr(self, enum_prop)
        if enum_value != 'custom':
            # We don't perform the value update logic in that situation
            setattr(self, update_prop, False)
            setattr(self, value_prop, TwosidedIORPropertyHelper.ior_value_dict[enum_value])

    def _update_ior_value(self, enum_prop, value_prop, update_prop):
        if getattr(self, update_prop):
            setattr(self, enum_prop, 'custom')
        else:
            setattr(self, update_prop, True)
    
    int_ior_need_value_update: BoolProperty(default=True)
    int_ior_enum: EnumProperty(items=ior_enum_items, 
                                name='IOR Preset', 
                                update=lambda self, context: self._update_ior_enum('int_ior_enum', 'int_ior_value', 'int_ior_need_value_update'))
    int_ior_value: FloatProperty(name='IOR Value',
                                min=1, 
                                precision=IOR_FLOAT_PRECISION, 
                                update=lambda self, context: self._update_ior_value('int_ior_enum', 'int_ior_value', 'int_ior_need_value_update'))

    ext_ior_need_value_update: BoolProperty(default=True)
    ext_ior_enum: EnumProperty(items=ior_enum_items, 
                                name='IOR Preset',
                                update=lambda self, context: self._update_ior_enum('ext_ior_enum', 'ext_ior_value', 'ext_ior_need_value_update'))
    ext_ior_value: FloatProperty(name='IOR Value',
                                min=1, 
                                precision=IOR_FLOAT_PRECISION, 
                                update=lambda self, context: self._update_ior_value('ext_ior_enum', 'ext_ior_value', 'ext_ior_need_value_update'))

    def draw_ior_props(self, context, layout):
        layout.label(text='Interior IOR')
        split = layout.split(factor=0.5)
        split.prop(self, 'int_ior_enum', text='')
        split.prop(self, 'int_ior_value', text='')

        layout.label(text='Exterior IOR')
        split = layout.split(factor=0.5)
        split.prop(self, 'ext_ior_enum', text='')
        split.prop(self, 'ext_ior_value', text='')

    def write_ior_props_to_dict(self, dict, export_context):
        dict['int_ior'] = self.int_ior_value if self.int_ior_enum == 'custom' else self.int_ior_enum
        dict['ext_ior'] = self.ext_ior_value if self.ext_ior_enum == 'custom' else self.ext_ior_enum

class ConductorPropertyHelper:
    '''
    Helper class for conductor specific node properties
    '''
    conductor_enum_items = (
        ('none', 'Custom', '', 0),
        ('a-C', 'Amorphous carbon', '', 1),
        ('Ag', 'Silver', '', 2),
        ('Al', 'Aluminium', '', 3),
        ('AlAs', 'Cubic aluminium arsenide', '', 4),
        ('AlSb', 'Cubic aluminium antimonide', '', 5),
        ('Au', 'Gold', '', 6),
        ('Be', 'Polycrystalline beryllium', '', 7),
        ('Cr', 'Chromium', '', 8),
        ('CsI', 'Cubic caesium iodide', '', 9),
        ('Cu', 'Copper', '', 10),
        ('Cu2O', 'Copper (I) oxide', '', 11),
        ('CuO', 'Copper (II) oxide', '', 12),
        ('d-C', 'Cubic diamond', '', 13),
        ('Hg', 'Mercury', '', 14),
        ('HgTe', 'Mercury telluride', '', 15),
        ('Ir', 'Iridium', '', 16),
        ('K', 'Polycrystalline potassium', '', 17),
        ('Li', 'Lithium', '', 18),
        ('MgO', 'Magnesium oxide', '', 19),
        ('Mo', 'Molybdenum', '', 20),
        ('Na_palik', 'Sodium', '', 21),
        ('Nb', 'Niobium', '', 22),
        ('Ni_palik', 'Nickel', '', 23),
        ('Rh', 'Rhodium', '', 24),
        ('Se', 'Selenium', '', 25),
        ('SiC', 'Hexagonal silicon carbide', '', 26),
        ('SnTe', 'Tin telluride', '', 27),
        ('Ta', 'Tantalum', '', 28),
        ('Te', 'Trigonal tellurium', '', 29),
        ('ThF4', 'Polycryst. thorium (IV) fluoride', '', 30),
        ('TiC', 'Polycrystalline titanium carbide', '', 31),
        ('TiN', 'Titanium nitride', '', 32),
        ('TiO2', 'Tetragonal titan. dioxide', '', 33),
        ('VC', 'Vanadium carbide', '', 34),
        ('V_palik', 'Vanadium', '', 35),
        ('VN', 'Vanadium nitride', '', 36),
        ('W', 'Tungsten', '', 37),
    )
    
    def _update_conductor_enum(self, context):
        should_enable_mat_params = self.conductor_enum == 'none'
        if 'Eta' in self.inputs and 'K' in self.inputs:
            self.inputs['Eta'].enabled = should_enable_mat_params
            self.inputs['K'].enabled = should_enable_mat_params

    conductor_enum: EnumProperty(items=conductor_enum_items,
                                name='Conductor Preset',
                                update=_update_conductor_enum)

    def add_conductor_inputs(self):
        self.add_input('MitsubaSocketFloatTextureUnbounded', 'Eta', default=0)
        self.add_input('MitsubaSocketFloatTextureUnbounded', 'K', default=1)

    def draw_conductor_props(self, context, layout):
        split = layout.split(factor=0.3)
        split.label(text='Material')
        split.prop(self, 'conductor_enum', text='')

    def write_conductor_props_to_dict(self, dict, export_context):
        if self.conductor_enum == 'none':
            dict['eta'] = self.inputs['Eta'].to_dict(export_context)
            dict['k'] = self.inputs['K'].to_dict(export_context)
        else:
            dict['material'] = self.conductor_enum

class RoughnessPropertyHelper:
    '''
    Helper class for isotropic rough material nodes
    '''
    distribution_enum_items = (
        ('beckmann', 'Beckmann', '', 0),
        ('ggx', 'GGX', '', 1),
    )

    distribution: EnumProperty(items=distribution_enum_items,
                                name='Microfacet Model')

    sample_visible: BoolProperty(default=True, name='Visible Sampling')

    def add_roughness_inputs(self):
        self.add_input('MitsubaSocketFloatTextureUnbounded', 'Alpha', default=0.1)

    def draw_roughness_props(self, context, layout):
        layout.prop(self, 'distribution', text='')
        layout.prop(self, 'sample_visible')

    def write_roughness_props_to_dict(self, dict, export_context):
        dict['distribution'] = self.distribution
        dict['sample_visible'] = self.sample_visible
        if self.inputs['Alpha'].enabled:
            dict['alpha'] = self.inputs['Alpha'].to_dict(export_context)

class AnisotropicRoughnessPropertyHelper(RoughnessPropertyHelper):
    '''
    Helper class for anisotropic rough material nodes
    '''
    def _update_anisotropic(self, context):
        if 'Alpha' in self.inputs and 'Alpha U' in self.inputs and 'Alpha V' in self.inputs:
            use_anisotropic = self.anisotropic
            self.inputs['Alpha'].enabled = not use_anisotropic
            self.inputs['Alpha U'].enabled = use_anisotropic
            self.inputs['Alpha V'].enabled = use_anisotropic

    anisotropic: BoolProperty(default=False, name='Anisotropic Roughness', update=_update_anisotropic)

    def add_roughness_inputs(self):
        super().add_roughness_inputs()
        self.add_input('MitsubaSocketFloatTextureUnbounded', 'Alpha U', default=0.1).enabled = False
        self.add_input('MitsubaSocketFloatTextureUnbounded', 'Alpha V', default=0.1).enabled = False

    def draw_roughness_props(self, context, layout):
        super().draw_roughness_props(context, layout)
        layout.prop(self, 'anisotropic')

    def write_roughness_props_to_dict(self, dict, export_context):
        super().write_roughness_props_to_dict(dict, export_context)
        if self.anisotropic:
            dict['alpha_u'] = self.inputs['Alpha U'].to_dict(export_context)
            dict['alpha_v'] = self.inputs['Alpha V'].to_dict(export_context)
