#include "TrainingLobby.h"

#include "TrainingReflectionAdapter.h"
#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystem/LyraAbilitySystemComponent.h"
#include "Blueprint/WidgetTree.h"
#include "CommonSessionSubsystem.h"
#include "CommonUIExtensions.h"
#include "CommonUserTypes.h"
#include "Components/Border.h"
#include "CommonButtonBase.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Engine/GameInstance.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "NativeGameplayTags.h"
#include "TimerManager.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/UObjectIterator.h"

UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingMenu, "UI.Layer.Menu");

namespace
{
ULyraAbilitySystemComponent* AbilitySystem(APawn* Pawn)
{
    return Pawn ? Cast<ULyraAbilitySystemComponent>(UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Pawn)) : nullptr;
}
}

void UTrainingLobbySubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    Collection.InitializeDependency<UCommonSessionSubsystem>();
    bNativeFrontend = FParse::Param(FCommandLine::Get(), TEXT("NovanodeNativeFrontend"));
    if (bNativeFrontend)
    {
        NativeDefinition = UTrainingReflectionAdapter::ConfigureNativeFrontendDefinition();
        if (!NativeDefinition) UE_LOG(LogTemp, Error, TEXT("NovanodeTraining native experience metadata schema failed"));
    }
    FParse::Value(FCommandLine::Get(), TEXT("NovanodeTrainingProbe="), ProbePath);
    if (!ProbePath.IsEmpty())
        ProbeWorldHandle = FWorldDelegates::OnPostWorldInitialization.AddUObject(this, &ThisClass::ProbeWorldInitialized);
}

void UTrainingLobbySubsystem::ProbeWorldInitialized(UWorld* World, const UWorld::InitializationValues)
{
    if (!World || !World->IsGameWorld() || World->GetGameInstance() != GetGameInstance()) return;
    FTimerHandle Deadline;
    World->GetTimerManager().SetTimer(Deadline, FTimerDelegate::CreateWeakLambda(this,
        [this]() { WriteProbe(false, TEXT("lifecycle_deadline")); }), 120.f, false);
    if (bNativeFrontend)
    {
        FTimerHandle Driver;
        World->GetTimerManager().SetTimer(Driver, FTimerDelegate::CreateWeakLambda(this,
            [this]() { NativeProbeStep(); }), .1f, true);
    }
}

void UTrainingLobbySubsystem::Deinitialize()
{
    ReleaseNativeSelectionPause();
    SetMenuBlocking(false);
    FWorldDelegates::OnPostWorldInitialization.Remove(ProbeWorldHandle);
    if (auto* Sessions = GetGameInstance()->GetSubsystem<UCommonSessionSubsystem>())
        Sessions->OnCreateSessionCompleteEvent.Remove(HostHandle);
    if (PauseScreen.IsValid()) PauseScreen->DeactivateWidget();
    PauseScreen.Reset();
    OnChanged.Clear();
    Super::Deinitialize();
}

void UTrainingLobbySubsystem::LobbyActivated()
{
    if (!Flow.ArriveAtLobby()) return;
    if (auto* Sessions = GetGameInstance()->GetSubsystem<UCommonSessionSubsystem>())
        Sessions->OnCreateSessionCompleteEvent.Remove(HostHandle);
    HostHandle.Reset();
    Status = TEXT("Local training. Choose a hero. Original Lyra modes remain available.");
    Refresh();
    // Opt-in unattended driver calls the same UI/session operations, never direct travel.
    if (!ProbePath.IsEmpty())
    {
        ++ProbeEvidence.LobbyArrivals;
        if (ProbeMatches == 2)
        {
            GetWorld()->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this,
                [this]() { WriteProbe(ProbeEvidence.Complete(), TEXT("two_matches_and_cleanup_verified")); }));
            return;
        }
        if (!OpenSelection() || !Choose(ProbeMatches != 0) || !Host()) WriteProbe(false, TEXT("host_rejected"));
    }
}

bool UTrainingLobbySubsystem::OpenSelection()
{
    if (!Flow.OpenSelection()) return false;
    Refresh();
    return true;
}

bool UTrainingLobbySubsystem::Choose(bool Mage)
{
    const auto Hero = Mage ? NovanodeTraining::Hero::Mage : NovanodeTraining::Hero::Melee;
    if (bNativeChoosing) Flow.Selected = Hero;
    else if (!Flow.Choose(Hero)) return false;
    Status = Mage ? TEXT("Mage selected. Combat/animation evolution is a separate gate.") :
        TEXT("Melee selected. Combat/animation evolution is a separate gate.");
    Refresh();
    return true;
}

