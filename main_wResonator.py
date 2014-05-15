from __future__ import division
import cProfile, itertools, time, timeit
import numpy as np


from beams.bunch import *
from beams import slices
from monitors.monitors import *
from aperture.aperture import *
from impedances.wake_fields  import *
from trackers.transverse_tracker import *
from trackers.longitudinal_tracker import *
from plots import *
from scipy.constants import c, e, m_p
from scipy.constants import physical_constants


# simulation setup
charge = e
mass = m_p
n_particles = 1.15e11
beta_x = 54.6408 # [m]
beta_y = 54.5054 # [m]
bunch_length = 0.192368 # [m]
momentum_spread = 0.00166945
epsn_x = 2.0 # [um]
epsn_y = 2.0 # [um]
gamma_t = 1/np.sqrt(0.0031)
C = 6911. # [m]
energy = 26e9 # total [eV]
n_turns = 1024
nsigmaz = 3
Qx = 20.15
Qy = 20.15
Qs = 0.017
Qp_x = 0
Qp_y = 0
n_macroparticles = 10000
n_particles = 1.15e11
n_slices = 100
R_frequency = 1.0e9 # [Hz]
Q = 1.
R_shunt = 15e6 # [Ohm/m]
initial_kick_x = 0.1*np.sqrt(beta_x * epsn_x*1.e-6 / (energy / 0.938e9))
initial_kick_y = 1*np.sqrt(beta_y * epsn_y*1.e-6 / (energy / 0.938e9))
RF_voltage = 4e6 # [V]
harmonic_number = 4620
Yokoya_X1 = np.pi**2/24
Yokoya_X2 = 0. #-np.pi**2/24
Yokoya_Y1 = 0. #np.pi**2/12
Yokoya_Y2 = 0. #np.pi**2/24


# Betatron
n_segments = 1
s = np.arange(1, n_segments + 1) * C / n_segments
linear_map = TransverseTracker.from_copy(s,
                               np.zeros(n_segments),
                               np.ones(n_segments) * beta_x,
                               np.zeros(n_segments),
                               np.zeros(n_segments),
                               np.ones(n_segments) * beta_y,
                               np.zeros(n_segments),
                               Qx, Qp_x, 0, Qy, Qp_y, 0)


# Synchrotron motion
cavity = CSCavity(C, gamma_t, Qs)
# cavity = RFCavity(C, C, gamma_t, harmonic_number, RF_voltage, 0, integrator='rk4')


# Bunch
bunch = bunch_matched_and_sliced(n_macroparticles, n_particles, charge, energy, mass,
                                 epsn_x, epsn_y, linear_map[0], bunch_length, 0.35, matching=None,
                                 n_slices=n_slices, nsigmaz=nsigmaz, slicemode='cspace')
# bunch =  bunch_unmatched_inbucket_sliced(n_macroparticles, n_particles, charge, energy, mass,
#                                          epsn_x, epsn_y, linear_map[0], bunch_length, momentum_spread, bucket=cavity,
#                                          n_slices=n_slices, nsigmaz=nsigmaz, slicemode='cspace')

# initial transverse kicks
# bunch.x += initial_kick_x
bunch.y += 0.01

# # save initial distribution
# ParticleMonitor('initial_distribution').dump(bunch)

# distribution from file
# bunch = bunch_from_file('initial_distribution', 0, n_particles, charge, energy, mass, n_slices, nsigmaz, slicemode='cspace')


# Monitors
bunchmonitor = SliceMonitor('bunch', n_turns)
particlemonitor = ParticleMonitor('particles')


# Resonator wakefields
# wakes = BB_Resonator_transverse(R_shunt=R_shunt, frequency=R_frequency, Q=Q, Yokoya_X1=Yokoya_X1, Yokoya_Y1=Yokoya_Y1, Yokoya_X2=Yokoya_X2, Yokoya_Y2=Yokoya_Y2)
wakes = BB_Resonator_Circular(R_shunt=R_shunt, frequency=R_frequency, Q=Q)


# accelerator map
map_ = linear_map + [wakes] + [cavity]


plt.ion()
for i in range(n_turns):
    bunch.compute_statistics()
    t0 = time.clock() 
    for m in map_:
        m.track(bunch)

    # plt.cla()
    # plt.scatter(bunch.dz, bunch.dp, marker='.')
    # # plt.xlim(-1e-2, 1e-2)
    # # # plt.ylim(-1e-2, 1e-2)
    # # plt.ylim(-0.5e-3, 0.5e-3)
    # plt.draw()
    bunchmonitor.dump(bunch)
    particlemonitor.dump(bunch)

    print '{0:4d} \t {1:+3e} \t {2:+3e} \t {3:+3e} \t {4:3e} \t {5:3e} \t {6:3f} \t {7:3f} \t {8:3f} \t {9:4e} \t {10:3s}'.format(i, bunch.slices.mean_x[-2], bunch.slices.mean_y[-2], bunch.slices.mean_dz[-2], bunch.slices.epsn_x[-2], bunch.slices.epsn_y[-2], bunch.slices.epsn_z[-2], bunch.slices.sigma_dz[-2], bunch.slices.sigma_dp[-2], bunch.slices.n_macroparticles[-2] / bunch.n_macroparticles * bunch.n_particles, str(time.clock() - t0))


# # dictionary of simulation parameters
# simulation_parameters_dict = {'comment': 'This is a broadband resonator with only a horizontal dipole wake',\
#                               'charge': charge,\
#                               'mass': mass,\
#                               'n_particles': n_particles,\
#                               'beta_x': beta_x,\
#                               'beta_y': beta_y,\
#                               'bunch_length': bunch_length,\
#                               'momentum_spread': momentum_spread,\
#                               'epsn_x': epsn_x,\
#                               'epsn_y': epsn_y,\
#                               'gamma_t': gamma_t,\
#                               'C': C,\
#                               'energy': energy,\
#                               'n_turns': n_turns,\
#                               'nsigmaz': nsigmaz,\
#                               'Qx': Qx,\
#                               'Qy': Qy,\
#                               'Qs': Qs,\
#                               'Qp_x': Qp_x,\
#                               'Qp_y': Qp_y,\
#                               'n_macroparticles': bunch.n_macroparticles,\
#                               'n_slices': n_slices,\
#                               'R_frequency': R_frequency,\
#                               'Q': Q,\
#                               'R_shunt': R_shunt,\
#                               'initial_kick_x': initial_kick_x,\
#                               'initial_kick_y': initial_kick_y,\
#                               'RF_voltage': RF_voltage,\
#                               'harmonic_number': harmonic_number,\
#                               'Yokoya_X1': Yokoya_X1,\
#                               'Yokoya_X2': Yokoya_X2,\
#                               'Yokoya_Y1': Yokoya_Y1,\
#                               'Yokoya_Y2': Yokoya_Y2}
