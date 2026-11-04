#pragma once

#include <cmath>
#include <cstdint>
#include <unordered_set>

// Engine-independent rules: shared by the live component and regression tests.
// Time comes from the authoritative world, never from an RPC argument.
namespace NovanodeHeroes
{
enum class Kit : uint8_t { Mage, Sword };

struct CombatRules
{
    Kit Selected = Kit::Mage;
    double PrimaryReadyAt = 0.0;
    double DashReadyAt = 0.0;
    double ComboExpiresAt = 0.0;
    int Combo = 0;
    std::unordered_set<uint32_t> HitTargets;

    bool TryPrimary(double Now)
    {
        if (!std::isfinite(Now) || Now < 0.0 || Now < PrimaryReadyAt)
            return false;
        if (Selected == Kit::Sword)
        {
            Combo = Now <= ComboExpiresAt ? (Combo % 3) + 1 : 1;
            ComboExpiresAt = Now + 1.15;
            PrimaryReadyAt = Now + (Combo == 3 ? 0.65 : 0.42);
        }
        else
        {
            Combo = 0;
            PrimaryReadyAt = Now + 0.8;
        }
        HitTargets.clear();
        return true;
    }

    void Select(Kit Value)
    {
        Selected = Value;
        Combo = 0;
        ComboExpiresAt = 0.0;
        // Switching kits intentionally does not reset either cooldown.
    }

    bool TryDash(double Now)
    {
        if (Selected != Kit::Sword || !std::isfinite(Now) || Now < 0.0 || Now < DashReadyAt)
            return false;
        DashReadyAt = Now + 2.5;
        return true;
    }

    bool FirstHit(uint32_t Target) { return HitTargets.insert(Target).second; }
    float Damage() const { return Selected == Kit::Mage ? 25.f : (Combo == 3 ? 30.f : 20.f); }
};
}
