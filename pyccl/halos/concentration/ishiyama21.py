from ... import ccllib as lib
from ...base import warn_api
from ...pyutils import check
from ..halo_model_base import Concentration
import numpy as np
from scipy.optimize import brentq, root_scalar


__all__ = ("ConcentrationIshiyama21",)


class ConcentrationIshiyama21(Concentration):
    r"""Concentration-mass relation by Ishiyama et al. (2021)
    :arXiv:2007.14720. Only valid for S.O. masses with
    :math:`\Delta = \Delta_{\rm vir}`, :math:`\Delta = 200c`,
    or :math:`\Delta = 500c`.

    The concentration takes the form

    .. math::

        c(\nu, n_{\rm eff}, \alpha_{\rm eff})
        = C(\alpha_{\rm eff}) \times \tilde{G} \left[
            \frac{A(n{\rm eff})}{\nu}
            \left( 1 + \frac{\nu^2}{B(n_{\rm eff})} \right) \right],

    where :math:`\tilde{G}` is the inverse function of

    .. math::

        G(x) = \frac{x}{\left[ f(x) \right]^{(5 + n_{\rm eff})/6}}.

    In the above, :math:`f(x) = \ln(1+x) - x/(1+x)` is the mass function of
    the NFW profile, :math:`\nu=\frac{\delta_c}{\sigma_\rm{M}}` is the height
    of the density peak. Variables :math:`n_{\rm eff}` and
    :math:`\alpha_{\rm eff}` are defined as

    .. math::

        n_{\rm eff}(M) = -2 \frac{\rm{d} \ln \sigma(R)}{\rm{d} \ln R} - 3,

    where :math:`R = \kappa R_{\rm L}` and

    .. math::

        \alpha_{\rm eff}(z)
        = -\frac{\mathrm{d} \ln D(z)}{\mathrm{d} \ln (1 + z)}.

    Terms :math:`(A,B,C)` have the following form:

    .. math::

        A(n_{\rm eff}) &= \alpha_0 \, (1 + \alpha_1 (n_{\rm eff} + 3)), \\
        B(n_{\rm eff}) &= \beta_0 \, (1 + \beta_1 (n_{\rm eff} + 3)), \\
        C(\alpha_{\rm eff}) &= 1 - c_\alpha \, (1 - \alpha_{\rm eff}).


    Parameters
    ----------
    mass_def : :class:`~pyccl.halos.massdef.MassDef` or str, optional
        Mass definition for this :math:`c(M)` parametrization.
        The default is :math:`\Delta=500c`.
    relaxed : bool, optional
        If True, use concentration for relaxed halos. Otherwise,
        use concentration for all halos. The default is False.
    Vmax : bool, optional
        If True, use the concentration found with the Vmax numerical
        method. Otherwise, use the concentration found with profile
        fitting. The default is False.
    """
    __repr_attrs__ = ("mass_def", "relaxed", "Vmax",)
    name = 'Ishiyama21'

    @warn_api(pairs=[("mdef", "mass_def")])
    def __init__(self, *, mass_def="500c",
                 relaxed=False, Vmax=False):
        self.relaxed = relaxed
        self.Vmax = Vmax
        super().__init__(mass_def=mass_def)

    def _check_mass_def_strict(self, mass_def):
        is_500Vmax = mass_def.Delta == 500 and self.Vmax
        return mass_def.name not in ["vir", "200c", "500c"] or is_500Vmax

    def _setup(self):
        # key: (Vmax, relaxed, Delta)
        vals = {(True, True, 200): (1.79, 2.15, 2.06, 0.88, 9.24, 0.51),
                (True, False, 200): (1.10, 2.30, 1.64, 1.72, 3.60, 0.32),
                (False, True, 200): (0.60, 2.14, 2.63, 1.69, 6.36, 0.37),
                (False, False, 200): (1.19, 2.54, 1.33, 4.04, 1.21, 0.22),
                (True, True, "vir"): (2.40, 2.27, 1.80, 0.56, 13.24, 0.079),
                (True, False, "vir"): (0.76, 2.34, 1.82, 1.83, 3.52, -0.18),
                (False, True, "vir"): (1.22, 2.52, 1.87, 2.13, 4.19, -0.017),
                (False, False, "vir"): (1.64, 2.67, 1.23, 3.92, 1.30, -0.19),
                (False, True, 500): (0.38, 1.44, 3.41, 2.86, 2.99, 0.42),
                (False, False, 500): (1.83, 1.95, 1.17, 3.57, 0.91, 0.26)}

        key = (self.Vmax, self.relaxed, self.mass_def.Delta)
        self.kappa, self.a0, self.a1, \
            self.b0, self.b1, self.c_alpha = vals[key]

    def _dlsigmaR(self, cosmo, M, a):
        # kappa multiplies radius, so in log, 3*kappa multiplies mass
        logM = 3*np.log10(self.kappa) + np.log10(M)

        status = 0
        dlns_dlogM, status = lib.dlnsigM_dlogM_vec(cosmo.cosmo, a, logM,
                                                   len(logM), status)
        check(status, cosmo=cosmo)
        return -3/np.log(10) * dlns_dlogM

    def _G(self, x, n_eff):
        fx = np.log(1 + x) - x / (1 + x)
        G = x / fx**((5 + n_eff) / 6)
        return G

    def _G_inv(self, arg, n_eff):
        # Numerical calculation of the inverse of `_G`.
        roots = []
        for val, neff in zip(arg, n_eff):
            func = lambda x: self._G(x, neff) - val  # noqa: _G_inv Traceback
            try:
                rt = brentq(func, a=0.05, b=200)
            except ValueError:
                # No root in [0.05, 200] (rare, but it may happen).
                rt = root_scalar(func, x0=1, x1=2).root.item()
            roots.append(rt)
        return np.asarray(roots)

    def _concentration(self, cosmo, M, a):
        nu = 1.686 / cosmo.sigmaM(M, a)
        n_eff = -2 * self._dlsigmaR(cosmo, M, a) - 3
        alpha_eff = cosmo.growth_rate(a)

        A = self.a0 * (1 + self.a1 * (n_eff + 3))
        B = self.b0 * (1 + self.b1 * (n_eff + 3))
        C = 1 - self.c_alpha * (1 - alpha_eff)
        arg = A / nu * (1 + nu**2 / B)
        G = self._G_inv(arg, n_eff)
        return C * G
