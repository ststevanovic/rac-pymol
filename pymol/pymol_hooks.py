"""Glue between PyMOL commands and backend controller."""

from pymol import cmd
from engine.api import get_controller

# this module registers PyMOL hooks and may notify the shared controller when
# objects are loaded.  we import the generic API rather than the concrete
# controller to keep the dependency graph clean.

controller = get_controller()


def install_hooks():
    # example stub
    _orig_load = cmd.load

    def load_and_record(*args, **kwargs):
        result = _orig_load(*args, **kwargs)
        # TODO: notify controller about new object, e.g.
        # controller.record_object(cmd.get_object_list()[-1])
        return result

    cmd.load = load_and_record


cmd.extend("install_hooks", install_hooks)
