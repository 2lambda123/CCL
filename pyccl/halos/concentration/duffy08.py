from __future__ import annotations

__all__ = ("ConcentrationDuffy08",)

from typing import TYPE_CHECKING, Union

from ... import warn_api
from . import Concentration

if TYPE_CHECKING:
    from .. import MassDef


class ConcentrationDuffy08(Concentration):
    r"""Concentration-mass relation by :footcite:t:`Duffy08`. Only valid for
    S.O. masses with :math:`\Delta_{\rm vir}`, :math:`\Delta_{200{\rm m}}`, or
    :math:`\Delta_{200{\rm c}}`.

    The concentration takes the form

    .. math::

        c(M, z) = A (M / M_{\rm pivot})^B (1 + z)^C,

    where :math:`M_{\rm pivot} = 2 \times 10^{12} h \, \rm{M_\odot}`, and
    :math:`(A,B,C)` are fitting parameters.

    Parameters
    ---------
    mass_def
        Mass definition for this :math:`c(M)` parametrization.

    References
    ----------
    .. footbibliography::
    """
    name = 'Duffy08'

    @warn_api(pairs=[("mdef", "mass_def")])
    def __init__(self, *, mass_def: Union[str, MassDef] = "200c"):
        super().__init__(mass_def=mass_def)

    def _check_mass_def_strict(self, mass_def):
        return mass_def.name not in ["vir", "200m", "200c"]

    def _setup(self):
        vals = {"vir": (7.85, -0.081, -0.71),
                "200m": (10.14, -0.081, -1.01),
                "200c": (5.71, -0.084, -0.47)}

        self.A, self.B, self.C = vals[self.mass_def.name]

    def _concentration(self, cosmo, M, a):
        M_pivot_inv = cosmo["h"] * 5e-13
        return self.A * (M * M_pivot_inv)**self.B * a**(-self.C)
