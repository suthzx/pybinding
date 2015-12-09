from collections import namedtuple

import numpy as np
import matplotlib.pyplot as plt

from . import _cpp
from . import pltutils
from .utils import with_defaults
from .support.sparse import SparseMatrix
from .support.pickle import pickleable

__all__ = ['Positions', 'Boundary', 'System', 'plot_hoppings', 'plot_sites']


Positions = namedtuple('Positions', 'x y z')
Positions.__doc__ = """
Named tuple of arrays

Attributes
----------
x, y, z : array_like
    1D arrays of Cartesian coordinates
"""


@pickleable(impl='shift hoppings.')
class Boundary:
    """Periodic boundary"""

    def __init__(self, impl: _cpp.Boundary):
        self.impl = impl

    @property
    def shift(self) -> np.ndarray:
        """Position shift of the periodic boundary condition"""
        return self.impl.shift

    @property
    def hoppings(self) -> SparseMatrix:
        """Sparse matrix of the boundary hoppings"""
        return SparseMatrix(self.impl.hoppings)


@pickleable(impl='positions sublattices hoppings. boundaries[]')
class System:
    """Structural data of the model

    Stores positions, sublattice and hopping IDs for all lattice sites.
    """

    def __init__(self, impl: _cpp.System):
        self.impl = impl

    @property
    def num_sites(self) -> int:
        """Total number of sites in the system"""
        return self.impl.num_sites

    @property
    def x(self) -> np.ndarray:
        """1D array of x coordinates"""
        return self.impl.positions.x

    @property
    def y(self) -> np.ndarray:
        """1D array of y coordinates"""
        return self.impl.positions.y

    @property
    def z(self) -> np.ndarray:
        """1D array of z coordinates"""
        return self.impl.positions.z

    @property
    def xyz(self) -> np.ndarray:
        """Return a new array with shape=(N, 3). Convenient, but slow for big systems."""
        return np.array(self.positions).T

    @property
    def positions(self):
        """Named tuple of x, y, z positions"""
        return Positions(self.x, self.y, self.z)

    @property
    def sublattices(self) -> np.ndarray:
        """1D array of sublattice IDs"""
        return self.impl.sublattices

    @property
    def hoppings(self) -> SparseMatrix:
        """Sparse matrix of hopping IDs"""
        return SparseMatrix(self.impl.hoppings)

    @property
    def boundaries(self):
        """List of :class:`.Boundary`"""
        return [Boundary(b) for b in self.impl.boundaries]

    def find_nearest(self, position, at_sublattice=-1):
        """Find the index of the atom closest to the given position

        Parameters
        ----------
        position : array_like
            Where to look.
        at_sublattice : int
            Look for a specific sublattice site, or -1 if any will do (default).

        Returns
        -------
        int
            Index of the site or -1 if not found.
        """
        if hasattr(self.impl, 'find_nearest'):
            # use cpp implementation
            return self.impl.find_nearest(position, int(at_sublattice))
        else:
            # fallback numpy implementation
            r = np.array(position)
            distance = np.linalg.norm(self.xyz[:, :len(r)] - r, axis=1)
            if at_sublattice < 0:
                return np.argmin(distance)
            else:
                from numpy import ma
                masked_distance = ma.array(distance, mask=self.sublattices != at_sublattice)
                return ma.argmin(masked_distance)

    def plot(self, site_radius=0.025, site_props=None, hopping_width=1.0, hopping_props=None,
             boundary_color='#ff4444', rotate=(0, 1, 2)):
        """Plot the structure of the system: sites and hoppings

        Parameters
        ----------
        site_radius : float
            Radius (in data units) of the circle representing a lattice site.
        site_props : Optional[dict]
            Forwarded to :class:`.CircleCollection`: additional site plotting options.
        hopping_width : float
            Width (in figure units) of the hopping lines.
        hopping_props : Optional[dict]
            Forwarded to :class:`.LineCollection`: additional hopping line options.
        boundary_color : color
            Color of the hopping lines on the boundaries.
        rotate : Tuple[int, int, int]
            Axes mapping:

            * (0, 1, 2) -> (x, y, z) plots xy-plane
            * (1, 2, 0) -> (y, z, x) plots yz-plane
        """
        ax = plt.gca()
        ax.set_aspect('equal')
        ax.set_xlabel("x (nm)")
        ax.set_ylabel("y (nm)")

        # position, sublattice and hopping
        pos = self.x, self.y, self.z
        pos = tuple(pos[i] for i in rotate)
        sub = self.sublattices
        hop = self.hoppings.tocoo()
        site_props = site_props if site_props else {}
        hopping_props = hopping_props if hopping_props else {}

        # plot main part
        plot_hoppings(pos, hop, hopping_width, **hopping_props)
        plot_sites(pos, sub, site_radius, **site_props)

        # plot periodic part
        for boundary in self.boundaries:
            # shift the main sites and hoppings with lowered alpha
            for shift in [boundary.shift, -boundary.shift]:
                plot_sites(pos, sub, site_radius, shift, blend=0.5, **site_props)
                plot_hoppings(pos, hop, hopping_width, shift, blend=0.5, **hopping_props)

            # special color for the boundary hoppings
            if boundary_color:
                kwargs = dict(hopping_props, colors=boundary_color)
            else:
                kwargs = hopping_props
            b_hop = boundary.hoppings.tocoo()
            plot_hoppings(pos, b_hop, hopping_width, boundary.shift, boundary=True, **kwargs)

        pltutils.set_min_axis_length(0.5)
        pltutils.despine(trim=True)
        pltutils.add_margin()


