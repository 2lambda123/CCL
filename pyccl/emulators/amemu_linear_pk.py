__all__ = ("amemuLinear",)

import numpy as np

from .. import Pk2D
from . import EmulatorPk
from amemu.prediction import EmuPredict


class amemuLinear(EmulatorPk):
    def __init__(self, download=True):
        """
        Calculates the linear matter power spectrum based on the following
        setup:
        - redshift: [0.0, 5.0]
        - wavenumber in 1/Mpc: [1e-4, 50]
        - Omega_cdm: [0.07, 0.50]
        - Omega_b: [0.028, 0.027]
        - h: [0.64, 0.82]

        for any n_s and sigma_8.

        Args:
            download: download the latest suite of pre-trained models.
        """
        # the emulator is trained on 500 training points only.
        self.emulator = EmuPredict(nlhs=500, download=download)

    def __str__(self):
        """
        Main description of the bounds for the wavenumber and redshift.

        Returns:
            str: prints the bounds for the emulator.
        """
        return (
            "amemu linear matter power spectrum:"
            + f"k_min={self.emulator.config.K_MIN},"
            + f"k_max={self.emulator.config.K_MAX},"
            + f"z_min={self.emulator.config.Z_MIN},"
            + f"z_max={self.emulator.config.Z_MAX}"
        )

    def _get_pk_at_a(self, cosmo: dict, a: np.ndarray):
        """
        Calculates the linear matter power spectrum given a dictionary for
        cosmology and the scale factor. An example of
        input comological parameter is:

        cosmo = {'Omega_cdm': 0.25, 'Omega_b': 0.04, 'h': 0.70, 'n_s': 1.0,
        'sigma8': 0.75}

        Args:
            cosmo : the set of cosmological parameters.
            a: the scale factor, a.

        Returns:
            the wavenumbers and the linear matter spectrum at the pre-defined
            values of k.
        """
        a = np.array(a)
        redshift = (np.ones(1) - a) / a
        record_mean = []
        for z_i in redshift:
            pk_quant = self.emulator.calculate_pklin(z_i, cosmo,
                                                     return_var=False)
            record_mean.append(pk_quant)
        record_mean = np.asarray(record_mean)
        return self.emulator.wavenumber.numpy(), record_mean

    def _get_pk2d(self, cosmo) -> Pk2D:
        """
        Calculates the 2D linear matter spectrum, as a function of wavenumber
        (1/Mpc) and scale factor. The scale factors are for redshift between
        0 and 5, inclusive.

        Args:
            cosmo : a dictionary for the cosmological parameter.

        Returns:
            Pk2D object implemented in CCL.
        """
        # we are using 21 redshifts between the minimum and maximum redshifts.
        redshifts = np.linspace(self.emulator.config.Z_MIN + 1e-10,
                                self.emulator.config.Z_MAX - 1e-10, 21)
        scalefactor = 1.0 / (1.0 + redshifts)
        wavenumbers, linearpk = self._get_pk_at_a(cosmo, scalefactor)
        return Pk2D(
            a_arr=scalefactor[::-1],
            lk_arr=np.log(wavenumbers),
            pk_arr=np.log(linearpk),
            is_logp=True,
            extrap_order_lok=1,
            extrap_order_hik=2,
        )
