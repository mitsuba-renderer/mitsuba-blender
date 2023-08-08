from .direct import MyDirectIntegrator
from .dummy_integrators import PSSMLT, PhotonMapper, VAPG, LPM

def register():
  from mitsuba import register_integrator
  register_integrator("mydirect", lambda props: MyDirectIntegrator(props))
  # dummy
  register_integrator("pssmlt", lambda props: PSSMLT(props))
  register_integrator("photonmapper", lambda props: PhotonMapper(props))
  # advanced
  register_integrator("vapg", lambda props: VAPG(props))
  register_integrator("lpm", lambda props: LPM(props))