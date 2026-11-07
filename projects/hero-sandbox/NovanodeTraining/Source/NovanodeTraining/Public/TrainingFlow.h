#pragma once

// Engine-independent transition policy. This is not a simulation of Unreal travel.
namespace NovanodeTraining
{
enum class Screen { Inactive, Lobby, Selection, Hosting, Match, Returning };
enum class Hero { None, Melee, Mage };

struct Flow
{
    Screen State = Screen::Inactive;
    Hero Selected = Hero::None;
    unsigned MatchGeneration = 0;

    bool ArriveAtLobby()
    {
        if (State != Screen::Inactive && State != Screen::Returning) return false;
        State = Screen::Lobby;
        Selected = Hero::None;
        return true;
    }
    bool OpenSelection()
    {
        if (State != Screen::Lobby) return false;
        State = Screen::Selection;
        return true;
    }
    bool Choose(Hero Value)
    {
        if (State != Screen::Selection || Value == Hero::None) return false;
        Selected = Value;
        return true;
    }
    bool BeginHosting()
    {
        if (State != Screen::Selection || Selected == Hero::None) return false;
        State = Screen::Hosting;
        ++MatchGeneration;
        return true;
    }
    void HostFailed() { if (State == Screen::Hosting) State = Screen::Selection; }
    bool MatchReady(bool HumanReady, int RivalBots)
    {
        if (State != Screen::Hosting || !HumanReady || RivalBots != 3) return false;
        State = Screen::Match;
        return true;
    }
    bool Return()
    {
        if (State != Screen::Match && State != Screen::Hosting) return false;
        State = Screen::Returning;
        return true;
    }
    bool Back()
    {
        if (State != Screen::Selection) return false;
        State = Screen::Lobby;
        Selected = Hero::None;
        return true;
    }
};
}
