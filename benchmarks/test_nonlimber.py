import numpy as np
import pyccl as ccl
import time
import os
import pytest

root = "benchmarks/data/nonlimber/"

def get_cosmological_parameters():
    return {'Omega_m': 0.3156,
            'Omega_b': 0.0492,
            'w0': -1.0,
            'h': 0.6727,
            'A_s': 2.12107E-9,
            'n_s': 0.9645,
            'Neff': 3.046,
            'T_CMB': 2.725}

def get_tracer_parameters():
    # Per-bin galaxy bias
    b_g = np.array([1.376695, 1.451179, 1.528404,
                    1.607983, 1.689579, 1.772899,
                    1.857700, 1.943754, 2.030887,
                    2.118943])
    return {'b_g': b_g}

def get_ells():
    return np.unique(np.geomspace(2, 2000, 128).astype(int)).astype(float)

def get_nmodes(fsky=0.4):
    """ Returns the number of modes in each ell bin"""
    ls = get_ells()
    nmodes = list(ls[1:]**2-ls[:-1]**2)
    lp = ls[-1]**2/ls[-2]
    nmodes.append(lp**2-ls[-1]**2)
    return np.array(nmodes)*0.5*fsky

def get_tracer_kernels():
    filename = root+'/kernels_fullwidth.npz'
    d = np.load(filename)
    kernels_cl = d['kernels_cl']
    kernels_sh = d['kernels_sh']
    return {'z_cl': d['z_cl'],
            'chi_cl': d['chi_cl'],
            'kernels_cl': kernels_cl,
            'z_sh': d['z_sh'],
            'chi_sh': d['chi_sh'],
            'kernels_sh': kernels_sh}

def read_cls():
    d = np.load(root + '/benchmarks_nl_full_clgg.npz')
    ls = d['ls']
    cls_gg = d['cls']
    d = np.load(root + '/benchmarks_nl_full_clgs.npz')
    cls_gs = d['cls']
    d = np.load(root + '/benchmarks_nl_full_clss.npz')
    cls_ss = d['cls']
    return ls, cls_gg, cls_gs, cls_ss

@pytest.fixture(scope='module')
def set_up():
    par = get_cosmological_parameters()
    cosmo = ccl.Cosmology(Omega_c=par['Omega_m']-par['Omega_b'],
                                   Omega_b=par['Omega_b'],
                                   h=par['h'], n_s=par['n_s'],
                                   A_s=par['A_s'], w0=par['w0'])
    tpar = get_tracer_parameters()
    ker = get_tracer_kernels()

    a_g = 1./(1+ker['z_cl'][::-1])    
    t_g = []
    for k in ker['kernels_cl']:
        t = ccl.Tracer()
        barr = np.ones_like(a_g)
        t.add_tracer(cosmo,
                        kernel = (ker['chi_cl'], k),
                        transfer_a=(a_g, barr))
        t_g.append(t)
    t_s = []
    for k in ker['kernels_sh']:
        t = ccl.Tracer()
        t.add_tracer(cosmo,
                        kernel = (ker['chi_sh'], k),
                        der_bessel=-1, der_angles=2)
        t_s.append(t)
    ells = get_ells()
    raw_truth = read_cls()
    indices_gg = []
    indices_gs = []
    indices_ss = []
    rind_gg = {}
    rind_gs = {}
    rind_ss= {}
    Ng, Ns = len(t_g), len(t_s)
    for i1 in range(Ng):
        for i2 in range(i1, Ng):
            rind_gg[(i1, i2)] = len(indices_gg)
            rind_gg[(i2, i1)] = len(indices_gg)
            indices_gg.append((i1, i2))

        for i2 in range(Ns):
            rind_gs[(i1, i2)] = len(indices_gs)
            rind_gs[(i2, i1)] = len(indices_gs)
            indices_gs.append((i1, i2))

    for i1 in range(Ns):
        for i2 in range(i1, Ns):
            rind_ss[(i1, i2)] = len(indices_ss)
            rind_ss[(i2, i1)] = len(indices_ss)
            indices_ss.append((i1, i2))

    # Sanity checks
    assert(np.allclose(raw_truth[0], ells))
    Nell = len(ells)
    tgg,tgs, tss = raw_truth[1:]
    assert(tgg.shape == (len(indices_gg),Nell))
    assert(tgs.shape == (len(indices_gs),Nell))
    assert(tss.shape == (len(indices_ss),Nell))

    ## now generate errors
    err_gg = []
    err_gs = []
    err_ss = []
    nmodes = get_nmodes()
    for i1,i2 in indices_gg:
        err_gg.append(  np.sqrt((tgg[rind_gg[(i1,i1)]]*tgg[rind_gg[(i2,i2)]]+tgg[rind_gg[(i1,i2)]]**2)/nmodes) )
    for i1,i2 in indices_gs:
        err_gs.append(  np.sqrt((tgg[rind_gg[(i1,i1)]]*tss[rind_ss[(i2,i2)]]+tgs[rind_gs[(i1,i2)]]**2)/nmodes) )
    for i1,i2 in indices_ss:
        err_ss.append(  np.sqrt((tss[rind_ss[(i1,i1)]]*tss[rind_ss[(i2,i2)]]+tss[rind_ss[(i1,i2)]]**2)/nmodes) )

    tracers1 = {'gg':t_g,    'gs':t_g,    'ss':t_s}
    tracers2 = {'gg':t_g,    'gs':t_s,    'ss':t_s}
    truth    = {'gg':tgg,    'gs':tgs,    'ss':tss}
    errors   = {'gg':err_gg, 'gs':err_gs, 'ss':err_ss} 
    indices = {'gg':indices_gg, 'gs':indices_gs, 'ss':indices_ss}
    return cosmo, ells, tracers1, tracers2, truth, errors, indices
    
