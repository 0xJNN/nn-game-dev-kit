#include "TrainingLobby.h"

#include "TrainingReflectionAdapter.h"
#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystem/LyraAbilitySystemComponent.h"
#include "Blueprint/WidgetTree.h"
#include "CommonSessionSubsystem.h"
#include "CommonUIExtensions.h"
#include "CommonUserTypes.h"
#include "Components/Border.h"
#include "Components/Button.h"
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
}

void UTrainingLobbySubsystem::Deinitialize()
{
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
    if (!Flow.Choose(Mage ? NovanodeTraining::Hero::Mage : NovanodeTraining::Hero::Melee)) return false;
    Status = Mage ? TEXT("Mage selected. Combat/animation evolution is a separate gate.") :
        TEXT("Melee selected. Combat/animation evolution is a separate gate.");
    Refresh();
    return true;
}

bool UTrainingLobbySubsystem::Host()
{
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

void UTrainingLobbySubsystem::MatchReady(bool HumanReady, int32 RivalBots)
{
    if (!Flow.MatchReady(HumanReady, RivalBots)) return;
    SetMenuBlocking(false);
    Status = TEXT("Local training ready — 3 rivals. Esc: menu. Visual/feel approval pending.");
    Refresh();
    if (!ProbePath.IsEmpty())
    {
        ++ProbeMatches;
        if (ProbeMatches == 1) ReturnToLobby();
        else WriteProbe(true, TEXT("two_matches_ready"));
    }
}

void UTrainingLobbySubsystem::ReturnToLobby()
{
    if (!Flow.Return()) return;
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
    const FString Json = FString::Printf(TEXT("{\"passed\":%s,\"reason\":\"%s\",\"ready_matches\":%d,\"generation\":%u,\"visual_verified\":false}"),
        Passed ? TEXT("true") : TEXT("false"), Reason, ProbeMatches, Flow.MatchGeneration);
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

UButton* UTrainingScreen::AddButton(UVerticalBox* Panel, const TCHAR* Label, FName Callback)
{
    UButton* Button = WidgetTree->ConstructWidget<UButton>();
    UTextBlock* Text = WidgetTree->ConstructWidget<UTextBlock>();
    Text->SetText(FText::FromString(Label));
    Text->SetColorAndOpacity(FSlateColor(FLinearColor(.025f, .04f, .07f)));
    Text->SetMargin(FMargin(20.f, 12.f));
    Button->AddChild(Text);
    FScriptDelegate Delegate;
    Delegate.BindUFunction(this, Callback);
    Button->OnClicked.Add(Delegate);
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
        if (StartButton) StartButton->SetIsEnabled(S->GetFlow().State == NovanodeTraining::Screen::Selection &&
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
