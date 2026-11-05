#pragma once

#include <cstdint>

// Pure transition rules shared by the real UI and compiled repository tests.
// No engine, UI, input or networking side effects are hidden in this state.
namespace NovanodeHeroes
{
enum class TrainingScreen : uint8_t { Lobby, HeroSelection, Loading, Playing, Paused, Returning };
enum class TrainingHero : uint8_t { Melee, Mage };

struct TrainingFlow
{
    TrainingScreen Screen = TrainingScreen::Lobby;
    TrainingHero Hero = TrainingHero::Melee;
    bool HasSelection = false;

    bool OpenTraining()
    {
        if (Screen != TrainingScreen::Lobby) return false;
        Screen = TrainingScreen::HeroSelection;
        HasSelection = false;
        return true;
    }
    bool Choose(TrainingHero Value)
    {
        if (Screen != TrainingScreen::HeroSelection ||
            (Value != TrainingHero::Melee && Value != TrainingHero::Mage)) return false;
        Hero = Value;
        HasSelection = true;
        return true;
    }
    bool Start(bool AssetsReady)
    {
        if (Screen != TrainingScreen::HeroSelection || !HasSelection || !AssetsReady) return false;
        Screen = TrainingScreen::Loading;
        return true;
    }
    bool MatchReady(bool PawnReady, int OpposingBots)
    {
        if (Screen != TrainingScreen::Loading || !PawnReady || OpposingBots != 3) return false;
        Screen = TrainingScreen::Playing;
        return true;
    }
    bool Pause()
    {
        if (Screen != TrainingScreen::Playing) return false;
        Screen = TrainingScreen::Paused;
        return true;
    }
    bool Resume()
    {
        if (Screen != TrainingScreen::Paused) return false;
        Screen = TrainingScreen::Playing;
        return true;
    }
    bool Return()
    {
        if (Screen != TrainingScreen::Playing && Screen != TrainingScreen::Paused &&
            Screen != TrainingScreen::Loading) return false;
        Screen = TrainingScreen::Returning;
        return true;
    }
    bool ArriveAtLobby()
    {
        if (Screen != TrainingScreen::Returning) return false;
        Screen = TrainingScreen::Lobby;
        HasSelection = false;
        return true;
    }
    bool BackFromSelection()
    {
        if (Screen != TrainingScreen::HeroSelection) return false;
        Screen = TrainingScreen::Lobby;
        HasSelection = false;
        return true;
    }
};
}
