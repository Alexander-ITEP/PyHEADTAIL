from pylab import *
import h5py

# Specify number of slices and range of turns (lower and upper limits) to overlay.
N_slices = 100
t_low    = 4000
t_up     = 8190

# Open hdf5 file containing bunch information for every turn and get handle 'hf'.
# BUNCH
hf     = h5py.File('bunch.h5', 'r')
B      = hf['Bunch']
y,  yp = B['mean_y'],  B['mean_yp']
dz, dp = B['mean_dz'], B['mean_dp']
epsn_y = B['epsn_y']                      # emittance (y,yp)

# SLICES
S         = hf['Slices']
S_y, S_yp = S['mean_y'], S['mean_yp']

# Generate plots
fig, ( ax1, ax2, ax3 ) = subplots(3)
fig.subplots_adjust(hspace = 0.4)

r = sqrt(y[:] ** 2 + (54.5054 * yp[:]) ** 2)
ax1.plot(r, c='purple', label='r')
ax1.plot(-r, c='purple')
ax1.plot(y, label='mean_y')
ax1.set_xlabel('#turns')
ax1.set_ylabel('y')

# Plot emittance epsn_y (y,yp) in same plot w. axis on the right.
ax11 = ax1.twinx()
ax11.plot(epsn_y, label='emittance')
ax11.set_ylabel('emittance_y')

ax1.legend(loc='upper right',prop={'size':10})
ax11.legend(loc='lower right',prop={'size':10})


ax2.plot(dz)
ax2.set_xlabel('#turns')
ax2.set_ylabel('dz')
ax2.ticklabel_format(style='sci', axis='y', scilimits=(0,0))

# SLICES PLOT
# Overlay mean_y (S_y) as a function of slice no. (S_n) for a number of turns t in certain range.
S_n = arange(N_slices)
for t in range(t_low, t_up):
    ax3.plot(S_n, S_y[:,t])

ax3.set_xlabel('slice no.')
ax3.set_ylabel('y')
ax3.ticklabel_format(style='sci', axis='y', scilimits=(0,0))

# Put text explaining which turns are overlaid.
strOl = 'overlay of turns ' + str(t_low) + '...' + str(t_up)
text(0.5, 0.8, strOl,
     horizontalalignment ='center',
     verticalalignment   ='center',
     transform = ax3.transAxes)

show()
