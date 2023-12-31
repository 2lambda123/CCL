import numpy as np
import pyccl as ccl
import pytest
from timeit import default_timer

ccl.gsl_params.LENSING_KERNEL_SPLINE_INTEGRATION = False
COSMO = ccl.Cosmology(
    Omega_c=0.27, Omega_b=0.045, h=0.67, sigma8=0.8, n_s=0.96,
    transfer_function='bbks', matter_power_spectrum='linear')


@pytest.mark.parametrize('method', ['bessel', 'legendre', 'fftlog'])
def test_correlation_smoke(method):
    z = np.linspace(0., 1., 200)
    n = np.ones(z.shape)
    lens = ccl.WeakLensingTracer(COSMO, dndz=(z, n))

    ell = np.logspace(1, 3, 5)
    cl = ccl.angular_cl(COSMO, lens, lens, ell)

    t_arr = np.logspace(-2., np.log10(5.), 5)
    t_lst = [t for t in t_arr]
    t_scl = 2.
    t_int = 2

    for tval in [t_arr, t_lst, t_scl, t_int]:
        corr = ccl.correlation(
            COSMO, ell=ell, C_ell=cl, theta=tval, type='NN', method=method)
        assert np.all(np.isfinite(corr))
        assert np.shape(corr) == np.shape(tval)


@pytest.mark.parametrize(
    'rval',
    [50,
     50.0,
     np.logspace(1, 2, 5),
     [r for r in np.logspace(1, 2, 5)]])
def test_correlation_3d_smoke(rval):
    a = 0.8
    corr = ccl.correlation_3d(COSMO, a=a, r=rval)
    assert np.all(np.isfinite(corr))
    assert np.shape(corr) == np.shape(rval)


@pytest.mark.parametrize(
    'sval',
    [50,
     50.0,
     np.logspace(1, 2, 5),
     [r for r in np.logspace(1, 2, 5)]])
def test_correlation_3dRSD_smoke(sval):
    a = 0.8
    mu = 0.7
    beta = 0.5
    corr = ccl.correlation_3dRsd(COSMO, a=a, r=sval, mu=mu, beta=beta)
    assert np.all(np.isfinite(corr))
    assert np.shape(corr) == np.shape(sval)


@pytest.mark.parametrize(
    'sval',
    [50,
     50.0,
     np.logspace(1, 2, 5),
     [r for r in np.logspace(1, 2, 5)]])
def test_correlation_3dRSD_avgmu_smoke(sval):
    a = 0.8
    beta = 0.5
    corr = ccl.correlation_3dRsd_avgmu(COSMO, a=a, r=sval, beta=beta)
    assert np.all(np.isfinite(corr))
    assert np.shape(corr) == np.shape(sval)


@pytest.mark.parametrize('l', [0, 2, 4])
@pytest.mark.parametrize(
    'sval',
    [50,
     50.0,
     np.logspace(1, 2, 5),
     [r for r in np.logspace(1, 2, 5)]])
def test_correlation_3dRSD_multipole_smoke(sval, l):
    a = 0.8
    beta = 0.5
    corr = ccl.correlation_multipole(COSMO, a=a, beta=beta,
                                     ell=l, r=sval)
    assert np.all(np.isfinite(corr))
    assert np.shape(corr) == np.shape(sval)


@pytest.mark.parametrize(
    'sval',
    [50,
     50.0,
     np.logspace(1, 2, 5),
     [r for r in np.logspace(1, 2, 5)]])
def test_correlation_pi_sigma_smoke(sval):
    a = 0.8
    beta = 0.5
    pie = 1
    corr = ccl.correlation_pi_sigma(COSMO, a=a, beta=beta, pi=pie, sigma=sval)
    assert np.all(np.isfinite(corr))
    assert np.shape(corr) == np.shape(sval)


def test_correlation_raises():
    with pytest.raises(ValueError):
        ccl.correlation(COSMO, ell=[1], C_ell=[1e-3], theta=[1], method='blah')
    with pytest.raises(ValueError):
        ccl.correlation(COSMO, ell=[1], C_ell=[1e-3], theta=[1], type='blah')


def test_correlation_zero():
    ell = np.arange(2, 100000)
    C_ell = np.zeros(ell.size)
    theta = np.logspace(0, 2, 10000)
    t0 = default_timer()
    corr = ccl.correlation(COSMO, ell=ell, C_ell=C_ell, theta=theta)
    t1 = default_timer()
    # if the short-cut has worked this should take
    # less than 1 second at the absolute outside
    assert t1 - t0 < 1.0
    assert (corr == np.zeros(theta.size)).all()


def test_correlation_zero_ends():
    # This should give an error instead of crashing
    ell = np.arange(2, 1001)
    C_ell = np.zeros(ell.size)
    C_ell[500] = 1.0
    theta = np.logspace(0, 2, 20)
    with pytest.raises(ccl.CCLError):
        ccl.correlation(COSMO, ell=ell, C_ell=C_ell, theta=theta)


ccl.gsl_params.reload()  # reset to the default parameters