bool UTrainingLobbySubsystem::Host()
{
    if (bNativeChoosing)
    {
        if (Flow.State != NovanodeTraining::Screen::Match || Flow.Selected == NovanodeTraining::Hero::None) return false;
        bNativeChoosing = false;
        ReleaseNativeSelectionPause();
        SetMenuBlocking(false);
        return true; // Native CommonSession already hosted this experience; never host twice.
    }
    if (!GetWorld() || GetWorld()->GetNetMode() != NM_Standalone ||
        Flow.State != NovanodeTraining::Screen::Selection || Flow.Selected == NovanodeTraining::Hero::None) return false;
    auto* Sessions = GetGameInstance()->GetSubsystem<UCommonSessionSubsystem>();
    APlayerController* Player = GetGameInstance()->GetFirstLocalPlayerController();
    UObject* Definition = LoadObject<UObject>(nullptr, TEXT("/NovanodeTraining/Experiences/DA_HeroTraining.DA_HeroTraining"));
    UCommonSession_HostSessionRequest* Request = UTrainingReflectionAdapter::CreateOfflineRequest(Definition, this);
    if (!Sessions || !Player || !Request || !Flow.BeginHosting())
    {
        Status = TEXT("Cannot host: native definition/schema or local player is not ready.");
        Refresh();
        return false;
    }
    Request->ExtraArgs.Add(TEXT("TrainingHero"), Flow.Selected == NovanodeTraining::Hero::Mage ? TEXT("Mage") : TEXT("Melee"));
    Sessions->OnCreateSessionCompleteEvent.Remove(HostHandle);
    HostHandle = Sessions->OnCreateSessionCompleteEvent.AddUObject(this, &ThisClass::HostComplete);
    Status = TEXT("Starting local training...");
    Refresh();
    Sessions->HostSession(Player, Request);
    return true;
}

void UTrainingLobbySubsystem::HostComplete(const FOnlineResultInformation& Result)
{
    if (auto* Sessions = GetGameInstance()->GetSubsystem<UCommonSessionSubsystem>())
        Sessions->OnCreateSessionCompleteEvent.Remove(HostHandle);
    HostHandle.Reset();
    if (!Result.bWasSuccessful)
    {
        Flow.HostFailed();
        Status = TEXT("Local session creation failed. Select a hero to try again explicitly.");
        Refresh();
        if (!ProbePath.IsEmpty()) WriteProbe(false, TEXT("session_creation_failed"));
    }
}

void UTrainingLobbySubsystem::MatchReady(const NovanodeTraining::MatchEvidence& Evidence)
{
    if (!Evidence.Valid() || !Flow.MatchReady(Evidence.HumanReady, Evidence.RivalBots)) return;
    if (bNativeFrontend)
    {
        bNativeChoosing = true;
        if (ProbePath.IsEmpty())
        {
            if (!GetWorld()->IsPaused())
                if (auto* Player = GetGameInstance()->GetFirstLocalPlayerController())
                    if (Player->SetPause(true)) NativePausedWorld = GetWorld();
            UClass* Widget = LoadClass<UTrainingScreen>(nullptr, TEXT("/NovanodeTraining/UI/W_HeroSelection.W_HeroSelection_C"));
            NativeSelection = Cast<UTrainingScreen>(UCommonUIExtensions::PushContentToLayer_ForPlayer(
                GetGameInstance()->GetFirstGamePlayer(), TAG_TrainingMenu, Widget));
            if (!NativeSelection.IsValid()) UE_LOG(LogTemp, Error, TEXT("NovanodeTraining native hero selection failed"));
            return;
        }
        if (!Choose(ProbeMatches != 0) || !Host()) { WriteProbe(false, TEXT("native_hero_selection_rejected")); return; }
    }
    SetMenuBlocking(false);
    Status = TEXT("Local training ready — 3 rivals. Esc: menu. Visual/feel approval pending.");
    Refresh();
    if (!ProbePath.IsEmpty())
    {
        if (ProbeMatches >= 2) { WriteProbe(false, TEXT("duplicate_ready_match")); return; }
        ProbeEvidence.Matches[ProbeMatches] = Evidence;
        ++ProbeMatches;
        ProbeEvidence.ReadyMatches = ProbeMatches;
        const FString Progress = FString::Printf(TEXT("{\"passed\":false,\"reason\":\"match_ready_pending_next_frame\",\"ready_matches\":%d,\"generation\":%u,\"visual_verified\":false}"),
            ProbeMatches, Flow.MatchGeneration);
        FFileHelper::SaveStringToFile(Progress, *ProbePath);
        // Pawn-ready may run inside experience/bot construction. Never tear down that world on its stack.
        GetWorld()->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this, [this]()
        {
            ReturnToLobby();
        }));
    }
}

