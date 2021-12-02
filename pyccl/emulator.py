"""
This script provides the tools needed for a uniform
framework for CCL to work with emulators.
"""  # noqa
from .pyutils import CCLWarning

# We need to load all subclasses of PowerSpectrumEmulator
# or the `from_name` method will not work!
from .boltzmann import *  # noqa

import warnings
import numpy as np


class Bounds(object):
    """ Operations related to the consistency of the bounds
    within which the emulator has been trained.

    Parameters:
        bounds (dict):
            Dictionary of parameters and their bounds (``vmin, vmax``).
    """

    def __init__(self, bounds):
        self.bounds = bounds
        for par, vals in self.bounds.items():
            vmin, vmax = vals
            if not vmin <= vmax:
                raise ValueError(f"Malformed bounds for parameter {par}. "
                                 "Should be [min, max].")
            if not isinstance(vals, list):
                self.bounds[par] = list(vals)

    def check_bounds(self, proposal):
        """ Check a dictionary of proposal parameters against the bounds.

        Arguments:
            proposal (dict):
                Dictionary of proposal parameters and values for the emulator.
        """
        for par, val in proposal.items():
            if par not in self.bounds:
                warnings.warn(
                    f"Unknown bounds for parameter {par}.", CCLWarning)
                continue
            vmin, vmax = self.bounds[par]
            if not (vmin <= val <= vmax):
                raise ValueError(f"Parameter {par} out of bounds "
                                 "for current emulator configuration.")


class Emulator(object):
    """ This class is used to store and access the emulator models.

    In an independent script, each emulator model which is loaded
    into memory is stored here and can be accessed without having
    to reload it. It can hold multiple models simultaneously,
    within a self-contained running script.

    * When subclassing from this class, the method ``_load`` must be
      overridden with a method that imports, loads, and returns the
      emulator.
    * You need a method that translates any CCL parameters to a set
      of parameters the emulator can understand.
    * You may also wish to validate that the parameters are within
      the allowed range of the emulator. Class ``pyccl.emulator.Bounds``
      is built with that in mind.
    * If the emulator contains multiple models (dependent on the
      emulator's configuration) then it may be useful to add an
      attribute ``_config_emu_kwargs`` in order for the ``Emulator``
      base to store the current configuration and decide whether
      the model needs to be reloaded.
    """
    name = 'emulator_base'
    emulators = {}

    def __init__(self):
        self._param_emu_kwargs = {}
        if not hasattr(self, "_config_emu_kwargs"):
            self._config_emu_kwargs = {}

        if not self._has_entry:
            self._set_entry()

        if not self._has_model:
            self._set_model()

        if self._reload or not self._has_config:
            self._set_config()

    def _load(self):
        # Load and return the emulator (override this)
        raise NotImplementedError(
            "You have to override the base class `_load` method "
            "in your emulator implementation.")

    @property
    def _has_entry(self):
        # Is there an entry for this emulator?
        return self.name in self.emulators

    @property
    def _has_model(self):
        # Does the required model exist?
        self._reload = self._get_config() != self._config_emu_kwargs
        if self._reload:
            return False
        else:
            entry = self._get_entry()
            return entry["model"] is not None

    @property
    def _has_config(self):
        # Is there a stored emulator configuration?
        entry = self._get_entry()
        return entry["config"] is not None

    def _has_bounds(self, key=None):
        # Are there any stored bounds?
        entry = self._get_entry()
        if key is None:
            return entry["bounds"] is not None
        else:
            if entry["bounds"] is None:
                entry["bounds"] = {}
                return False
            elif key in entry["bounds"]:
                return entry["bounds"][key] is not None
            else:
                entry["bounds"][key] = None
                return False

    def _get_entry(self):
        # Return the stored emulator entry
        entry = self.emulators[self.name]
        return entry

    def _get_model(self):
        # Return the stored emulator model
        entry = self._get_entry()
        return entry["model"]

    def _get_config(self):
        # Return the stored emulator configuration
        if self._has_config:
            entry = self._get_entry()
            return entry["config"]
        else:
            # first go used in `_reload`
            return None

    def _get_bounds(self, key=None):
        # Return the stored emulator bounds
        entry = self._get_entry()
        if key is None:
            return entry["bounds"]
        else:
            return entry["bounds"][key]

    def _set_entry(self):
        # Create an entry for this emulator. The entry is
        # a dictionary with the emulator name containing
        # 'model', 'config', and 'bounds'.
        keys = ["model", "config", "bounds"]
        self.emulators[self.name] = dict.fromkeys(keys)

    def _set_model(self):
        # Store the model of this emulator
        emu = self._load()
        entry = self._get_entry()
        entry["model"] = emu

    def _set_config(self):
        # Store the configuration of this emulator
        entry = self._get_entry()
        entry["config"] = self._config_emu_kwargs

    def _set_bounds(self, bounds, key=None):
        # Store the bounds of this emulator
        entry = self._get_entry()
        if key is None:
            entry["bounds"] = bounds
        else:
            if entry["bounds"] is None:
                entry["bounds"] = {key: bounds}
            else:
                entry["bounds"][key] = bounds


