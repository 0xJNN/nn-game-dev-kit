#include "LabState.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FNovanodePrerequisites, "Novanode.State.Prerequisites",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FNovanodePrerequisites::RunTest(const FString& Parameters)
{
    FLabState State;
    TestFalse(TEXT("Cannot run before power and door"), State.RunReference());
    State.TogglePower();
    TestFalse(TEXT("Power alone is insufficient"), State.RunReference());
    State.ToggleDoor();
    TestTrue(TEXT("Prerequisites permit reference"), State.RunReference());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FNovanodePeriod, "Novanode.State.Period",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FNovanodePeriod::RunTest(const FString& Parameters)
{
    FLabState State;
    State.ToggleDoor();
    State.TogglePower();
    TestTrue(TEXT("Runs reference"), State.RunReference());
    TestTrue(TEXT("Independent numerical reference"), std::abs(State.PeriodSeconds - 2.00606668) < 0.00001);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FNovanodeInvalidInputs, "Novanode.State.InvalidInputs",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FNovanodeInvalidInputs::RunTest(const FString& Parameters)
{
    FLabState State;
    State.ToggleDoor();
    State.TogglePower();
    TestFalse(TEXT("Reject zero gravity"), State.RunReference(1.0, 0.0));
    TestFalse(TEXT("Reject negative length"), State.RunReference(-1.0, 9.81));
    return true;
}
#endif
