#include "HeroSandbox.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHeroCooldownTest, "Novanode.Heroes.Rules.Cooldown",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHeroCooldownTest::RunTest(const FString&)
{
    NovanodeHeroes::CombatRules Rules;
    TestTrue(TEXT("First spell"), Rules.TryPrimary(1.0));
    TestFalse(TEXT("Spam is rejected"), Rules.TryPrimary(1.1));
    Rules.Select(NovanodeHeroes::Kit::Sword);
    TestFalse(TEXT("Switch does not bypass cooldown"), Rules.TryPrimary(1.2));
    TestTrue(TEXT("Ready exactly at boundary"), Rules.TryPrimary(1.8));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHeroComboTest, "Novanode.Heroes.Rules.ComboAndDeduplication",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHeroComboTest::RunTest(const FString&)
{
    NovanodeHeroes::CombatRules Rules;
    Rules.Select(NovanodeHeroes::Kit::Sword);
    TestTrue(TEXT("First strike"), Rules.TryPrimary(2.0));
    TestEqual(TEXT("Combo starts at one"), Rules.Combo, 1);
    TestTrue(TEXT("First target hit"), Rules.FirstHit(42));
    TestFalse(TEXT("Same target once per swing"), Rules.FirstHit(42));
    TestTrue(TEXT("Second strike"), Rules.TryPrimary(2.5));
    TestTrue(TEXT("New swing may hit same target"), Rules.FirstHit(42));
    TestEqual(TEXT("Second combo"), Rules.Combo, 2);
    TestTrue(TEXT("Third strike"), Rules.TryPrimary(3.0));
    TestEqual(TEXT("Third combo damage"), Rules.Damage(), 30.f);
    TestTrue(TEXT("Combo expires"), Rules.TryPrimary(5.0));
    TestEqual(TEXT("Expired restarts at one"), Rules.Combo, 1);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHeroDashTest, "Novanode.Heroes.Rules.DashAndInvalidTime",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FHeroDashTest::RunTest(const FString&)
{
    NovanodeHeroes::CombatRules Rules;
    TestFalse(TEXT("Mage cannot dash"), Rules.TryDash(0.0));
    TestFalse(TEXT("Negative time"), Rules.TryPrimary(-1.0));
    TestFalse(TEXT("NaN"), Rules.TryPrimary(NAN));
    Rules.Select(NovanodeHeroes::Kit::Sword);
    TestTrue(TEXT("Sword dash"), Rules.TryDash(2.0));
    TestFalse(TEXT("Dash cooldown"), Rules.TryDash(2.1));
    TestTrue(TEXT("Dash ready"), Rules.TryDash(4.5));
    return true;
}
#endif
