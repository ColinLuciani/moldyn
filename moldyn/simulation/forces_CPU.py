"""
Forces calculator.
Runs on GPU.
"""

"""
installer icc-rt et tbb sur les machines à processeur intel
"""

import numpy as np
import numba
import threading


@numba.njit
def force(dist, epsilon, p):
    return (-4.0 * epsilon * (6.0 * p - 12.0 * p * p)) / (dist * dist)


@numba.njit
def energy(dist, epsilon, p):
    # p = (dist/sigma)**6
    return epsilon * (4.0 * (p * p - p) + 127.0 / 4096.0)


@numba.njit
def _iterate(current_pos, i, pos, F, PE, counts, a, b, epsilon, sigma, rcut, X_PERIODIC, Y_PERIODIC, SHIFT_X, SHIFT_Y, LENGTH_X, LENGTH_Y):
    for j in range(a, b):
        distxy = current_pos - pos[j, :]
        dist = np.sqrt(sum(distxy ** 2))

        if X_PERIODIC:
            if distxy.x < (-SHIFT_X):
                distxy.x += LENGTH_X
            if distxy.x > SHIFT_X:
                distxy.x -= LENGTH_X

        if Y_PERIODIC:
            if distxy.y < (-SHIFT_Y):
                distxy.y += LENGTH_Y
            if distxy.y > SHIFT_Y:
                distxy.y -= LENGTH_Y

        if dist < rcut:
            p = (dist / sigma) ** 6
            F[i, :] += force(dist, epsilon, p)*distxy
            PE[i] += energy(dist, epsilon, p)
            counts[i] += 1


@numba.njit(parallel=True, nogil=True, cache=True)
def _compute_forces(pos, F, PE, counts, consts, offset=0, end=None):
    EPSILON_A = consts["EPSILON_A"]
    EPSILON_B = consts["EPSILON_B"]
    EPSILON_AB = consts["EPSILON_AB"]
    SIGMA_A = consts["SIGMA_A"]
    SIGMA_B = consts["SIGMA_B"]
    SIGMA_AB = consts["SIGMA_AB"]
    RCUT_A = consts["RCUT_A"]
    RCUT_B = consts["RCUT_B"]
    RCUT_AB = consts["RCUT_AB"]
    N_A = consts["N_A"]
    NPART = consts["NPART"]
    LENGTH_X = consts["LENGTH_X"]
    LENGTH_Y = consts["LENGTH_Y"]
    X_PERIODIC = consts["X_PERIODIC"]
    Y_PERIODIC = consts["Y_PERIODIC"]

    SHIFT_X = LENGTH_X / 2
    SHIFT_Y = LENGTH_Y / 2
    end = end or NPART

    for i in numba.prange(offset, end):
        current_pos = pos[i,:]
        F[i, :] = 0
        PE[i] = 0.0
        counts[i] = 0
        if i < N_A:
            _iterate(current_pos, i, pos, F, PE, counts, 0, N_A, EPSILON_A, SIGMA_A, RCUT_A, X_PERIODIC, Y_PERIODIC, SHIFT_X, SHIFT_Y, LENGTH_X, LENGTH_Y)
            _iterate(current_pos, i, pos, F, PE, counts, N_A, NPART, EPSILON_AB, SIGMA_AB, RCUT_AB, X_PERIODIC, Y_PERIODIC, SHIFT_X, SHIFT_Y, LENGTH_X, LENGTH_Y)
        else:
            _iterate(current_pos, i, pos, F, PE, counts, 0, N_A, EPSILON_AB, SIGMA_AB, RCUT_AB, X_PERIODIC, Y_PERIODIC, SHIFT_X, SHIFT_Y, LENGTH_X, LENGTH_Y)
            _iterate(current_pos, i, pos, F, PE, counts, N_A, NPART, EPSILON_B, SIGMA_B, RCUT_B, X_PERIODIC, Y_PERIODIC, SHIFT_X, SHIFT_Y, LENGTH_X, LENGTH_Y)


class ForcesComputeCPU:

    def __init__(self, consts, compute_npart=None, compute_offset=0):

        self.consts = consts

        self.compute_offset = max(0, compute_offset)

        self.npart = consts["npart"]
        self.compute_npart = compute_npart or (consts["NPART"] - self.compute_offset)

        self.compute_npart = min(self.compute_npart, self.npart)

        self.array_shape = (self.npart, 2)
        self._POS = np.zeros(self.array_shape, dtype=np.float32)
        self._F = np.zeros(self.array_shape, dtype=np.float32)
        self._PE = np.zeros((self.npart,), dtype=np.float32)
        self._COUNT = np.zeros((self.npart,), dtype=np.float32)

        self.thr_run = False

    def _compute_forces(self):
        _compute_forces(self._POS, self._F, self._PE, self._COUNT, self.consts, offset=self.compute_offset)

    def _join_thr(self):
        if self.thr_run:
            self.thread.join()
            self.thr_run = False

    def set_pos(self, pos):
        self._POS[:,:] = pos
        self.thr_run = True
        self.thread = threading.Thread(target=self._compute_forces)
        self.thread.start()

    def get_F(self):
        self._join_thr()
        return self._F[:,:]

    def get_PE(self):
        self._join_thr()
        return self._PE[:]

    def get_COUNT(self):
        self._join_thr()
        return self._COUNT[:]