def plot_hoppings(positions, hoppings, width, offset=(0, 0, 0),
                  boundary=False, blend=1.0, **kwargs):
    """Plot hopping lines between sites

    Parameters
    ----------
    positions : Positions
        Site coordinates in the form of a (x, y, z) tuple of arrays.
    hoppings : :class:`~scipy.sparse.coo_matrix`
        Sparse COO matrix with the hopping data, usually `model.system.hoppings.tocoo()`.
    width : float
        Width of the hopping plot lines.
    offset : Tuple[float, float, float]
        Offset all positions by a constant value.
    boundary : bool
        The offset is applied differently at boundaries.
    blend : float
        Blend all colors to white (fake alpha blending): expected values between 0 and 1.
    **kwargs
        Forwarded to matplotlib's :class:`.LineCollection`.

    Returns
    -------
    :class:`.LineCollection`
    """
    if width == 0 or hoppings.data.size == 0:
        return

    kwargs = with_defaults(kwargs, zorder=-1, colors='#666666')

    colors = kwargs.pop('colors')
    if colors == 'default':
        colors = ["#666666", "#1b9e77", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d"]
    unique_hop_ids = np.arange(hoppings.data.max() + 1)
    kwargs['cmap'], kwargs['norm'] = pltutils.direct_cmap_norm(unique_hop_ids, colors, blend)

    ax = plt.gca()
    ndims = 3 if ax.name == '3d' else 2
    offset = np.array(offset[:ndims])
    positions = np.array(positions[:ndims]).T

    if not boundary:
        pos = positions + offset
        lines = ((pos[i], pos[j]) for i, j in zip(hoppings.row, hoppings.col))
    else:
        from itertools import chain
        lines = chain(
            ((positions[i] + offset, positions[j]) for i, j in zip(hoppings.row, hoppings.col)),
            ((positions[i], positions[j] - offset) for i, j in zip(hoppings.row, hoppings.col))
        )

    if ndims == 2:
        from matplotlib.collections import LineCollection
        col = LineCollection(lines, lw=width, **kwargs)
        col.set_array(hoppings.data)
        ax.add_collection(col)
        ax.autoscale_view()
    else:
        from mpl_toolkits.mplot3d.art3d import Line3DCollection
        had_data = ax.has_data()
        col = Line3DCollection(list(lines), lw=width, **kwargs)
        col.set_array(hoppings.data)
        ax.add_collection3d(col)

        ax.set_zmargin(0.5)
        minmax = np.vstack((positions.min(axis=0), positions.max(axis=0))).T
        ax.auto_scale_xyz(*minmax, had_data=had_data)

    return col


def plot_sites(positions, data, radius, offset=(0, 0, 0), blend=1.0, **kwargs):
    """Plot circles at lattice site positions

    Parameters
    ----------
    positions : Positions
        Site coordinates in the form of a (x, y, z) tuple of arrays.
    data : array_like
        Color data at each site. Should be a 1D array of the same size as `positions`.
    radius : Union[float, array_like]
        Radius (in data units) of the plotted circles representing lattice sites.
        Should be a scalar value or array with the same size as `positions`.
    offset : Tuple[float, float, float]
            Offset all positions by a constant value.
    blend : float
        Blend all colors to white (fake alpha blending): expected values between 0 and 1.
    **kwargs
        Forwarded to :class:`.CircleCollection`.

    Returns
    -------
    :class:`.CircleCollection`
    """
    if np.all(radius == 0):
        return

    kwargs = with_defaults(kwargs, alpha=0.95, lw=0.1)

    # create colormap from discrete colors
    if 'cmap' not in kwargs:
        colors = kwargs.pop('colors', None)
        if not colors or colors == 'default':
            colors = ["#377ec8", "#ff7f00", "#41ae76", "#e41a1c",
                      "#984ea3", "#ffff00", "#a65628", "#f781bf"]
        elif colors == 'pairs':
            colors = ["#a6cee3", "#1f78b4", "#b2df8a", "#33a02c", "#fb9a99", "#e31a1c",
                      "#fdbf6f", "#ff7f00", "#cab2d6", "#6a3d9a"]
        kwargs['cmap'], kwargs['norm'] = pltutils.direct_cmap_norm(data, colors, blend)

    # create array of (x, y) points
    points = np.array(positions[:2]).T + offset[:2]

    ax = plt.gca()
    if ax.name != '3d':
        # sort based on z position to get proper 2D z-order
        idx = positions[2].argsort()
        if not np.isscalar(radius):
            radius = radius[idx]
        points, data = points[idx], data[idx]

        from pybinding.support.collections import CircleCollection
        col = CircleCollection(radius, offsets=points, transOffset=ax.transData, **kwargs)
        col.set_array(data)

        ax.add_collection(col)
        ax.autoscale_view()
    else:
        from pybinding.support.collections import Circle3DCollection
        col = Circle3DCollection(radius/8, offsets=points, transOffset=ax.transData, **kwargs)
        col.set_array(data)
        z = positions[2] + offset[2]
        col.set_3d_properties(z, 'z')

        had_data = ax.has_data()
        ax.add_collection(col)
        minmax = tuple((v.min(), v.max()) for v in positions)
        ax.auto_scale_xyz(*minmax, had_data=had_data)

    return col


def plot_site_indices(system):
    """Show the Hamiltonian index next to each atom (mainly for debugging)

    Parameters
    ----------
    system : System
    """
    for i, xy in enumerate(zip(system.x, system.y)):
        pltutils.annotate_box(i, xy)


def plot_hopping_values(system, lattice):
    """Show the hopping energy over each hopping line (mainly for debugging)

    Parameters
    ----------
    system : System
    lattice : Lattice
    """
    pos = system.xyz[:, :2]

    def get_energy(hopping_id):
        t = lattice.hopping_energies[hopping_id]
        return t.real if t.imag == 0 else t

    for i, j, k in system.hoppings.triplets():
        pltutils.annotate_box(get_energy(k), (pos[i] + pos[j]) / 2)

    for boundary in system.boundaries:
        for i, j, k in boundary.hoppings.triplets():
            pltutils.annotate_box(get_energy(k), (pos[i] + pos[j] + boundary.shift[:2]) / 2)
            pltutils.annotate_box(get_energy(k), (pos[i] + pos[j] - boundary.shift[:2]) / 2)
