from .direct import MyDirectIntegrator

def register():
  from mitsuba import register_integrator
  register_integrator("mydirect", lambda props: MyDirectIntegrator(props))