void UTrainingLobbySubsystem::MatchEnded(bool Clean)
{
    if (bNativeFrontend)
    {
        ReleaseNativeSelectionPause();
        bNativeChoosing = false;
        if (NativeSelection.IsValid()) NativeSelection->DeactivateWidget();
        NativeSelection.Reset();
        Flow.Return();
    }
    if (ProbePath.IsEmpty()) return;
    ++ProbeEvidence.Cleanups;
    ProbeEvidence.CleanupValid &= Clean;
}

void UTrainingLobbySubsystem::ReturnToLobby()
{
    if (!Flow.Return()) return;
    if (!ProbePath.IsEmpty()) ++ProbeEvidence.NativeReturns;
    Resume();
    SetMenuBlocking(false);
    if (auto* Sessions = GetGameInstance()->GetSubsystem<UCommonSessionSubsystem>())
    {
        Sessions->OnCreateSessionCompleteEvent.Remove(HostHandle);
        Sessions->CleanUpSessions();
    }
    HostHandle.Reset();
    // Lyra/CommonGame's native return path; process-local GameDefaultMap is the owned lobby.
    GetGameInstance()->ReturnToMainMenu();
}

void UTrainingLobbySubsystem::OpenPause()
{
    if (Flow.State != NovanodeTraining::Screen::Match || PauseScreen.IsValid()) return;
    UClass* Widget = LoadClass<UTrainingScreen>(nullptr, TEXT("/NovanodeTraining/UI/W_TrainingPause.W_TrainingPause_C"));
    PauseScreen = Cast<UTrainingScreen>(UCommonUIExtensions::PushContentToLayer_ForPlayer(
        GetGameInstance()->GetFirstGamePlayer(), TAG_TrainingMenu, Widget));
}

void UTrainingLobbySubsystem::Resume()
{
    if (PauseScreen.IsValid()) PauseScreen->DeactivateWidget();
    PauseScreen.Reset();
    SetMenuBlocking(false);
}

void UTrainingLobbySubsystem::SetMenuBlocking(bool Block)
{
    const FGameplayTag Tag = FGameplayTag::RequestGameplayTag(TEXT("Gameplay.AbilityInputBlocked"));
    if (bAddedInputBlock)
        if (auto* ASC = AbilitySystem(BlockedPawn.Get())) ASC->RemoveLooseGameplayTag(Tag);
    bAddedInputBlock = false;
    BlockedPawn.Reset();
    bMenuBlocking = Block;
    if (!Block) return;
    APlayerController* Player = GetGameInstance()->GetFirstLocalPlayerController();
    BlockedPawn = Player ? Player->GetPawn() : nullptr;
    if (auto* ASC = AbilitySystem(BlockedPawn.Get()))
    {
        ASC->ClearAbilityInput();
        ASC->CancelInputActivatedAbilities(false);
        ASC->AddLooseGameplayTag(Tag);
        bAddedInputBlock = true;
    }
}

void UTrainingLobbySubsystem::Back() { if (Flow.Back()) Refresh(); }
void UTrainingLobbySubsystem::Refresh() { OnChanged.Broadcast(); }

