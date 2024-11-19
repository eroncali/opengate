from box import Box
from scipy.spatial.transform import Rotation

import opengate_core as g4
from .base import (
    SourceBase,
    all_beta_plus_radionuclides,
    read_beta_plus_spectra,
    compute_cdf_and_total_yield,
)
from ..base import process_cls
from ..utility import g4_units
from ..exception import fatal, warning


def _generic_source_default_position():
    return Box(
        {
            "type": "point",
            "radius": 0,
            "sigma_x": 0,
            "sigma_y": 0,
            "size": [0, 0, 0],
            "translation": [0, 0, 0],
            "rotation": Rotation.identity().as_matrix(),
            "confine": None,
        }
    )


def _generic_source_default_direction():
    return Box(
        {
            "type": "iso",
            "theta": [0, 180 * g4_units.deg],
            "phi": [0, 360 * g4_units.deg],
            "momentum": [0, 0, 1],
            "focus_point": [0, 0, 0],
            "sigma": [0, 0],
            "acceptance_angle": _generic_source_default_aa(),
            "accolinearity_flag": False,
            "histogram_theta_weights": [],
            "histogram_theta_angles": [],
            "histogram_phi_weights": [],
            "histogram_phi_angles": [],
        }
    )


def _generic_source_default_aa():
    deg = g4_units.deg
    return Box(
        {
            "skip_policy": "SkipEvents",
            "volumes": [],
            "intersection_flag": False,
            "normal_flag": False,
            "normal_vector": [0, 0, 1],
            "normal_tolerance": 3 * deg,
        }
    )


def _generic_source_default_energy():
    return Box(
        {
            "type": "mono",
            "mono": 0,
            "sigma_gauss": 0,
            "is_cdf": False,
            "min_energy": None,
            "max_energy": None,
            "spectrum_type": None,
        }
    )


def _setter_hook_generic_source_particle(self, particle):
    # particle must be a str
    if not isinstance(particle, str):
        fatal(f"the .particle user info must be a str, while it is {type(str)}")
    # if it does not start with ion, we consider this is a simple particle (gamma, e+ etc)
    if not particle.startswith("ion"):
        return particle
    # if start with ion, it is like 'ion 9 18' with Z A E
    words = particle.split(" ")
    if len(words) > 1:
        self.ion.Z = int(words[1])
    if len(words) > 2:
        self.ion.A = int(words[2])
    if len(words) > 3:
        self.ion.E = int(words[3])
    return particle