class PowerSpectrumEmulator(Emulator):
    """ This class provides the functionality needed to construct
    Pk2D objects from power spectrum emulators. Since most emulators
    are written in Python, this is the Python equivalent of the C-level
    `psp` computation.

    Power spectrum emulators can be set-up to be used with CCL by
    subclassing this class. Each implementation should have at least
    one of the following methods:
        * ``_get_pk_linear(cosmo) -> k, a, pka``
        * ``_get_pk_nonlin(cosmo, baryons=False) -> k, a, pka`` : \
          (If the non-linear method cannot correct for baryons \
           it must raise an exception - ``NotImplementedError``.)
        * ``_get_nonlin_boost(cosmo) -> k, a, pka``
        * ``_get_baryon_boost(cosmo) -> k, a, pka``

    Additionally, it may be useful to implement methods which check
    the consistency of the emulator with the input cosmology.

    Further information for general use of the emulators can be found
    in the docs of ``pyccl.emulators.Emulator``.
    """

    def __init__(self):
        super().__init__()

    @classmethod
    def from_name(cls, name):
        """Return an emulator class from a name string."""
        pspec_emus = {p.name: p for p in cls.__subclasses__()}
        if name in pspec_emus:
            return pspec_emus[name]
        else:
            raise ValueError(f"Power spectrum emulator {name} "
                             "not implemented.")

    @classmethod
    def get_pk_linear(cls, cosmo, name):
        """Linear matter power spectrum, given a model name."""
        from .pk2d import Pk2D

        emu = cls.from_name(name)()
        if not hasattr(emu, "_get_pk_linear"):
            raise NotImplementedError(
                f"Emulator {name} does not have a method "
                "`_get_pk_linear` to compute the linear "
                "matter power spectrum.")

        k, a, pk = emu._get_pk_linear(cosmo)
        pk2d = Pk2D(lk_arr=np.log(k), a_arr=a, pk_arr=np.log(pk))
        return pk2d

    @classmethod
    def get_pk_nonlin(cls, cosmo, name):
        """Non-linear matter power spectrum, given a model name."""
        from .pk2d import Pk2D

        emu = cls.from_name(name)()
        if hasattr(emu, "_get_pk_nonlin"):
            k, a, pk = emu._get_pk_nonlin(cosmo)
            pk2d = Pk2D(lk_arr=np.log(k), a_arr=a, pk_arr=np.log(pk))
        elif hasattr(emu, "_get_nonlin_boost"):
            # query the emulator
            k, a, pk = emu._get_pk_linear(cosmo)
            knl, anl, fknl = emu._get_nonlin_boost(cosmo)
            # construct Pk2D objects
            pk2d_lin = Pk2D(lk_arr=np.log(k), a_arr=a, pk_arr=np.log(pk))
            pk2d_nonlin_boost = Pk2D(lk_arr=np.log(knl), a_arr=anl,
                                     pk_arr=np.log(fknl))
            # multiply
            pk2d = pk2d_nonlin_boost * pk2d_lin
        else:
            raise NotImplementedError(
                f"Emulator {name} does not have any of the methods "
                "`_get_pk_nonlin` or `_get_nonlin_boost` to compute "
                "the non-linear matter power spectrum.")

        return pk2d

    @classmethod
    def apply_model(cls, cosmo, name, pk_linear):
        from .pk2d import Pk2D

        emu = cls.from_name(name)()
        if hasattr(emu, "_get_nonlin_boost"):
            knl, anl, fknl = emu._get_nonlin_boost(cosmo)
            pk2d_nonlin_boost = Pk2D(lk_arr=np.log(knl), a_arr=anl,
                                     pk_arr=np.log(fknl))
            pk2d = pk2d_nonlin_boost * pk_linear
        elif (hasattr(emu, "_get_pk_linear") and
              hasattr(emu, "_get_pk_nonlin")):
            # In this case we calculate the non-linear boost using
            # the ratio of nonlin/linear.
            # query the emulator
            kl, al, pkl = emu._get_pk_linear(cosmo)
            knl, anl, pknl = emu._get_pk_nonlin(cosmo)
            # construct Pk2D objects and take their ratio
            pk2d_lin = Pk2D(lk_arr=np.log(kl), a_arr=al, pk_arr=np.log(pkl))
            pk2d_nl = Pk2D(lk_arr=np.log(knl), a_arr=anl, pk_arr=np.log(pknl))
            pk2d_nonlin_boost = pk2d_nl * pk2d_lin**(-1)
            # multiply
            pk2d = pk2d_nonlin_boost * pk_linear
        else:
            raise NotImplementedError(
                f"Emulator {name} does not have any of the methods "
                "`_get_pk_linear`, `_get_pk_nonlin`, or `get_nonlin_boost` "
                "to apply the matter power spectrum correction.")

        return pk2d

    @classmethod
    def include_baryons(cls, cosmo, name, pk_in):
        from .pk2d import Pk2D

        emu = cls.from_name(name)()
        if hasattr(emu, "_get_baryon_boost"):
            k, a, pk = emu._get_baryon_boost(cosmo)
            pk2d_baryon = Pk2D(lk_arr=np.log(k), a_arr=a, pk_arr=np.log(pk))
            pk2d = pk2d_baryon * pk_in
        else:
            # Here, we can't safely infer the baryon correction from
            # a ratio of power spectra because the baryon correction
            # could have been applied in any power spectrum.
            raise NotImplementedError(
                f"Emulator {name} does not have a method "
                "`_get_baryon_boost` to compute the baryon correction.")

        return pk2d