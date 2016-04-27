from __future__ import division

import numpy as np

from scipy.optimize import brentq
from scipy.constants import c
from scipy.integrate import dblquad

from . import Printing

from functools import partial, wraps
import operator

def attach_clean_buckets(rf_parameter_changing_method, rfsystems_instance):
    '''Wrap an rf_parameter_changing_method (that changes relevant RF
    parameters, i.e. Kick attributes). Needs to be an instance method,
    presumably an RFSystems instance (hence the self argument in
    cleaned_rf_parameter_changing_method).
    In detail, attaches a call to the rfsystems_instance.clean_buckets
    method after calling the wrapped function.
    '''
    @wraps(rf_parameter_changing_method)
    def cleaned_rf_parameter_changing_method(self, *args, **kwargs):
        res = rf_parameter_changing_method(*args, **kwargs)
        rfsystems_instance.clean_buckets()
        return res
    return cleaned_rf_parameter_changing_method

class RFBucket(Printing):
    """Holds a blueprint of the current RF bucket configuration.
    Should be requested via RFSystems.get_bucket(gamma).

    Contains all information and all physical parameters of the
    current longitudinal RF configuration for a (real, not macro-)
    particle.

    Use for plotting or obtaining the Hamiltonian etc.

    Warning: zmin and zmax do not (yet) account for phi_offset of
    Kick objects, i.e. the left and right side of the bucket are not
    accordingly moved w.r.t. the harmonic phase offset.
    """
    def __init__(self, circumference, gamma, mass,
                 charge, alpha_array, p_increment,
                 harmonic_list, voltage_list, phi_offset_list,
                 z_offset=None, *args, **kwargs):
        '''Implements only the leading order momentum compaction factor.

        Arguments:
        - mass is the mass of the particle type in the beam
        - charge is the charge of the particle type in the beam
        - z_offset determines where to start the root finding
        (of the electric force field to calibrate the separatrix
        Hamiltonian value to zero). z_offset is per default given by
        the phase shift of the fundamental RF element.
        '''

        self.circumference = circumference
        self.mass = mass
        self.charge = charge

        self._gamma = gamma
        self._beta = np.sqrt(1 - gamma**-2)
        self._p0 = np.sqrt(gamma**2 - 1) * mass * c

        self.alpha0 = alpha_array[0]
        self.p_increment = p_increment

        self.h = harmonic_list
        self.V = voltage_list
        self.dphi = phi_offset_list

        """Additional electric force fields to be added on top of the
        RF electric force field.
        """
        self._add_forces = []
        """Additional electric potential energies to be added on top
        of the RF electric potential energy.
        """
        self._add_potentials = []

        if z_offset is None:
            i_fund = np.argmin(self.h) # index of fundamental RF element
            phi_offset = self.dphi[i_fund]
            # account for bucket size between -pi and pi.
            # below transition there should be no relocation of the
            # bucket interval by an offset of pi! we only need relative
            # offset w.r.t. normal phi setting at given gamma (0 resp. pi)
            if self.eta0 < 0:
                phi_offset -= np.pi
            z_offset = -phi_offset * self.R / self.h[i_fund]
        self.z_offset = z_offset

        zmax = self.circumference / (2*np.amin(harmonic_list))

        """Minimum and maximum z values on either side of the
        stationary bucket to cover the maximally possible bucket area,
        defined by the fundamental harmonic.
        (Does not necessarily coincide with the unstable fix points
        of the real bucket including self.p_increment .)
        """
        self.interval = (z_offset - 1.01*zmax, z_offset + 1.01*zmax)

    @property
    def gamma(self):
        return self._gamma

    @property
    def beta(self):
        return self._beta

    @property
    def p0(self):
        return self._p0

    @property
    def deltaE(self):
        return self.p_increment * self.beta * c

    @property
    def z_ufp(self):
        '''Return the (left-most) unstable fix point on the z axis
        within self.interval .
        '''
        try:
            return self._z_ufp
        except AttributeError:
            self._z_sfp, self._z_ufp = self._get_zsfp_and_zufp()
            return self._z_ufp

    @property
    def z_sfp(self):
        '''Return the (left-most) stable fix point on the z axis.
        within self.interval .
        '''
        try:
            return self._z_sfp
        except AttributeError:
            self._z_sfp, self._z_ufp = self._get_zsfp_and_zufp()
            return self._z_sfp

    @property
    def z_ufp_separatrix(self):
        '''Return the (left-most) unstable fix point at the separatrix
        of the bucket.
        (i.e. a bucket boundary defining unstable fix point)
        '''
        if self.eta0 * self.p_increment > 0:
            # separatrix ufp right of sfp
            return self.z_ufp[-1]
        else:
            # separatrix ufp left of sfp
            return self.z_ufp[0]

    @property
    def z_sfp_extr(self):
        '''Return the (left-most) absolute extremal stable fix point
        within the bucket.
        '''
        sfp_extr_index = np.argmax(self.hamiltonian(self.z_sfp, 0,
                                                    make_convex=True))
        return self.z_sfp[sfp_extr_index]

    @property
    def zleft(self):
        '''Return the left bucket boundary within self.interval .'''
        try:
            return self._zleft
        except AttributeError:
            self._zleft, self._zright, _ = self._get_bucket_boundaries()
            return self._zleft

    @property
    def zright(self):
        '''Return the right bucket boundary within self.interval .'''
        try:
            return self._zright
        except AttributeError:
            self._zleft, self._zright, _ = self._get_bucket_boundaries()
            return self._zright

    @property
    def R(self):
        return self.circumference/(2*np.pi)

    # should make use of eta functionality of LongitudinalMap at some point
    @property
    def eta0(self):
        return self.alpha0 - self.gamma**-2

    @property
    def beta_z(self):
        return np.abs(self.eta0 * self.R / self.Qs)

    @property
    def Qs(self):
        """Synchrotron tunes for small amplitudes i.e., in the center of the bucket.

        """
        hV = sum([h * self.V[i] for i, h in enumerate(self.h)])
        return np.sqrt(np.abs(self.charge)*np.abs(self.eta0)*hV /
                       (2*np.pi*self.p0*self.beta*c))

    def add_fields(self, add_forces, add_potentials):
        '''Include additional (e.g. non-RF) effects to this RFBucket.
        Use this interface for adding space charge influence etc.
        to the bucket parameters and shape.

        Arguments:
        - add_forces are additional electric force fields to be added
        on top of the RF electric force field.
        add_forces is expected to be an iterable of functions of z,
        in units of Coul*Volt/metre.
        - add_potentials are additional electric potential energies
        to be added on top of the RF electric potential energy.
        add_potentials is expected to be an iterable of functions of z,
        in units of Coul*Volt.

        Bucket shape parameters z_ufp, z_sfp, zleft and zright are
        recalculated.
        '''
        self._add_forces += add_forces
        self._add_potentials += add_potentials
        try:
            delattr(self, "_z_ufp")
            delattr(self, "_z_sfp")
        except AttributeError:
            pass
        try:
            delattr(self, "_zleft")
            delattr(self, "_zright")
        except AttributeError:
            pass

    # FORCE FIELDS AND POTENTIALS OF MULTI-HARMONIC ACCELERATING BUCKET
    # =================================================================
    def make_singleharmonic_force(self, V, h, dphi):
        '''Return the electric force field of a single harmonic
        RF element as a function of z in units of Coul*Volt/metre.
        '''
        def force(z):
            return (np.abs(self.charge) * V / self.circumference
                    * np.sin(h * z / self.R + dphi))
        return force

    def make_total_force(self, ignore_add_forces=False):
        '''Return the stationary total electric force field of
        superimposed RF elements (multi-harmonics) as a function of z.
        Parameters are taken from RF parameters of this
        RFBucket instance.

        Adds the additional electric force fields (provided via
        self.add_nonRF_influences) on top.
        Uses units of Coul*Volt/metre.
        '''
        def total_force(z):
            '''Return stationary total electric force field of
            superimposed RF elements (multi-harmonics) and additional
            force fields as a function of z in units of Coul*Volt/metre.
            '''
            harmonics = (self.make_singleharmonic_force(V, h, dphi)(z)
                         for V, h, dphi in zip(self.V, self.h, self.dphi))
            return (sum(harmonics) + sum(f(z) for f in self._add_forces
                                         if not ignore_add_forces))
        return total_force

    def acc_force(self, z, ignore_add_forces=False):
        '''Return the total electric force field including
        - the acceleration offset and
        - the additional electric force fields (provided via
        self.add_nonRF_influences),
        evaluated at position z in units of Coul*Volt/metre.
        '''
        total_force = self.make_total_force(
            ignore_add_forces=ignore_add_forces)
        return total_force(z) - self.deltaE / self.circumference

    def make_singleharmonic_potential(self, V, h, dphi):
        '''Return the electric potential energy of a single harmonic
        RF element as a function of z in units of Coul*Volt.
        '''
        def potential(z):
            return (np.abs(self.charge) * V / (2 * np.pi * h)
                    * np.cos(h * z / self.R + dphi))
        return potential

    def make_total_potential(self, ignore_add_potentials=False):
        '''Return the stationary total electric potential energy of
        superimposed RF elements (multi-harmonics) as a function of z.
        Parameters are taken from RF parameters of this
        RFBucket instance.

        Adds the additional electric potential energies
        (provided via self.add_nonRF_influences) on top.
        Uses units of Coul*Volt.
        '''
        def total_potential(z):
            '''Return stationary total electric potential energy of
            superimposed RF elements (multi-harmonics) and additional
            electric potentials as a function of z
            in units of Coul*Volt.
            '''
            harmonics = (self.make_singleharmonic_potential(V, h, dphi)(z)
                         for V, h, dphi in zip(self.V, self.h, self.dphi))
            return (sum(harmonics) + sum(pot(z) for pot in self._add_potentials
                                         if not ignore_add_potentials))
        return total_potential

    def acc_potential(self, z, ignore_add_potentials=False,
                      make_convex=False):
        '''Return the total electric potential energy including
        - the linear acceleration slope and
        - the additional electric potential energies (provided via
        self.add_nonRF_influences),
        evaluated at position z in units of Coul*Volt.

        Note:
        Adds a potential energy offset: this relocates the extremum
        (defining the unstable fix point UFP of the bucket)
        to obtain zero potential energy at the UFP.
        Thus the Hamiltonian value of the separatrix is calibrated
        to zero.

        Arguments:
        - make_convex: multiplies by sign(eta) for plotting etc.
        To see a literal 'bucket structure' in the sense of a
        local minimum in the Hamiltonian topology, set make_convex=True
        in order to return sign(eta)*hamiltonian(z, dp).
        '''
        pot_tot = self.make_total_potential(
            ignore_add_potentials=ignore_add_potentials)
        z_boundary = self.z_ufp_separatrix
        v_acc = (pot_tot(z) - pot_tot(z_boundary)
                 + self.deltaE / self.circumference * (z - z_boundary))
        if make_convex:
            v_acc *= np.sign(self.eta0)
        return v_acc

    # ROOT AND BOUNDARY FINDING ROUTINES
    # ==================================
    def zero_crossings(self, f, x=None, subintervals=1000):
        '''Determine roots of f along x.
        If x is not explicitely given, take stationary bucket interval.
        '''
        if x is None:
            x = np.linspace(*self.interval, num=subintervals)

        y = f(x)
        zix = np.where(np.abs(np.diff(np.sign(y))) == 2)[0]

        x0 = np.array([brentq(f, x[i], x[i+1]) for i in zix])
        # y0 = np.array(f(i) for i in x0)

        return x0 #, y0

    def _get_bucket_boundaries(self):
        '''Return the bucket boundaries as well as the whole list
        of acceleration voltage roots, (zleft, zright, z_roots).
        '''
        z0 = np.atleast_1d(self.zero_crossings(self.acc_potential))
        z0 = np.append(z0, self.z_ufp)
        return np.min(z0), np.max(z0), z0

    def _get_zsfp_and_zufp(self):
        '''Return (z_sfp, z_ufp),
        where z_sfp is the synchronous z on stable fix point,
        and z_ufp is the z of the (first) unstable fix point.

        Works for dominant harmonic situations which look like
        a single harmonic (which may be slightly perturbed), i.e.
        only one stable fix point and at most
        2 unstable fix points (stationary case).
        '''
        z0 = np.atleast_1d(self.zero_crossings(self.acc_force))

        if not z0.size:
            # no bucket (i.e. bucket area 'negative')
            raise ValueError('With an electric force field this weak ' +
                             'there is no bucket for such strong ' +
                             'momentum increase -- ' +
                             'why do you ask me for bucket boundaries ' +
                             'in this hyperbolic phase space structure?!')

        z0odd = z0[::2]
        z0even = z0[1::2]

        if len(z0) == 1: # exactly zero bucket area
            return z0, z0

        if self.eta0 * self.p_increment > 0:
            # separatrix ufp right of sfp
            z_sfp, z_ufp = z0odd, z0even
        else:
            # separatrix ufp left of sfp
            z_sfp, z_ufp = z0even, z0odd

        return z_sfp, z_ufp

    # HAMILTONIANS, SEPARATRICES AND RELATED FUNCTIONS
    # ================================================
    def hamiltonian(self, z, dp, make_convex=False):
        '''Return the Hamiltonian at position z and dp in units of
        Coul*Volt/p0.

        Arguments:
        - make_convex: multiplies by sign(eta) for plotting etc.
        To see a literal 'bucket structure' in the sense of a
        local minimum in the Hamiltonian topology, set make_convex=True
        in order to return sign(eta)*hamiltonian(z, dp).
        '''
        h = (-0.5 * self.eta0 * self.beta * c * dp**2 +
            self.acc_potential(z) / self.p0)
        if make_convex:
            h *= np.sign(self.eta0)
        return h

    def H0_from_sigma(self, z0, make_convex=True):
        """Pure estimate value of H_0 starting from a bi-Gaussian bunch
        in a linear "RF bucket". Intended for use by iterative matching
        algorithms in the generators module.
        """
        # to be replaced with something more flexible (add_forces etc.)
        h0 = self.beta*c * (z0/self.beta_z)**2
        if make_convex:
            h0 *= np.abs(self.eta0)
        return h0

    def H0_from_epsn(self, epsn, make_convex=True):
        """Pure estimate value of H_0 starting from a bi-Gaussian bunch
        in a linear "RF bucket". Intended for use by iterative matching
        algorithms in the generators module.
        """
        # to be replaced with something more flexible (add_forces etc.)
        z0 = np.sqrt(epsn/(4.*np.pi) * self.beta_z * np.abs(self.charge)/self.p0)
        h0 = self.beta*c * (z0/self.beta_z)**2
        if make_convex:
            h0 *= np.abs(self.eta0)
        return h0

    def equihamiltonian(self, zcut):
        '''Return a function dp_at that encodes the equi-Hamiltonian
        contour line that cuts the z axis at (zcut, 0).
        In more detail, dp_at(z) returns the (positive) dp value at
        its given z argument such that
        self.hamiltonian(z, dp_at(z)) == self.hamiltonian(zcut, 0) .
        '''
        def dp_at(z):
            hcut = self.hamiltonian(zcut, 0)
            r = np.abs(2./(self.eta0*self.beta*c) *
                 (-hcut - self.acc_potential(z)/self.p0))
            return np.sqrt(r.clip(min=0))
        return dp_at

    def separatrix(self, z):
        '''Return the positive dp value corresponding to the separatrix
        Hamiltonian contour line at the given z.
        '''
        dp_separatrix_at = self.equihamiltonian(self.z_ufp_separatrix)
        return dp_separatrix_at(z)

    def h_sfp(self, make_convex=False):
        '''Return the extremal Hamiltonian value at the corresponding
        stable fix point (self.z_sfp_extr, 0) of the bucket.
        '''
        return self.hamiltonian(self.z_sfp_extr, 0, make_convex)

    def dp_max(self, zcut):
        '''Return the maximal dp value along the equihamiltonian which
        is located at (one of the) self.z_sfp .
        '''
        dp_at = self.equihamiltonian(zcut)
        return np.amax(dp_at(self.z_sfp))

    def is_in_separatrix(self, z, dp, margin=0):
        """Return boolean whether the coordinate (z, dp) is located
        strictly inside the separatrix of this bucket
        (i.e. excluding neighbouring buckets).

        If margin is different from 0, use the equihamiltonian
        defined by margin*self.h_sfp instead of the separatrix.
        (Use margin as a weighting factor in units of the Hamiltonian
        value at the stable fix point to move from the separatrix
        toward the extremal Hamiltonian value at self.z_sfp .)
        """
        within_interval = np.logical_and(self.zleft < z, z < self.zright)
        within_separatrix = (self.hamiltonian(z, dp, make_convex=True)
                             > margin * self.h_sfp(make_convex=True))
        return np.logical_and(within_interval, within_separatrix)

    def make_is_accepted(self, margin=0):
        """Return the function is_accepted(z, dp) definining the
        equihamiltonian with a value of margin*self.h_sfp .
        For margin 0, the returned is_accepted(z, dp) function is
        identical to self.is_in_separatrix(z, dp).
        """
        return partial(self.is_in_separatrix, margin=margin)

    def bucket_area(self):
        Q, error = dblquad(lambda y, x: 1, self.zleft, self.zright, lambda x: 0,
                           self.separatrix)

        return Q * 2*self.p0/np.abs(self.charge)
