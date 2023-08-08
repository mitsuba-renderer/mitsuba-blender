import mitsuba as mi
from mitsuba import SamplingIntegrator

class Dummy(SamplingIntegrator):
    def __init__(self, props):
        SamplingIntegrator.__init__(self, props)

    def sample(self, scene, sampler, ray, medium, active):
        pass

    def integrator_sample(self, scene, sampler, rays, medium, active=True):
        pass

    def aov_names(self):
        return []

    def to_string(self):
        return "Dummy[]"

class PSSMLT(Dummy):
    def __init__(self, props):
        Dummy.__init__(self, props)
        self.bidirectional = props.get("bidirectional", True)
        self.luminanceSamples = props.get("luminanceSamples", 100000)

class PhotonMapper(Dummy):
    def __init__(self, props):
        Dummy.__init__(self, props)
        self.causticPhotons = props.get("causticPhotons", 250000)
        self.causticLookupRadius = props.get("causticLookupRadius", 0.0125)

class VAPG(Dummy):
    def __init__(self, props):
        Dummy.__init__(self, props)
        self.nee = props.get("nee", "always")
        self.sampleCombination = props.get("sampleCombination", "discard")
        self.distribution = props.get("distribution", "radiance")
        self.budgetType = props.get("budgetType", "seconds")
        self.budget = props.get("budget", 300)
        self.trainingIterations = props.get("trainingIterations", -1)

class LPM(Dummy):
    def __init__(self, props):
        Dummy.__init__(self, props)
        self.maxDepth = props.get("maxDepth", -1)
        self.rrDepth = props.get("rrDepth", 5)
        self.lpRatio = props.get("lpRatio", 1.0)
        self.initialRadius = props.get("initialRadius", 0.0)
        self.iterations = props.get("iterations", 2)
        self.cp_per_iter = props.get("cp_per_iter", 1)
        self.min_lp = props.get("min_lp", 5000)
        self.enableMerge = props.get("enableMerge", True)
        