class GenericSource(SourceBase, g4.GateGenericSource):
    """
    GenericSource close to the G4 SPS, but a bit simpler.
    The G4 source created by this class is GateGenericSource.
    """

    # hints for IDE
    particle: str
    ion: Box
    weight: float
    weight_sigma: float
    user_particle_life_time: float
    tac_times: list
    tac_activities: list
    direction_relative_to_attached_volume: bool
    position: Box
    direction: Box
    energy: Box

    user_info_defaults = {
        "particle": (
            "gamma",
            {
                "doc": "Name of the particle generated by the source (gamma, e+ ... or an ion such as 'ion 9 18')",
                "setter_hook": _setter_hook_generic_source_particle,
            },
        ),
        "ion": (
            Box({"Z": 0, "A": 0, "E": 0}),
            {
                "doc": "If the particle is an ion, you must set Z: Atomic Number, A: Atomic Mass (nn + np +nlambda), E: Excitation energy (i.e. for metastable)"
            },
        ),
        "weight": (
            -1,
            {"doc": "Particle initial weight (for variance reduction technique)"},
        ),
        "weight_sigma": (
            -1,
            {
                "doc": "if not negative, the weights of the particle are a Gaussian distribution with this sigma"
            },
        ),
        "user_particle_life_time": (
            -1,
            {"doc": "FIXME "},
        ),
        "tac_times": (
            None,
            {
                "doc": "TAC: Time Activity Curve, this set the vector for the times. Must be used with tac_activities."
            },
        ),
        "tac_activities": (
            None,
            {
                "doc": "TAC: Time Activity Curve, this set the vector for the activities. Must be used with tac_times."
            },
        ),
        "direction_relative_to_attached_volume": (
            False,
            {
                "doc": "Should we update the direction of the particle "
                "when the volume is moved (with dynamic parametrisation)?"
            },
        ),
        "position": (
            _generic_source_default_position(),
            {"doc": "Define the position of the primary particles"},
        ),
        "direction": (
            _generic_source_default_direction(),
            {"doc": "Define the direction of the primary particles"},
        ),
        "energy": (
            _generic_source_default_energy(),
            {"doc": "Define the energy of the primary particles"},
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self.__initcpp__()
        self.total_zero_events = 0
        self.total_skipped_events = 0
        if not self.user_info.particle.startswith("ion"):
            return
        words = self.user_info.particle.split(" ")
        if len(words) > 1:
            self.user_info.ion.Z = words[1]
        if len(words) > 2:
            self.user_info.ion.A = words[2]
        if len(words) > 3:
            self.user_info.ion.E = words[3]

    def __initcpp__(self):
        g4.GateGenericSource.__init__(self)

    def initialize(self, run_timing_intervals):
        if not isinstance(self.position, Box):
            fatal(
                f"Generic Source: user_info.position must be a Box, but is: {self.position}"
            )
        if not isinstance(self.direction, Box):
            fatal(
                f"Generic Source: user_info.direction must be a Box, but is: {self.direction}"
            )
        if not isinstance(self.energy, Box):
            fatal(
                f"Generic Source: user_info.energy must be a Box, but is: {self.energy}"
            )

        if self.particle == "back_to_back":
            # force the energy to 511 keV
            self.energy.type = "mono"
            self.energy.mono = 511 * g4_units.keV

        # check energy type
        l = [
            "mono",
            "gauss",
            "F18_analytic",
            "O15_analytic",
            "C11_analytic",
            "histogram",
            "spectrum_discrete",
            "spectrum_histogram",
            "range",
        ]
        l.extend(all_beta_plus_radionuclides)
        if not self.energy.type in l:
            fatal(
                f"Cannot find the energy type {self.energy.type} for the source {self.name}.\n"
                f"Available types are {l}"
            )

        # check energy spectrum type if not None
        valid_spectrum_types = [
            "discrete",
            "histogram",
            "interpolated",
        ]
        if self.energy.spectrum_type is not None:
            if self.energy.spectrum_type not in valid_spectrum_types:
                fatal(
                    f"Cannot find the energy spectrum type {self.energy.spectrum_type} for the source {self.name}.\n"
                    f"Available types are {valid_spectrum_types}"
                )

        # special case for beta plus energy spectra
        # FIXME put this elsewhere
        if self.particle == "e+":
            if self.energy.type in all_beta_plus_radionuclides:
                data = read_beta_plus_spectra(self.user_info.energy.type)
                ene = data[:, 0] / 1000  # convert from KeV to MeV
                proba = data[:, 1]
                cdf, total = compute_cdf_and_total_yield(proba, ene)
                # total = total * 1000  # (because was in MeV)
                # self.user_info.activity *= total
                self.energy.is_cdf = True
                self.SetEnergyCDF(ene)
                self.SetProbabilityCDF(cdf)

        self.update_tac_activity()

        # histogram parameters: histogram_weight, histogram_energy"
        ene = self.energy
        if ene.type == "histogram":
            if len(ene.histogram_weight) != len(ene.histogram_energy):
                fatal(
                    f'For the source {self.name}, the parameters "energy", '
                    f'"histogram_energy" and "histogram_weight" must have the same length'
                )

        # check direction type
        l = ["iso", "histogram", "momentum", "focused", "beam2d"]
        if not self.direction.type in l:
            fatal(
                f"Cannot find the direction type {self.direction.type} for the source {self.name}.\n"
                f"Available types are {l}"
            )

        # logic for half life and user_particle_life_time
        if self.half_life > 0:
            # if the user set the half life and not the user_particle_life_time
            # we force the latter to zero
            if self.user_particle_life_time < 0:
                self.user_particle_life_time = 0

        # initialize
        SourceBase.initialize(self, run_timing_intervals)

        if self.n > 0 and self.activity > 0:
            fatal(
                f"Cannot use both the two parameters 'n' and 'activity' at the same time. "
            )
        if self.n == 0 and self.activity == 0:
            fatal(f"You must set one of the two parameters 'n' or 'activity'.")
        if self.activity > 0:
            self.n = 0
        if self.n > 0:
            self.activity = 0
        # warning for non-used ?

        # check confine
        if self.position.confine:
            if self.position.type == "point":
                warning(
                    f"In source {self.name}, "
                    f"confine is used, while position.type is point ... really ?"
                )

    def check_ui_activity(self, ui):
        # FIXME: This should rather be a function than a method
        # FIXME: self actually holds the parameters n and activity, but the ones from ui are used here.
        if ui.n > 0 and ui.activity > 0:
            fatal(f"Cannot use both n and activity, choose one: {self.user_info}")
        if ui.n == 0 and ui.activity == 0:
            fatal(f"Choose either n or activity : {self.user_info}")
        if ui.activity > 0:
            ui.n = 0
        if ui.n > 0:
            ui.activity = 0

    def check_confine(self, ui):
        # FIXME: This should rather be a function than a method
        # FIXME: self actually holds the parameters n and activity, but the ones from ui are used here.
        if ui.position.confine:
            if ui.position.type == "point":
                warning(
                    f"In source {ui.name}, "
                    f"confine is used, while position.type is point ... really ?"
                )

    def prepare_output(self):
        SourceBase.prepare_output(self)
        # store the output from G4 object
        self.total_zero_events = self.GetTotalZeroEvents()
        self.total_skipped_events = self.GetTotalSkippedEvents()

    def update_tac_activity(self):
        if self.tac_times is None and self.tac_activities is None:
            return
        if len(self.tac_times) != len(self.tac_activities):
            fatal(
                f"option tac_activities must have the same size as tac_times in source '{self.name}'"
            )
        # it is important to set the starting time for this source as the tac
        # may start later than the simulation timing
        self.start_time = self.tac_times[0]
        self.activity = self.tac_activities[0]
        self.SetTAC(self.tac_times, self.tac_activities)

    def can_predict_number_of_events(self):
        aa = self.direction.acceptance_angle
        if aa.intersection_flag or aa.normal_flag:
            if aa.skip_policy == "ZeroEnergy":
                return True
            return False
        return True

class TemplateSource(SourceBase):
    """
    Source template: to create a new type of source, copy-paste
    this file and adapt to your needs.
    Also declare the source type in the file helpers_source.py
    """

    type_name = "TemplateSource"

    @staticmethod
    def set_default_user_info(user_info):
        SourceBase.set_default_user_info(user_info)
        # initial user info
        user_info.float_value = None
        user_info.vector_value = None

    def create_g4_source(self):
        return opengate_core.GateTemplateSource()

    def __init__(self, user_info):
        super().__init__(user_info)

    def initialize(self, run_timing_intervals):
        # Check user_info type
        if self.user_info.float_value is None:
            fatal(
                f"Error for source {self.user_info.name}, float_value must be a float"
            )
        if self.user_info.vector_value is None:
            fatal(
                f"Error for source {self.user_info.name}, vector_value must be a vector"
            )

        # initialize
        SourceBase.initialize(self, run_timing_intervals)

process_cls(GenericSource)