void UTrainingLobbySubsystem::WriteProbe(bool Passed, const TCHAR* Reason)
{
    Passed &= ProbeEvidence.Complete() && Flow.MatchGeneration == 2;
    if (bNativeFrontend) Passed &= NativeMenuCallbacks == 2 && NativeExperienceCallbacks == 2 &&
        NativeHostCallbacks == 2 && NativeOfflineHostCallbacks == 2;
    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("passed"), Passed);
    Result->SetStringField(TEXT("reason"), Reason);
    Result->SetNumberField(TEXT("ready_matches"), ProbeMatches);
    Result->SetNumberField(TEXT("generation"), Flow.MatchGeneration);
    Result->SetNumberField(TEXT("lobby_arrivals"), ProbeEvidence.LobbyArrivals);
    Result->SetNumberField(TEXT("native_returns"), ProbeEvidence.NativeReturns);
    Result->SetNumberField(TEXT("cleanups"), ProbeEvidence.Cleanups);
    Result->SetBoolField(TEXT("cleanup_valid"), ProbeEvidence.CleanupValid);
    Result->SetBoolField(TEXT("visual_verified"), false);
    Result->SetBoolField(TEXT("native_frontend"), bNativeFrontend);
    Result->SetNumberField(TEXT("native_menu_callbacks"), NativeMenuCallbacks);
    Result->SetNumberField(TEXT("native_experience_callbacks"), NativeExperienceCallbacks);
    Result->SetNumberField(TEXT("native_host_callbacks"), NativeHostCallbacks);
    Result->SetNumberField(TEXT("native_offline_host_callbacks"), NativeOfflineHostCallbacks);
    TArray<TSharedPtr<FJsonValue>> Matches;
    for (int32 Index = 0; Index < FMath::Min(ProbeMatches, 2); ++Index)
    {
        const auto& Match = ProbeEvidence.Matches[Index];
        TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
        Item->SetNumberField(TEXT("total_bots"), Match.TotalBots);
        Item->SetNumberField(TEXT("owned_bots"), Match.OwnedBots);
        Item->SetNumberField(TEXT("ready_bots"), Match.ReadyBots);
        Item->SetNumberField(TEXT("rival_bots"), Match.RivalBots);
        Item->SetNumberField(TEXT("match_components"), Match.MatchComponents);
        Item->SetNumberField(TEXT("human_team"), Match.HumanTeam);
        Item->SetNumberField(TEXT("rival_team"), Match.RivalTeam);
        Item->SetBoolField(TEXT("human_ready"), Match.HumanReady);
        Matches.Add(MakeShared<FJsonValueObject>(Item));
    }
    Result->SetArrayField(TEXT("matches"), Matches);
    FString Json;
    FJsonSerializer::Serialize(Result, TJsonWriterFactory<>::Create(&Json));
    FFileHelper::SaveStringToFile(Json, *ProbePath);
    FPlatformMisc::RequestExitWithStatus(false, Passed ? 0 : 1);
}

UTrainingScreen::UTrainingScreen(const FObjectInitializer& Initializer) : Super(Initializer)
{
    bIsBackHandler = true;
    bIsModal = true;
}

UTrainingLobbySubsystem* UTrainingScreen::Session() const
{
    return GetGameInstance() ? GetGameInstance()->GetSubsystem<UTrainingLobbySubsystem>() : nullptr;
}

UCommonButtonBase* UTrainingScreen::AddButton(UVerticalBox* Panel, const TCHAR* Label, FName Callback)
{
    UClass* ButtonClass = LoadClass<UCommonButtonBase>(nullptr, TEXT("/Game/UI/Menu/W_LyraMenuButton.W_LyraMenuButton_C"));
    UCommonButtonBase* Button = ButtonClass ? CreateWidget<UCommonButtonBase>(GetOwningPlayer(), ButtonClass) : nullptr;
    if (!Button || !UTrainingReflectionAdapter::SetNativeButtonLabel(Button, FText::FromString(Label)))
    {
        UE_LOG(LogTemp, Error, TEXT("NovanodeTraining native button schema failed"));
        return nullptr;
    }
    FSimpleDelegate Delegate;
    Delegate.BindUFunction(this, Callback);
    Button->OnClicked().Add(Delegate);
    Panel->AddChildToVerticalBox(Button)->SetPadding(FMargin(0.f, 5.f));
    return Button;
}

