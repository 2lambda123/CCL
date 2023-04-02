from ...base import warn_api
from ..halo_model_base import MassFunc
import numpy as np
from scipy.interpolate import interp1d


__all__ = ("MassFuncTinker08",)


class MassFuncTinker08(MassFunc):
    r"""Halo mass function by Tinker et al. (2008) :arXiv:0803.2706.
    Valid for any S.O. masses with :math:`\Delta \in (200{\rm m},3200{\rm m})`.

    The mass function takes the form

    .. math::

        1 + 1 = 2

    Parameters
    ----------
    mass_def : :class:`~pyccl.halos.massdef.MassDef` or str, optional
        Mass definition for this :math:`n(M)` parametrization.
        The default is :math:`200{\rm m}`.
    mass_def_strict : bool, optional
        If True, only allow the mass definitions for which this halo bias
        relation was fitted, and raise if another mass definition is passed.
        If False, do not check for model consistency for the mass definition.
        The default is True.

    Raises
    ------
    ValueError
        Interpolation out of bounds. :math:`\Delta_m` for the particular
        combination of mass definition and scale factor is out of bounds with
        the range of the mass function.
    """
    name = 'Tinker08'

    @warn_api
    def __init__(self, *,
                 mass_def="200m",
                 mass_def_strict=True):
        super().__init__(mass_def=mass_def, mass_def_strict=mass_def_strict)

    def _check_mass_def_strict(self, mass_def):
        return mass_def.Delta == "fof"

    def _setup(self):
        delta = np.array(
            [200., 300., 400., 600., 800., 1200., 1600., 2400., 3200.])
        alpha = np.array(
            [0.186, 0.200, 0.212, 0.218, 0.248, 0.255, 0.260, 0.260, 0.260])
        beta = np.array(
            [1.47, 1.52, 1.56, 1.61, 1.87, 2.13, 2.30, 2.53, 2.66])
        gamma = np.array(
            [2.57, 2.25, 2.05, 1.87, 1.59, 1.51, 1.46, 1.44, 1.41])
        phi = np.array(
            [1.19, 1.27, 1.34, 1.45, 1.58, 1.80, 1.97, 2.24, 2.44])
        ldelta = np.log10(delta)
        self.pA0 = interp1d(ldelta, alpha)
        self.pa0 = interp1d(ldelta, beta)
        self.pb0 = interp1d(ldelta, gamma)
        self.pc = interp1d(ldelta, phi)

    def _get_fsigma(self, cosmo, sigM, a, lnM):
        ld = np.log10(self.mass_def._get_Delta_m(cosmo, a))
        pA = self.pA0(ld) * a**0.14
        pa = self.pa0(ld) * a**0.06
        pd = 10.**(-(0.75/(ld - 1.8750612633))**1.2)
        pb = self.pb0(ld) * a**pd
        return pA * ((pb / sigM)**pa + 1) * np.exp(-self.pc(ld)/sigM**2)
