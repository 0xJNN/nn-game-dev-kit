#include "StudioHUD.h"
#include "StudioCharacter.h"
#include "StudioGameMode.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"

void AStudioHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas || !PlayerOwner) { return; }
    const auto* Lab = GetWorld()->GetAuthGameMode<AStudioGameMode>();
    if (!Lab) { return; }
    const FLinearColor Teal(0.15f, 0.95f, 0.80f), Muted(0.55f, 0.68f, 0.77f);
    DrawRect(FLinearColor(0.015f, 0.025f, 0.045f, 0.88f), 28, 28, 455, 170);
    DrawRect(Teal, 28, 28, 3, 170);
    DrawText(TEXT("NOVANODE / RESEARCH 01"), FLinearColor::White, 48, 44, GEngine->GetSmallFont(), 1.5f);
    const FLabState& State = Lab->GetLabState();
    DrawText(FString::Printf(TEXT("AIRLOCK  %s     POWER  %s"),
        State.DoorOpen ? TEXT("OPEN") : TEXT("SEALED"), State.PowerOn ? TEXT("ONLINE") : TEXT("OFFLINE")),
        Teal, 48, 82, GEngine->GetSmallFont(), 1.f);
    DrawText(Lab->Notice, Muted, 48, 112, GEngine->GetSmallFont(), 0.9f);
    DrawText(TEXT("Analytical reference / not a validated physics simulation"), Muted,
        48, 164, GEngine->GetSmallFont(), 0.8f);
    const float X = Canvas->SizeX * 0.5f, Y = Canvas->SizeY * 0.5f;
    DrawRect(Teal, X - 5, Y, 11, 1);
    DrawRect(Teal, X, Y - 5, 1, 11);
    if (const auto* Character = Cast<AStudioCharacter>(PlayerOwner->GetPawn()))
    {
        DrawText(Lab->InteractionPrompt(Character->TraceInteraction()), Teal,
            X - 130, Y + 32, GEngine->GetSmallFont(), 1.f);
    }
    DrawText(TEXT("WASD MOVE   /   MOUSE LOOK   /   E INTERACT   /   ESC CURSOR"), Muted,
        28, Canvas->SizeY - 40, GEngine->GetSmallFont(), 1.f);
}
