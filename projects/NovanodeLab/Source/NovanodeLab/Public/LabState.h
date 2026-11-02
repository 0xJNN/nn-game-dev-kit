#pragma once

#include <cmath>

// Engine-independent state: compile/run its tests without downloading Unreal or consuming GPU VRAM.
struct FLabState
{
    bool DoorOpen = false;
    bool PowerOn = false;
    bool ExperimentComplete = false;
    double PeriodSeconds = 0.0;

    void ToggleDoor() { DoorOpen = !DoorOpen; }
    void TogglePower() { PowerOn = !PowerOn; }

    bool RunReference(double LengthMeters = 1.0, double Gravity = 9.81)
    {
        if (!DoorOpen || !PowerOn || !std::isfinite(LengthMeters) ||
            !std::isfinite(Gravity) || LengthMeters <= 0.0 || Gravity <= 0.0)
        {
            return false;
        }
        const double Period = 2.0 * 3.14159265358979323846 * std::sqrt(LengthMeters / Gravity);
        if (!std::isfinite(Period) || Period <= 0.0)
        {
            return false;
        }
        PeriodSeconds = Period;
        ExperimentComplete = true;
        return true;
    }
};
