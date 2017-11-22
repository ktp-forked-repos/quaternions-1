import functools
import numpy as np
from collections import Iterable
import numbers

from quaternions.general_quaternion import GeneralQuaternion, QuaternionError, DEFAULT_TOLERANCE, is_quaternion


class Quaternion(GeneralQuaternion):
    ''' A class that holds unit quaternions (norm==1, aka versors). It actually holds Q^op, as
    this is the way Schaub-Jenkins work with them.
    Note: Quaternion is equal up to sign.
    '''
    tolerance = 1e-8

    def __init__(self, qr, qi, qj, qk):
        q = [qr, qi, qj, qk]
        norm = np.linalg.norm(q)
        if norm < DEFAULT_TOLERANCE:
            raise QuaternionError('provided numerically unstable quaternion: %s' % q)

        super().__init__(*q / norm)

    def __mul__(self, p):
        if isinstance(p, Quaternion) or isinstance(p, numbers.Number):
            mul = GeneralQuaternion(*self.coordinates) * p
            return Quaternion(*mul.coordinates)
        elif isinstance(p, GeneralQuaternion):
            return GeneralQuaternion(*self.coordinates) * p
        elif isinstance(p, Iterable) and len(p) == 3:  # applies quaternion rotation on vector
            return self.matrix.dot(p)
        else:
            raise QuaternionError('cant multiply by %s' % type(p))

    def __call__(self, p):
        return self * p

    def is_equal(self, other, tolerance=DEFAULT_TOLERANCE):
        """ compares as quaternions, i.e. up to sign. """
        return super().is_equal(other, tolerance) or super().is_equal(-other, tolerance)

    def __eq__(self, other):
        return self.is_equal(other)

    def log(self):
        """
        logarithm of quaternion
        :return: GeneralQuaternion
        """
        norm = self.norm()
        imag = np.array((self.qi, self.qj, self.qk)) / norm
        imag_norm = np.linalg.norm(imag)
        if imag_norm == 0:
            i_part = 0 if self.qr > 0 else np.pi
            return GeneralQuaternion(np.log(norm), i_part, 0, 0)

        j, k, l = imag / imag_norm * np.arctan2(imag_norm, self.qr / norm)
        return GeneralQuaternion(np.log(norm), j, k, l)

    def distance(self, other):
        """ Returns the distance in radians between two unitary quaternions. """
        return min(super().euclidean_distance(other), super().euclidean_distance(-other))

    @property
    def positive_representant(self):
        """
        Unitary quaternions q and -q correspond to the same element in SO(3).
        In order to perform some computations (v.g., distance), it is important
        to fix one of them.

        Though the following computations can be done for any quaternion, we allow them
        only for unitary ones.
        """
        for coord in self.coordinates:
            if coord > 0:
                return self
            if coord < 0:
                return -self

    @property
    def matrix(self):
        """ returns 3x3 rotation matrix representing the same rotation. """
        qr, qi, qj, qk = self.coordinates
        return np.array([
            [qr * qr + qi * qi - qj * qj - qk * qk,
                2 * (qi * qj + qr * qk),
                2 * (qi * qk - qr * qj)],
            [2 * (qi * qj - qr * qk),
                qr * qr - qi * qi + qj * qj - qk * qk,
                2 * (qj * qk + qr * qi)],
            [2 * (qi * qk + qr * qj),
                2 * (qj * qk - qr * qi),
                qr * qr - qi * qi - qj * qj + qk * qk]
        ])

    @classmethod
    def _first_eigenvector(cls, matrix):
        """ matrix must be a 4x4 symmetric matrix. """
        vals, vecs = np.linalg.eigh(matrix)
        # q is the eigenvec with heighest eigenvalue (already normalized)
        q = vecs[:, -1]
        if q[0] < 0:
            q = -q
        return cls(*q)

    @classmethod
    def average(cls, *quaternions, weights=None):
        """
        Return the quaternion such that its matrix minimizes the square distance
        to the matrices of the quaternions in the argument list.

        See Averaging Quaternions, by Markley, Cheng, Crassidis, Oschman.
        """
        b = np.array([q.coordinates for q in quaternions])
        if weights is None:
            weights = np.ones(len(quaternions))
        m = b.T.dot(np.diag(weights)).dot(b)

        return cls._first_eigenvector(m)

    @property
    def basis(self):
        m = self.matrix
        return m[0, :], m[1, :], m[2, :]

    @property
    def rotation_vector(self):
        """ returns [x, y, z]: direction is rotation axis, norm is angle [rad]  """
        return (2 * self.log()).coordinates[1:]

    def rotation_axis(self):
        """ returns unit rotation axis: [x, y, z] """
        v = self.rotation_vector
        return v / np.linalg.norm(v)

    def rotation_angle(self):
        """ returns rotation angle [rad] """
        return np.linalg.norm(self.rotation_vector)

    @property
    def ra_dec_roll(self):
        '''Returns ra, dec, roll for quaternion [deg].
        The Euler angles are those called Tait-Bryan XYZ, as defined in
        https://en.wikipedia.org/wiki/Euler_angles#Tait-Bryan_angles
        '''
        m = self.matrix
        ra_rad = np.arctan2(-m[0][1], m[0][0])
        dec_rad = np.arctan2(m[0][2], np.sqrt(m[1][2] ** 2 + m[2][2] ** 2))
        roll_rad = np.arctan2(-m[1][2], m[2][2])
        return np.rad2deg(np.array([ra_rad, dec_rad, roll_rad]))

    @property
    def astrometry_ra_dec_roll(self):
        '''Returns ra, dec, roll as reported by astrometry [deg].
        Notice that Tetra gives a different roll angle, so this is not
        a fixed standard.
        '''
        twisted = self.OpticalAxisFirst() * self
        ra, dec, roll = twisted.ra_dec_roll
        return np.array([-ra, dec, roll - 180])

    @staticmethod
    def from_matrix(mat):
        """ Returns the quaternion corresponding to the unitary matrix mat. """
        mat = np.array(mat)
        tr = np.trace(mat)
        d = 1 + 2 * mat.diagonal() - tr
        qsquare = 1 / 4 * np.array([1 + tr, d[0], d[1], d[2]])
        qsquare = qsquare.clip(0, None)  # avoid numerical errors
        # compute signs matrix
        signs = np.sign([mat[1, 2] - mat[2, 1], mat[2, 0] - mat[0, 2], mat[0, 1] - mat[1, 0],
                         mat[0, 1] + mat[1, 0], mat[2, 0] + mat[0, 2], mat[1, 2] + mat[2, 1]])
        signs_m = np.zeros((4, 4))
        signs_m[np.triu_indices(4, 1)] = signs
        signs_m += signs_m.T
        signs_m[np.diag_indices(4)] = 1.
        # choose appropriate signs
        max_idx = qsquare.argmax()
        coords = np.sqrt(qsquare) * signs_m[max_idx]
        return Quaternion(*coords)

    @staticmethod
    def from_rotation_vector(xyz):
        '''
        Returns the quaternion corresponding to the rotation xyz.
        Explicitly: rotation occurs along the axis xyz and has angle
        norm(xyz)

        This corresponds to the exponential of the quaternion with
        real part 0 and imaginary part 1/2 * xyz.
        '''
        a, b, c = .5 * np.array(xyz)
        return Quaternion.exp([0, a, b, c ])

    @staticmethod
    def from_qmethod(source, target, probabilities=None):
        '''
        Returns the quaternion corresponding to solving with qmethod.

        See: Closed-form solution of absolute orientation using unit quaternions,
        Berthold K. P. Horn,
        J. Opt. Soc. Am. A, Vol. 4, No. 4, April 1987

        It "sends" the (3xn) matrix source to the (3xn) matrix target.
        Vectors are multiplied by probabilities too, if available.

        "sends" means that if q = Quaternion.from_qmethod(s, t)
        then q.matrix will be a rotation matrix (not a coordinate changing matrix).
        In other words, q.matrix.dot(s) ~ t

        The method can also produce the change of basis quaternion
        in this way: assume that there are vectors v1,..., vn for which we have coordinates
        in two frames, F1 and F2.
        If s and t are the 3xn matrices of v1,..., vn in frames F1 and F2, then
        Quaternion.from_qmethod(s, t) is the quaternion corresponding to the change of basis
        from F1 to F2.
        '''
        if probabilities is not None:
            B = source.dot(np.diag(probabilities)).dot(target.T)
        else:
            B = source.dot(target.T)
        sigma = np.trace(B)
        S = B + B.T
        Z = B - B.T
        i, j, k = Z[2, 1], Z[0, 2], Z[1, 0]
        K = np.zeros((4, 4))
        K[0] = [sigma, i, j, k]
        K[1:4, 0] = [i, j, k]
        K[1:4, 1:4] = S - sigma * np.identity(3)
        return Quaternion._first_eigenvector(K)

    @staticmethod
    def integrate_from_velocity_vectors(vectors):
        '''vectors must be an iterable of 3-d vectors.
        This method just exponentiates all vectors/2, multiplies them and takes 2*log.
        Thus, the return value corresponds to the resultant rotation vector of a body
        under all rotations in the iterable.
        '''
        qs = list(map(Quaternion.from_rotation_vector, vectors))[::-1]
        prod = functools.reduce(Quaternion.__mul__, qs, Quaternion.unit())
        return prod.rotation_vector

    @staticmethod
    def from_ra_dec_roll(ra, dec, roll):
        '''constructs a quaternion from ra/dec/roll params
        using Tait-Bryan angles XYZ.

        ra stands for right ascencion, and usually lies in [0, 360]
        dec stands for declination, and usually lies in [-90, 90]
        roll stands for rotation/rolling, and usually lies in [0, 360]
        '''
        raq = Quaternion.exp([0, 0, 0, -np.deg2rad(ra) / 2])
        decq = Quaternion.exp([0, 0, -np.deg2rad(dec) / 2, 0])
        rollq = Quaternion.exp([0, -np.deg2rad(roll) / 2, 0, 0])
        return rollq * decq * raq

    @staticmethod
    def OpticalAxisFirst():
        '''
        This quaternion is useful for changing from camera coordinates in
        two standard frames:

        Let the sensor plane have axes
        R (pointing horizontally to the right)
        D (pointing vertically down)
        and let P be the optical axis, pointing "outwards", i.e., from the
        focus to the center of the focal plane.

        One typical convention is taking the frame [R, D, P].
        The other one is taking the frame [P, -R, -D].

        This quaternion gives the change of basis from the first to the second.
        '''
        return Quaternion(0.5, 0.5, -.5, 0.5)
