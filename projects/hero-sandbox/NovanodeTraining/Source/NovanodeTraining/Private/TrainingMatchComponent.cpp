#include "TrainingLobby.h"

#include "AIController.h"
#include "Components/GameFrameworkComponentManager.h"
#include "Engine/GameInstance.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameModes/LyraExperienceManagerComponent.h"
#include "GameModes/LyraGameMode.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "Player/LyraPlayerState.h"

UTrainingMatchComponent::UTrainingMatchComponent(const FObjectInitializer& Initializer) : Super(Initializer)
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UTrainingMatchComponent::BeginPlay()
{
    Super::BeginPlay();
    if (GetWorld()->GetNetMode() != NM_Standalone) return;
    if (auto* Manager = GetGameState<AGameStateBase>()->FindComponentByClass<ULyraExperienceManagerComponent>())
        Manager->CallOrRegister_OnExperienceLoaded_LowPriority(
            FOnLyraExperienceLoaded::FDelegate::CreateUObject(this, &ThisClass::ExperienceLoaded));
}

void UTrainingMatchComponent::ExperienceLoaded(const ULyraExperienceDefinition*)
{
    if (bStarted || !GetOwner()->HasAuthority() || !BotControllerClass) return;
    bStarted = true;
    ALyraGameMode* Mode = GetWorld()->GetAuthGameMode<ALyraGameMode>();
    if (!Mode) return;
    auto* Components = GetWorld()->GetGameInstance()->GetSubsystem<UGameFrameworkComponentManager>();
    PawnReadyHandle = Components->RegisterAndCallForClassInitState(APawn::StaticClass(), NAME_None,
        FGameplayTag::RequestGameplayTag(TEXT("InitState.GameplayReady")),
        FActorInitStateChangedDelegate::CreateUObject(this, &ThisClass::PawnReady), true);
    for (int32 Index = 0; Index < 3; ++Index)
    {
        FActorSpawnParameters Parameters;
        Parameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        AAIController* Bot = GetWorld()->SpawnActor<AAIController>(BotControllerClass, FVector::ZeroVector, FRotator::ZeroRotator, Parameters);
        if (!Bot) continue;
        Bots.Add(Bot);
        Mode->GenericPlayerInitialization(Bot);
        if (auto* State = Bot->GetPlayerState<ALyraPlayerState>()) State->SetGenericTeamId(FGenericTeamId(1));
        Mode->RestartPlayer(Bot);
    }
    CheckReady();
}

void UTrainingMatchComponent::PawnReady(const FActorInitStateChangedParams& Params)
{
    APawn* Pawn = Cast<APawn>(Params.OwningActor);
    if (!Pawn || Pawn->GetWorld() != GetWorld() || ReadyPawns.Contains(Pawn)) return;
    ReadyPawns.Add(Pawn);
    if (APlayerController* Player = Cast<APlayerController>(Pawn->GetController()))
    {
        if (auto* State = Player->GetPlayerState<ALyraPlayerState>()) State->SetGenericTeamId(FGenericTeamId(0));
        UnbindInput();
        if (Player->IsLocalController() && MenuAction && MenuMapping)
        {
            if (auto* Input = Cast<UEnhancedInputComponent>(Pawn->InputComponent))
            {
                BoundInput = Input;
                InputHandle = Input->BindAction(MenuAction, ETriggerEvent::Started, this, &ThisClass::Pause).GetHandle();
            }
            if (auto* Local = Player->GetLocalPlayer())
                if (auto* Input = Local->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>()) Input->AddMappingContext(MenuMapping, 100);
        }
    }
    CheckReady();
}

void UTrainingMatchComponent::CheckReady()
{
    APlayerController* Human = GetWorld()->GetGameInstance()->GetFirstLocalPlayerController();
    int32 ReadyBots = 0;
    for (const auto& Bot : Bots)
        if (Bot.IsValid() && Bot->GetPawn() && ReadyPawns.Contains(Bot->GetPawn()))
            if (auto* State = Bot->GetPlayerState<ALyraPlayerState>())
                if (State->GetGenericTeamId() == FGenericTeamId(1)) ++ReadyBots;
    int32 TotalBots = 0;
    for (APlayerState* State : GetGameState<AGameStateBase>()->PlayerArray)
        if (State && State->IsABot()) ++TotalBots;
    if (auto* Session = GetWorld()->GetGameInstance()->GetSubsystem<UTrainingLobbySubsystem>())
        Session->MatchReady(Human && Human->GetPawn() && ReadyPawns.Contains(Human->GetPawn()) && TotalBots == 3, ReadyBots);
}

void UTrainingMatchComponent::Pause()
{
    if (auto* Session = GetWorld()->GetGameInstance()->GetSubsystem<UTrainingLobbySubsystem>()) Session->OpenPause();
}

void UTrainingMatchComponent::UnbindInput()
{
    if (BoundInput.IsValid()) BoundInput->RemoveBindingByHandle(InputHandle);
    BoundInput.Reset();
    InputHandle = 0;
}

void UTrainingMatchComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (auto* Components = GetWorld()->GetGameInstance()->GetSubsystem<UGameFrameworkComponentManager>())
        Components->UnregisterClassInitStateDelegate(APawn::StaticClass(), PawnReadyHandle);
    UnbindInput();
    if (auto* Human = GetWorld()->GetGameInstance()->GetFirstLocalPlayerController())
        if (auto* Local = Human->GetLocalPlayer())
            if (auto* Input = Local->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
                if (MenuMapping) Input->RemoveMappingContext(MenuMapping);
    for (const auto& Bot : Bots)
    {
        if (!Bot.IsValid()) continue;
        if (APawn* Pawn = Bot->GetPawn()) Pawn->Destroy();
        Bot->Destroy();
    }
    Bots.Reset();
    ReadyPawns.Reset();
    bStarted = false;
    Super::EndPlay(Reason);
}
