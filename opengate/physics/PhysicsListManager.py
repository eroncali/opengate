import sys

import opengate_core as g4
from ..helpers import fatal
from ..GateObjects import GateObjectSingleton


class PhysicsListManager(GateObjectSingleton):
    # Names of the physics constructors that can be created dynamically
    available_g4_physics_constructors = [
        "G4EmStandardPhysics",
        "G4EmStandardPhysics_option1",
        "G4EmStandardPhysics_option2",
        "G4EmStandardPhysics_option3",
        "G4EmStandardPhysics_option4",
        "G4EmStandardPhysicsGS",
        "G4EmLowEPPhysics",
        "G4EmLivermorePhysics",
        "G4EmLivermorePolarizedPhysics",
        "G4EmPenelopePhysics",
        "G4EmDNAPhysics",
        "G4OpticalPhysics",
    ]

    def __init__(self, physics_manager, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.physics_manager = physics_manager
        self.created_physics_list_classes = {}
        self.create_physics_list_classes()

    def create_physics_list_classes(self):
        for g4pc_name in self.available_g4_physics_constructors:
            self.created_physics_list_classes[
                g4pc_name
            ] = create_modular_physics_list_class(g4pc_name)

    def get_physics_list(self, physics_list_name):
        if physics_list_name in self.created_physics_list_classes:
            return self.created_physics_list_classes[physics_list_name]()
        else:
            g4_factory = g4.G4PhysListFactory()
            if g4_factory.IsReferencePhysList(physics_list_name):
                return g4_factory.GetReferencePhysList(physics_list_name)
            else:
                s = (
                    f"Cannot find the physic list: {physics_list_name}\n"
                    f"{self.dump_info_physics_lists()}"
                    f"Default is {self.physics_manager.default_physic_list}\n"
                    f"Help : https://geant4-userdoc.web.cern.ch/UsersGuides/PhysicsListGuide/html/physicslistguide.html"
                )
                fatal(s)

    def dump_info_physics_lists(self):
        g4_factory = g4.G4PhysListFactory()
        s = (
            "\n**** INFO about GATE physics lists ****\n"
            f"* Known Geant4 lists are: {g4_factory.AvailablePhysLists()}\n"
            f"* With EM options: {g4_factory.AvailablePhysListsEM()[1:]}\n"
            f"* Or the following simple physics lists with a single PhysicsConstructor: \n"
            f"* {self.available_g4_physics_constructors} \n"
            "**** ----------------------------- ****\n\n"
        )
        return s


def retrieve_g4_physics_constructor_class(g4_physics_constructor_class_name):
    """
    Dynamically create a class with the given PhysicList
    Only possible if the class exist in g4
    """
    # Retrieve the G4VPhysicsConstructor class
    try:
        a = getattr(sys.modules["opengate_core"], g4_physics_constructor_class_name)
    except:
        s = f"Cannot find the class {g4_physics_constructor_class_name} in opengate_core"
        fatal(s)
    # sanity check:
    assert g4_physics_constructor_class_name == a.__name__
    return a


def create_modular_physics_list_class(g4_physics_constructor_class_name):
    """
    Create a class (not on object!) which:
    - inherit from g4.G4VModularPhysicsList
    - register a single G4 PhysicsConstructor (inherited from G4VPhysicsConstructor)
    - has the same name as this PhysicsConstructor
    """
    g4_physics_constructor_class = retrieve_g4_physics_constructor_class(
        g4_physics_constructor_class_name
    )
    # create the class with __init__ method
    cls = type(
        g4_physics_constructor_class_name,
        (g4.G4VModularPhysicsList,),
        {
            "g4_physics_constructor_class": g4_physics_constructor_class,
            "__init__": init_method,
        },
    )
    return cls


def init_method(self):
    """
    Init method of the dynamically created physics list class.
    - call the init method of the super class (G4VModularPhysicsList)
    - Create and register the physics constructor (G4VPhysicsConstructor)
    """
    g4.G4VModularPhysicsList.__init__(self)
    self.g4_physics_constructor = self.g4_physics_constructor_class(
        1
    )  # argument 1 means verbose=1
    self.RegisterPhysics(self.g4_physics_constructor)
