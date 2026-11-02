#include "LabState.h"
#include <cstdlib>
#include <iostream>
#include <limits>

#define CHECK(condition) do { if (!(condition)) { std::cerr << "Failed: " #condition << '\n'; return EXIT_FAILURE; } } while (false)

int main()
{
    FLabState State;
    CHECK(!State.RunReference());
    State.TogglePower();
    CHECK(!State.RunReference());
    State.ToggleDoor();
    CHECK(State.RunReference());
    CHECK(State.ExperimentComplete);
    CHECK(std::abs(State.PeriodSeconds - 2.00606668) < 0.00001);
    CHECK(!State.RunReference(1.0, 0.0));
    CHECK(!State.RunReference(-1.0));
    CHECK(!State.RunReference(std::numeric_limits<double>::quiet_NaN()));
    CHECK(!State.RunReference(1.0, std::numeric_limits<double>::infinity()));
    CHECK(!State.RunReference(1.0, std::numeric_limits<double>::denorm_min()));
    CHECK(!State.RunReference(std::numeric_limits<double>::denorm_min(), 1e308));
    State.TogglePower();
    CHECK(!State.RunReference());
    std::cout << "Portable lab-state checks passed; engine integration not exercised\n";
    return EXIT_SUCCESS;
}
