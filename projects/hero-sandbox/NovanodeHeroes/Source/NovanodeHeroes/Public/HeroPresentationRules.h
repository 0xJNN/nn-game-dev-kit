#pragma once

#include <cmath>

namespace NovanodeHeroes
{
// TextRender glyphs face local -X. Keep Z upright; turn the readable side toward
// the viewer, not the back of a two-sided font material. No negative scales.
inline double TextFacingYaw(double TextX, double TextY, double ViewX, double ViewY, double Previous = 0.)
{
    const double X = ViewX - TextX, Y = ViewY - TextY;
    if (!std::isfinite(X) || !std::isfinite(Y) || X * X + Y * Y < 0.0001) return Previous;
    constexpr double RadiansToDegrees = 57.29577951308232;
    double Yaw = std::atan2(Y, X) * RadiansToDegrees + 180.;
    if (Yaw > 180.) Yaw -= 360.;
    return Yaw;
}

inline bool HasUsableBody(int ControllerAssemblers, int AttachedBodyActors, int VisibleBodies, int AnimatedBodies)
{
    return ControllerAssemblers > 0 && AttachedBodyActors > 0 && VisibleBodies > 0 && AnimatedBodies > 0;
}
}