TSharedRef<SWidget> UTrainingScreen::RebuildWidget()
{
    if (!WidgetTree->RootWidget)
    {
        UBorder* Background = WidgetTree->ConstructWidget<UBorder>();
        Background->SetBrushColor(FLinearColor(.012f, .025f, .05f, .98f));
        Background->SetPadding(FMargin(48.f));
        Background->SetHorizontalAlignment(HAlign_Center);
        Background->SetVerticalAlignment(VAlign_Center);
        UVerticalBox* Panel = WidgetTree->ConstructWidget<UVerticalBox>();
        Background->AddChild(Panel);
        WidgetTree->RootWidget = Background;
        UTextBlock* Title = WidgetTree->ConstructWidget<UTextBlock>();
        Title->SetText(FText::FromString(Screen == ETrainingScreen::Lobby ? TEXT("NOVANODE / LOCAL LOBBY") :
            Screen == ETrainingScreen::Selection ? TEXT("HERO TRAINING / SELECT HERO") : TEXT("HERO TRAINING / MENU")));
        Panel->AddChildToVerticalBox(Title)->SetPadding(FMargin(0.f, 0.f, 0.f, 20.f));
        Status = WidgetTree->ConstructWidget<UTextBlock>();
        Status->SetAutoWrapText(true);
        Panel->AddChildToVerticalBox(Status)->SetPadding(FMargin(0.f, 0.f, 0.f, 20.f));
        if (Screen == ETrainingScreen::Lobby)
        {
            PrimaryButton = AddButton(Panel, TEXT("Hero Training"), GET_FUNCTION_NAME_CHECKED(ThisClass, Training));
            AddButton(Panel, TEXT("Original Lyra modes"), GET_FUNCTION_NAME_CHECKED(ThisClass, Original));
        }
        else if (Screen == ETrainingScreen::Selection)
        {
            PrimaryButton = AddButton(Panel, TEXT("Melee"), GET_FUNCTION_NAME_CHECKED(ThisClass, Melee));
            AddButton(Panel, TEXT("Mage"), GET_FUNCTION_NAME_CHECKED(ThisClass, Mage));
            StartButton = AddButton(Panel, TEXT("Start — 3 rivals / Offline"), GET_FUNCTION_NAME_CHECKED(ThisClass, Start));
            AddButton(Panel, TEXT("Back"), GET_FUNCTION_NAME_CHECKED(ThisClass, Back));
        }
        else
        {
            PrimaryButton = AddButton(Panel, TEXT("Resume"), GET_FUNCTION_NAME_CHECKED(ThisClass, Resume));
            AddButton(Panel, TEXT("Return to lobby"), GET_FUNCTION_NAME_CHECKED(ThisClass, Return));
        }
    }
    Refresh();
    return Super::RebuildWidget();
}

void UTrainingScreen::NativeOnActivated()
{
    Super::NativeOnActivated();
    if (auto* S = Session())
    {
        S->OnChanged.Remove(ChangeHandle);
        ChangeHandle = S->OnChanged.AddUObject(this, &ThisClass::Refresh);
        S->SetMenuBlocking(true);
        if (Screen == ETrainingScreen::Lobby) S->LobbyActivated();
    }
    Refresh();
}

void UTrainingScreen::NativeOnDeactivated()
{
    if (auto* S = Session())
    {
        S->OnChanged.Remove(ChangeHandle);
        if (Screen == ETrainingScreen::Pause) S->SetMenuBlocking(false);
    }
    ChangeHandle.Reset();
    Super::NativeOnDeactivated();
}

void UTrainingScreen::Refresh()
{
    if (auto* S = Session())
    {
        if (Status) Status->SetText(FText::FromString(S->GetStatus()));
        if (StartButton) StartButton->SetIsEnabled(S->IsChoosingHero() &&
            S->GetFlow().Selected != NovanodeTraining::Hero::None);
    }
}

TOptional<FUIInputConfig> UTrainingScreen::GetDesiredInputConfig() const
{
    return FUIInputConfig(ECommonInputMode::Menu, EMouseCaptureMode::NoCapture);
}
UWidget* UTrainingScreen::NativeGetDesiredFocusTarget() const { return PrimaryButton; }
bool UTrainingScreen::NativeOnHandleBackAction() { Back(); return true; }
void UTrainingScreen::Training()
{
    if (!Session() || !Session()->OpenSelection()) return;
    UClass* Class = LoadClass<UTrainingScreen>(nullptr, TEXT("/NovanodeTraining/UI/W_HeroSelection.W_HeroSelection_C"));
    if (!UCommonUIExtensions::PushContentToLayer_ForPlayer(GetOwningLocalPlayer(), TAG_TrainingMenu, Class)) Session()->Back();
}
void UTrainingScreen::Melee() { if (Session()) Session()->Choose(false); }
void UTrainingScreen::Mage() { if (Session()) Session()->Choose(true); }
void UTrainingScreen::Start() { if (Session() && Session()->Host()) DeactivateWidget(); }
void UTrainingScreen::Back()
{
    if (Screen == ETrainingScreen::Selection && Session() && Session()->UsesNativeFrontend())
    {
        Session()->ReturnToLobby();
        return;
    }
    if (Screen == ETrainingScreen::Selection) { if (Session()) Session()->Back(); DeactivateWidget(); }
    else if (Screen == ETrainingScreen::Pause) Resume();
}
void UTrainingScreen::Original()
{
    if (UClass* Class = OriginalMainScreen.LoadSynchronous())
        UCommonUIExtensions::PushContentToLayer_ForPlayer(GetOwningLocalPlayer(), TAG_TrainingMenu, Class);
}
void UTrainingScreen::Resume() { if (Session()) Session()->Resume(); }
void UTrainingScreen::Return() { if (Session()) Session()->ReturnToLobby(); }
