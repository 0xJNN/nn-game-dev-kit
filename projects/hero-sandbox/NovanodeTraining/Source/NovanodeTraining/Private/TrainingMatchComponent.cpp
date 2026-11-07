#include "TrainingLobby.h"

#include "AIController.h"
#include "Character/LyraHeroComponent.h"
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
#include "Teams/LyraTeamSubsystem.h"
#include "Dom/JsonObject.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Serialization/JsonSerializer.h"
#include "HAL/FileManager.h"

namespace
{
void InitializationDiagnostic(const TCHAR* Stage, ALyraGameMode* Mode, AAIController* Bot,
    int32 HumanTeam, int32 RivalTeam, const TArray<int32>& TeamIDs, bool AssignedTeamsValid)
{
    FString Path;
    if (!FParse::Value(FCommandLine::Get(), TEXT("NovanodeTrainingDiagnostics="), Path)) return;
    const bool ModeValid = IsValid(Mode), BotValid = IsValid(Bot);
    ALyraPlayerState* State = BotValid ? Bot->GetPlayerState<ALyraPlayerState>() : nullptr;
    TSharedRef<FJsonObject> Data = MakeShared<FJsonObject>();
    Data->SetStringField(TEXT("stage"), Stage);
    Data->SetBoolField(TEXT("game_mode_valid"), ModeValid);
    Data->SetBoolField(TEXT("controller_valid"), BotValid);
    Data->SetBoolField(TEXT("player_state_valid"), IsValid(State));
    Data->SetBoolField(TEXT("bot_flag"), IsValid(State) && State->IsABot());
    Data->SetBoolField(TEXT("same_world"), ModeValid && BotValid && IsValid(State) &&
        Mode->GetWorld() == Bot->GetWorld() && State->GetWorld() == Mode->GetWorld());
    Data->SetBoolField(TEXT("authority"), ModeValid && BotValid && Mode->HasAuthority() && Bot->HasAuthority());
    Data->SetBoolField(TEXT("mode_destroying"), ModeValid && Mode->IsActorBeingDestroyed());
    Data->SetBoolField(TEXT("controller_destroying"), BotValid && Bot->IsActorBeingDestroyed());
    Data->SetBoolField(TEXT("player_state_destroying"), IsValid(State) && State->IsActorBeingDestroyed());
    Data->SetBoolField(TEXT("controller_begun_play"), BotValid && Bot->HasActorBegunPlay());
    Data->SetBoolField(TEXT("assigned_teams_registered"), AssignedTeamsValid);
    Data->SetNumberField(TEXT("human_team"), HumanTeam);
    Data->SetNumberField(TEXT("rival_team"), RivalTeam);
    Data->SetNumberField(TEXT("bot_team"), State ? State->GetGenericTeamId().GetId() : -1);
    Data->SetStringField(TEXT("game_mode_class"), ModeValid ? Mode->GetClass()->GetName() : TEXT("none"));
    Data->SetStringField(TEXT("controller_class"), BotValid ? Bot->GetClass()->GetName() : TEXT("none"));
    Data->SetStringField(TEXT("player_state_class"), IsValid(State) ? State->GetClass()->GetName() : TEXT("none"));
    TArray<TSharedPtr<FJsonValue>> IDs;
    for (int32 ID : TeamIDs) IDs.Add(MakeShared<FJsonValueNumber>(ID));
    Data->SetArrayField(TEXT("registered_team_ids"), IDs);
    FString Json;
    FJsonSerializer::Serialize(Data, TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Json));
    FFileHelper::SaveStringToFile(Json + TEXT("\n"), *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
        &IFileManager::Get(), FILEWRITE_Append);
}
}

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
    auto* Teams = GetWorld()->GetSubsystem<ULyraTeamSubsystem>();
    auto* Human = GetWorld()->GetGameInstance()->GetFirstLocalPlayerController();
    auto* HumanState = Human ? Human->GetPlayerState<ALyraPlayerState>() : nullptr;
    const TArray<int32> TeamIDs = Teams ? Teams->GetTeamIDs() : TArray<int32>();
    HumanTeam = HumanState ? HumanState->GetGenericTeamId().GetId() : INDEX_NONE;
    RivalTeam = NovanodeTraining::SelectRivalTeam(TeamIDs.GetData(), TeamIDs.Num(), HumanTeam);
    if (!HumanState || RivalTeam == INDEX_NONE)
    {
        InitializationDiagnostic(TEXT("invalid_native_team_configuration"), Mode, nullptr, HumanTeam, RivalTeam, TeamIDs, false);
        UE_LOG(LogTemp, Error, TEXT("NovanodeTraining requires two registered teams and a natively assigned human team"));
        return;
    }
    if (auto* Session = GetWorld()->GetGameInstance()->GetSubsystem<UTrainingLobbySubsystem>())
        Session->NativeMatchStarted();
    auto* Components = GetWorld()->GetGameInstance()->GetSubsystem<UGameFrameworkComponentManager>();
    PawnReadyHandle = Components->RegisterAndCallForClassInitState(APawn::StaticClass(), ULyraHeroComponent::NAME_ActorFeatureName,
        FGameplayTag::RequestGameplayTag(TEXT("InitState.GameplayReady")),
        FActorInitStateChangedDelegate::CreateUObject(this, &ThisClass::PawnReady), true);
    for (int32 Index = 0; Index < 3; ++Index)
    {
        FActorSpawnParameters Parameters;
        Parameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        AAIController* Bot = GetWorld()->SpawnActor<AAIController>(BotControllerClass, FVector::ZeroVector, FRotator::ZeroRotator, Parameters);
        if (!Bot) continue;
        Bots.Add(Bot);
        bool AssignedTeamsValid = true;
        for (APlayerState* PlayerState : GetGameState<AGameStateBase>()->PlayerArray)
            if (auto* Player = Cast<ALyraPlayerState>(PlayerState))
            {
                const int32 Team = Player->GetGenericTeamId().GetId();
                AssignedTeamsValid &= Team == FGenericTeamId::NoTeam.GetId() || TeamIDs.Contains(Team);
            }
        InitializationDiagnostic(TEXT("pre_generic"), Mode, Bot, HumanTeam, RivalTeam, TeamIDs, AssignedTeamsValid);
        auto* BotState = Bot->GetPlayerState<ALyraPlayerState>();
        if (!IsValid(Mode) || !IsValid(Bot) || !IsValid(BotState) ||
            Mode->IsActorBeingDestroyed() || Bot->IsActorBeingDestroyed() || BotState->IsActorBeingDestroyed() ||
            !Mode->HasAuthority() || !Bot->HasAuthority() || BotState->GetWorld() != Mode->GetWorld() ||
            Bot->GetWorld() != Mode->GetWorld() || !AssignedTeamsValid)
        {
            UE_LOG(LogTemp, Error, TEXT("NovanodeTraining native initialization prerequisite rejected"));
            return;
        }
        Mode->GenericPlayerInitialization(Bot);
        InitializationDiagnostic(TEXT("post_generic"), Mode, Bot, HumanTeam, RivalTeam, TeamIDs, true);
        if (auto* State = Bot->GetPlayerState<ALyraPlayerState>()) State->SetGenericTeamId(FGenericTeamId(RivalTeam));
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
        // Preserve the registered team chosen by Lyra's high-priority team initialization.
        UnbindInput();
        auto* Session = GetWorld()->GetGameInstance()->GetSubsystem<UTrainingLobbySubsystem>();
        if ((!Session || !Session->UsesNativeFrontend()) && Player->IsLocalController() && MenuAction && MenuMapping)
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
    NovanodeTraining::MatchEvidence Evidence;
    Evidence.HumanTeam = HumanTeam;
    Evidence.RivalTeam = RivalTeam;
    Evidence.OwnedBots = Bots.Num();
    for (const auto& Bot : Bots)
        if (Bot.IsValid() && Bot->GetPawn() && ReadyPawns.Contains(Bot->GetPawn()))
        {
            ++Evidence.ReadyBots;
            if (auto* State = Bot->GetPlayerState<ALyraPlayerState>())
                if (State->GetGenericTeamId() == FGenericTeamId(RivalTeam)) ++Evidence.RivalBots;
        }
    for (APlayerState* State : GetGameState<AGameStateBase>()->PlayerArray)
        if (State && State->IsABot()) ++Evidence.TotalBots;
    TArray<UTrainingMatchComponent*> MatchComponents;
    GetGameState<AGameStateBase>()->GetComponents<UTrainingMatchComponent>(MatchComponents);
    Evidence.MatchComponents = MatchComponents.Num();
    auto* State = Human ? Human->GetPlayerState<ALyraPlayerState>() : nullptr;
    Evidence.HumanReady = Human && Human->GetPawn() && ReadyPawns.Contains(Human->GetPawn()) &&
        State && State->GetGenericTeamId().GetId() == HumanTeam;
    if (auto* Session = GetWorld()->GetGameInstance()->GetSubsystem<UTrainingLobbySubsystem>())
        Session->MatchReady(Evidence);
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
    PawnReadyHandle.Reset();
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
    int32 RemainingBots = 0;
    for (const auto& Bot : Bots) if (Bot.IsValid()) ++RemainingBots;
    if (auto* Session = GetWorld()->GetGameInstance()->GetSubsystem<UTrainingLobbySubsystem>())
        Session->MatchEnded(bStarted && Bots.Num() == 3 && RemainingBots == 0 &&
            !PawnReadyHandle.IsValid() && !BoundInput.IsValid() && InputHandle == 0);
    Bots.Reset();
    ReadyPawns.Reset();
    bStarted = false;
    Super::EndPlay(Reason);
}
