#pragma once

// Engine-independent transition policy. This is not a simulation of Unreal travel.
namespace NovanodeTraining
{
enum class Screen { Inactive, Lobby, Selection, Hosting, Match, Returning };
enum class Hero { None, Melee, Mage };

// Team IDs come from Lyra's registered teams, not zero-based UI indices.
inline int SelectRivalTeam(const int* Teams, int Count, int HumanTeam)
{
    if (!Teams || Count != 2 || Teams[0] < 0 || Teams[1] < 0 ||
        Teams[0] >= 255 || Teams[1] >= 255 || Teams[0] == Teams[1]) return -1;
    if (Teams[0] == HumanTeam) return Teams[1];
    if (Teams[1] == HumanTeam) return Teams[0];
    return -1;
}

struct MatchEvidence
{
    bool HumanReady = false;
    int TotalBots = 0;
    int OwnedBots = 0;
    int ReadyBots = 0;
    int RivalBots = 0;
    int MatchComponents = 0;
    int HumanTeam = -1;
    int RivalTeam = -1;
    bool Valid() const
    {
        return HumanReady && TotalBots == 3 && OwnedBots == 3 && ReadyBots == 3 && RivalBots == 3 &&
            MatchComponents == 1 && HumanTeam >= 0 && HumanTeam < 255 && RivalTeam >= 0 &&
            RivalTeam < 255 && HumanTeam != RivalTeam;
    }
};

struct LoopEvidence
{
    int LobbyArrivals = 0;
    int NativeReturns = 0;
    int Cleanups = 0;
    int ReadyMatches = 0;
    bool CleanupValid = true;
    MatchEvidence Matches[2];
    bool Complete() const
    {
        return ReadyMatches == 2 && LobbyArrivals == 3 && NativeReturns == 2 && Cleanups == 2 &&
            CleanupValid && Matches[0].Valid() && Matches[1].Valid();
    }
};

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
    bool BeginNativeMatch()
    {
        if (State != Screen::Inactive && State != Screen::Returning) return false;
        State = Screen::Hosting;
        Selected = Hero::None;
        ++MatchGeneration;
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
