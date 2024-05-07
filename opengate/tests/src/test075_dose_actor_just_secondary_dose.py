#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import opengate as gate
from opengate.tests import utility
from scipy.spatial.transform import Rotation
import numpy as np
import itk
import uproot



def test075_2(img_arr_1,img_arr_2, tol = 0.01):

    img_arr_1[:,10:30,10:30] = 0
    img_arr_2[:,10:30,10:30] = 0

    print('Deposited OOF dose: ',np.sum(img_arr_2), 'Gy')
    print('Deposited OOF dose by secondaries: ', np.sum(img_arr_1), 'Gy')
    if np.abs(np.sum(img_arr_1) - np.sum(img_arr_2))/np.sum(img_arr_2) < tol and np.sum(img_arr_2) !=0:
        return True
    else :
        return False


if __name__ == "__main__":
    paths = utility.get_default_test_paths(__file__)
    output_path = paths.output

    # create the simulation
    sim = gate.Simulation()

    # main options
    sim.g4_verbose = False
    # sim.visu = True
    sim.visu_type = "vrml"
    sim.check_volumes_overlap = False
    # sim.running_verbose_level = gate.logger.EVENT
    sim.number_of_threads = 1
    sim.random_seed = "auto"

    # units
    um = gate.g4_units.um
    m = gate.g4_units.m
    km = gate.g4_units.km
    mm = gate.g4_units.mm
    cm = gate.g4_units.cm
    nm = gate.g4_units.nm
    Bq = gate.g4_units.Bq
    MeV = gate.g4_units.MeV
    keV = gate.g4_units.keV
    sec = gate.g4_units.s
    gcm3 = gate.g4_units["g/cm3"]

    #  adapt world size
    world = sim.world
    world.size = [1 * m, 1 * m, 1 * m]
    world.material = "G4_Galactic"
    
    
    water_box = sim.add_volume("Box","water_box")
    water_box.size = [40*cm,40*cm,20*cm]
    water_box.material = 'G4_WATER'
    water_box.mother = world.name


    sim.volume_manager.material_database.add_material_weights(
        "Tungsten",
        ["W"],
        [1],
        19.3 * gcm3,
    )
    W_box = sim.add_volume("Box","tungsten_box")
    W_box.size = [1*cm,1*cm,1*cm]
    W_box.mother = water_box.name
    W_box.material = 'Tungsten'





    source = sim.add_source("GenericSource", "photon_source")
    source.particle = "gamma"
    source.position.type = "box"
    source.mother = world.name
    source.position.size = [0.5 * nm, 0.5*nm,  0* nm]
    source.direction.type = "momentum"
    source.position.translation = [0,0,11*cm]
    source.direction.momentum = [0, 0, -1]
    source.energy.type = "mono"
    source.energy.mono = 2 * MeV
    source.n = 10000



    ### First dose actor : normal one

    dose = sim.add_actor("DoseActor", "dose")
    dose.output = paths.output / "test075_normal_dose_actor_for_secondary.mhd"
    dose.mother = water_box.name
    dose.size = [40, 40, 20]
    mm = gate.g4_units.mm
    # ts = [1*cm, 1*cm, 1 * cm]
    dose.spacing = [1*cm, 1*cm, 1 * cm]
    dose.uncertainty = False
    dose.dose = False
    dose.hit_type = "random"

    ### Second dose actor : no primary photon dose

    dose_sec = sim.add_actor("DoseActorSecondariesFromPhotons", "dose_sec")
    dose_sec.output = paths.output / "test075_normal_dose_sec_actor_for_secondary.mhd"
    dose_sec.mother = water_box.name
    dose_sec.size = [40, 40, 20]
    mm = gate.g4_units.mm
    dose_sec.spacing = [1*cm, 1*cm, 1 * cm]
    dose_sec.uncertainty = False
    dose_sec.dose = False
    dose_sec.hit_type = "random"
    
    


    # stat actor
    s = sim.add_actor("SimulationStatisticsActor", "Stats")
    s.track_types_flag = True

    # Physic list and cuts
    sim.physics_manager.physics_list_name = "G4EmStandardPhysics_option3"
    sim.physics_manager.enable_decay = False
    sim.physics_manager.global_production_cuts.gamma = 1 * um
    sim.physics_manager.global_production_cuts.electron = 1 * um
    sim.physics_manager.global_production_cuts.positron = 1 * um

    # go !
    sim.run()
    output = sim.output

    img_dose = itk.imread(paths.output / "test075_normal_dose_actor_for_secondary-edep.mhd")
    arr_dose = itk.GetArrayFromImage(img_dose)

    img_dose_sec = itk.imread(paths.output / "test075_normal_dose_sec_actor_for_secondary-edep.mhd")
    arr_dose_sec = itk.GetArrayFromImage(img_dose_sec)

    is_ok = test075_2(arr_dose_sec,arr_dose)
    utility.test_ok(is_ok)