@pytest.mark.parametrize("method",['FKEM'])
@pytest.mark.parametrize("cross_type", ['gg','gs','ss'])
def test_cells(set_up, method, cross_type):
    cosmo, ells, tracers1, tracers2, truth, errors, indices = set_up
    t0 = time.time()
    chi2max = 0
    for pair_index, (i1, i2) in enumerate(indices[cross_type]):
        cls = ccl.angular_cl(cosmo, tracers1[cross_type][i1], tracers2[cross_type][i2], ells, l_limber=-1, non_limber_integration_method=method)
        chi2 = (cls - truth[cross_type][pair_index,:])**2/errors[cross_type][pair_index]**2
        chi2max = max(chi2.max(), chi2max)
        assert(np.all(chi2<0.3))
    t1 = time.time()
    print(f"Time taken for {method} on {cross_type} = {(t1-t0):3.2f}; worst chi2 = {chi2max:5.3f}")
    return cls




class NonLimberTest:

    def __init__(self):
        self.nb_g = 10
        self.nb_s = 5
        self.pk = get_pk()
        self.background = get_background()
        self.cosmo = get_cosmological_parameters()

    def get_pk(self):
        return np.load('benchmarks/data/nonlimber/pk.npz')

    def get_background(self):
        return np.load('benchmarks/data/nonlimber/background.npz')



    def get_tracer_dndzs(self):
        filename = 'benchmarks/data/nonlimber/dNdzs_fullwidth.npz'
        dNdz_file = np.load(filename)
        z_sh = dNdz_file['z_sh']
        dNdz_sh = dNdz_file['dNdz_sh']
        z_cl = dNdz_file['z_cl']
        dNdz_cl = dNdz_file['dNdz_cl']
        return {'z_sh': z_sh, 'dNdz_sh': dNdz_sh,
                'z_cl': z_cl, 'dNdz_cl': dNdz_cl}

    def get_noise_biases(self):
        from scipy.integrate import simps

        # Lens sample: 40 gals/arcmin^2
        ndens_c = 40.
        # Source sample: 27 gals/arcmin^2
        ndens_s = 27.
        # Ellipticity scatter per component
        e_rms = 0.28
        
        ndic = self.get_tracer_dndzs()
        nc_ints = np.array([simps(n, x=ndic['z_cl'])
                            for n in ndic['dNdz_cl'].T])
        ns_ints = np.array([simps(n, x=ndic['z_sh'])
                            for n in ndic['dNdz_sh'].T])
        nc_ints *= ndens_c / np.sum(nc_ints)
        ns_ints *= ndens_s / np.sum(ns_ints)
        tosrad = (180*60/np.pi)**2
        nl_cl = 1./(nc_ints*tosrad)
        nl_sh = e_rms**2/(ns_ints*tosrad)
        return nl_cl, nl_sh




    def get_nmodes_fullsky(self):
        """ Returns the number of modes in each ell bin"""
        ls = self.get_ells()
        nmodes = list(ls[1:]**2-ls[:-1]**2)
        lp = ls[-1]**2/ls[-2]
        nmodes.append(lp**2-ls[-1]**2)
        return np.array(nmodes)*0.5

    def get_num_cls(self):
        ngg = (self.nb_g * (self.nb_g + 1)) // 2
        nss = (self.nb_s * (self.nb_s + 1)) // 2
        ngs = self.nb_g * self.nb_s
        return ngg, ngs, nss


