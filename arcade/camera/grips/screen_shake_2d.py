"""
ScreenShakeController2D:
    Provides an easy way to cause a camera to shake.
"""

from __future__ import annotations

from math import exp, floor, log, pi, sin
from random import uniform

from arcade.camera.data_types import CameraData
from arcade.math import quaternion_rotation

__all__ = ("ScreenShake2D",)


class ScreenShake2D:
    """
    Offsets the camera position in a random direction repeatedly over
    a set length of time to create a screen shake effect.

    The amplitude of the screen-shaking grows based on two functions.
    The first is a simple sin wave whose frequency is adjustable.
    This is multiplied with a pair of equations which go from 0-1 smoothly.
    the equation rises using a inverse exponential equation, before decreasing
    using a modified smooth-step sigmoid.

    Args:
        camera_data:
            The CameraData PoD that the controller modifies. Should not be
            changed once initialized.
        max_amplitude:
            The largest possible world space offset.
        falloff_time:
            The length of time in seconds it takes the shaking to reach 0 after
            reaching the maximum. Can be set to a negative number to disable falloff.
        acceleration_duration:
            The length of time in seconds it takes the shaking to reach max
            amplitude. Can be set to 0.0 to start at max amplitude.
        shake_frequency:
            The number of peaks per second. Avoid making it a multiple of half
            the target frame-rate. (e.g. at 60 fps avoid 30, 60, 90, 120, etc.)
        direction_deg:
            Optional direction in degrees for the screen shake. If not provided,
            random directions will be used.
    """

    def __init__(
        self,
        camera_data: CameraData,
        *,
        max_amplitude: float = 1.0,
        falloff_time: float = 1.0,
        acceleration_duration: float = 1.0,
        shake_frequency: float = 15.0,
        direction_deg: float = None,
    ):
        self._data: CameraData = camera_data

        self.max_amplitude: float = max_amplitude
        """The largest possible world space offset."""

        self.falloff_duration: float = falloff_time
        """
        The length of time in seconds it takes the shaking to reach 0
        after reaching the maximum.
        """

        self.shake_frequency: float = shake_frequency
        """
        The number of peaks per second. Avoid making it a multiple of
        half the target frame-rate.
        """

        self._acceleration_duration: float = acceleration_duration

        self._shaking: bool = False
        self._length_shaking: float = 0.0

        self._current_dir: float = 0.0
        self._last_vector: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._last_update_time: float = 0.0

        self.direction_deg = direction_deg  # New argument for constant direction

    @property
    def shaking(self) -> bool:
        """Read only property to check if the controller is currently shaking the camera."""
        return self._shaking

    @property
    def duration(self) -> float:
        """
        The length of the screen shake in seconds.

        If falloff is disabled (by setting falloff_duration to a negative number) only returns the
        acceleration duration.

        Setting the duration to a negative number disables falloff.
        While the falloff is disabled setting duration will only set the acceleration.
        Otherwise, scales both the acceleration and falloff time to match new duration.
        """
        if self.falloff_duration < 0.0:
            return self._acceleration_duration
        return self._acceleration_duration + self.falloff_duration

    @duration.setter
    def duration(self, _duration: float) -> None:
        if _duration <= 0.0:
            self.falloff_duration = -1.0

        elif self.falloff_duration < 0.0:
            self._acceleration_duration = _duration
            return

        else:
            ratio = _duration / self.duration
            self._acceleration_duration = ratio * self._acceleration_duration
            self.falloff_duration = ratio * self.falloff_duration

    @property
    def current_amplitude(self) -> float:
        """Read only property which provides the current shake amplitude."""
        return self._calc_amplitude() * self.max_amplitude

    @property
    def acceleration_duration(self) -> float:
        """
        The length of time in seconds it takes for the shaking to reach max amplitude.

        Setting to a value less than zero causes the amplitude to start at max.
        """
        return self._acceleration_duration

    @acceleration_duration.setter
    def acceleration_duration(self, _duration: float) -> None:
        if _duration < 0.0:
            self._acceleration_duration = 0.0
        else:
            self._acceleration_duration = _duration

    @property
    def acceleration(self) -> float:
        """
        The inverse of acceleration time.

        setting to a value less than zero causes the amplitude to start at max.
        """
        if self._acceleration_duration <= 0.0:
            return 0.0
        return 1 / self._acceleration_duration

    @acceleration.setter
    def acceleration(self, _acceleration: float) -> None:
        if _acceleration <= 0.0:
            self._acceleration_duration = 0.0
        else:
            self._acceleration_duration = 1 / _acceleration

    @property
    def falloff(self) -> float:
        """
        The maximum gradient of the amplitude falloff,
        and is the gradient at the inflection point of the sigmoid equation.

        Is inversely proportional to the falloff duration by a factor of 15/8.
        """
        if self.falloff_duration < 0.0:
            return -1.0
        return (15 / 8) * (1 / self.falloff_duration)

    @falloff.setter
    def falloff(self, _falloff: float) -> None:
        if _falloff <= 0.0:
            self.falloff_duration = -1.0
        else:
            self.falloff_duration = (15 / 8) * (1 / _falloff)

    def _acceleration_amp(self, _t: float) -> float:
        """
        The equation for the growing half of the amplitude equation.
        It uses 1.0001 so that at _t = 1.0 the amplitude equals 1.0.

        Args:
            _t: The scaled time. Should be between 0.0 and 1.0
        """
        return 1.0001 - 1.0001 * exp(log(0.0001 / 1.0001) * _t)

    def _falloff_amp(self, _t: float) -> float:
        """
        The equation for the falloff half of the amplitude equation.
        It is based on the 'smootherstep' function.

        Args:
            _t: The scaled time. Should be between 0.0 and 1.0
        """
        return 1 - _t**3 * (_t * (_t * 6.0 - 15.0) + 10.0)

    def _calc_max_amp(self) -> float:
        """
        Determine the maximum amplitude by using either _acceleration_amp() or _falloff_amp().
        If falloff duration is less than 0.0 then the falloff never begins and
        """
        if self._length_shaking <= self._acceleration_duration:
            _t = self._length_shaking / self._acceleration_duration
            return self._acceleration_amp(_t)

        if self.falloff_duration < 0.0:
            return self.max_amplitude

        if self._length_shaking <= self.duration:
            _t = (self._length_shaking - self._acceleration_duration) / self.falloff_duration
            return self._falloff_amp(_t)

        return 0.0

    def _calc_amplitude(self) -> float:
        _max_amp = self._calc_max_amp()
        _sin_amp = sin(self.shake_frequency * 2.0 * pi * self._length_shaking)

        return _sin_amp * _max_amp

    def reset(self) -> None:
        """
        Reset the temporary shaking variables. WILL NOT STOP OR START SCREEN SHAKE.
        """
        self._current_dir = 0.0
        self._last_vector = (0.0, 0.0, 0.0)
        self._last_update_time = 0.0
        self._length_shaking = 0.0

    def start(self) -> None:
        """
        Start the screen-shake.
        """
        self.reset()
        self._shaking = True

    def stop(self) -> None:
        """
        Instantly stop the screen-shake.
        """
        self._data.position = (
            self._data.position[0] - self._last_vector[0],
            self._data.position[1] - self._last_vector[1],
            self._data.position[2] - self._last_vector[2],
        )

        self.reset()
        
    def stop(self) -> None:
        """
        Instantly stop the screen-shake.
        """
        self._data.position = (
            self._data.position[0] - self._last_vector[0],
            self._data.position[1] - self._last_vector[1],
            self._data.position[2] - self._last_vector[2],
        )

        self.reset()
        self._shaking = False

    def update(self, delta_time: float) -> None:
        """
        Update the screen-shake. Should be called every frame.

        Args:
            delta_time: The time since the last frame.
        """
        if not self._shaking:
            return

        self._length_shaking += delta_time
        amplitude = self._calc_amplitude()

        if self.direction_deg is None:
            # Use random directions if no direction is set
            angle_radians = uniform(0, 2 * pi)
        else:
            # Convert direction_deg to radians and use it
            angle_radians = self.direction_deg * (pi / 180)

        offset_x = amplitude * sin(angle_radians)
        offset_y = amplitude * sin(angle_radians + pi / 2)

        self._data.position = (
            self._data.position[0] - self._last_vector[0] + offset_x,
            self._data.position[1] - self._last_vector[1] + offset_y,
            self._data.position[2] - self._last_vector[2],
        )

        self._last_vector = (offset_x, offset_y, 0.0)

        if self._length_shaking >= self.duration:
            self.stop()
