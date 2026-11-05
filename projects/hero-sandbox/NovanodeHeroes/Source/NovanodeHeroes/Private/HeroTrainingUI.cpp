#include "HeroTraining.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystem/Attributes/LyraHealthSet.h"
#include "Blueprint/WidgetTree.h"
#include "CommonUIExtensions.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Engine/AssetManager.h"
#include "Engine/GameInstance.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "GenericTeamAgentInterface.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "NativeGameplayTags.h"
#include "PrimaryGameLayout.h"
#include "GameModes/LyraExperienceDefinition.h"

UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingMenuLayer, "UI.Layer.Menu");

namespace
{
constexpr const TCHAR* TrainingRoot = TEXT("/NovanodeHeroes/TrainingV3");
constexpr const TCHAR* FrontendMap = TEXT("/Game/System/FrontEnd/Maps/L_LyraFrontEnd");
constexpr const TCHAR* TrainingMap = TEXT("/ShooterCore/Maps/L_ShooterGym");

bool IsFrontend(const UWorld* World)
{
    return World && World->GetOutermost()->GetName() == FrontendMap;
}

int32 OpposingBots(const UWorld* World)
{
    int32 Count = 0;
    const AGameStateBase* State = World ? World->GetGameState() : nullptr;
    if (!State) return Count;
    for (const APlayerState* Player : State->PlayerArray)
    {
        const IGenericTeamAgentInterface* Team = Cast<IGenericTeamAgentInterface>(Player);
        if (Player && Player->IsABot() && Team && Team->GetGenericTeamId() == FGenericTeamId(1)) ++Count;
    }
    return Count;
}

void Visible(UWidget* Widget, bool Show)
{
    if (Widget) Widget->SetVisibility(Show ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
}
}

bool UHeroTrainingData::IsComplete() const
{
    if (!TargetMesh || SwordMontages.Num() != 3 || !CastMontage || !DashMontage ||
        !SwordEquipment || !MageEquipment || AttackSlot.IsNone() || !FMath::IsFinite(SwordLengthCm) ||
        SwordLengthCm < 80.f || SwordLengthCm > 160.f) return false;
    for (const UAnimMontage* Montage : SwordMontages) if (!Montage) return false;
    return true;
}

void UHeroTrainingSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    bEnabled = !IsRunningCommandlet() && FParse::Param(FCommandLine::Get(), TEXT("HeroTrainingV3"));
    if (!bEnabled) return;
    UAssetManager::CallOrRegister_OnCompletedInitialScan(
        FSimpleMulticastDelegate::FDelegate::CreateUObject(this, &UHeroTrainingSubsystem::RegisterExperience));
}

void UHeroTrainingSubsystem::RegisterExperience()
{
    if (!bEnabled || bExperienceRegistered) return;
    UAssetManager::Get().ScanPathForPrimaryAssets(FPrimaryAssetType(TEXT("LyraExperienceDefinition")),
        TrainingRoot, ULyraExperienceDefinition::StaticClass(), true, false, true);
    Data = LoadObject<UHeroTrainingData>(nullptr, TEXT("/NovanodeHeroes/TrainingV3/DA_HeroTraining_v3.DA_HeroTraining_v3"));
    bExperienceRegistered = Data && Data->IsComplete();
}

void UHeroTrainingSubsystem::Deinitialize()
{
    if (Menu) { Menu->DeactivateWidget(); Menu->RemoveFromParent(); }
    if (HUD) HUD->RemoveFromParent();
    Menu = nullptr;
    HUD = nullptr;
    Data = nullptr;
    bEnabled = false;
    Super::Deinitialize();
}

bool UHeroTrainingSubsystem::IsTickable() const { return bEnabled && !IsTemplate(); }
TStatId UHeroTrainingSubsystem::GetStatId() const { RETURN_QUICK_DECLARE_CYCLE_STAT(HeroTrainingSubsystem, STATGROUP_Tickables); }

bool UHeroTrainingSubsystem::IsTrainingWorld() const
{
    const UWorld* World = GetWorld();
    return bEnabled && World && World->GetNetMode() == NM_Standalone &&
        World->GetOutermost()->GetName() == TrainingMap &&
        FString(World->URL.GetOption(TEXT("Experience="), TEXT(""))) == TEXT("B_HeroTraining_v3");
}

void UHeroTrainingSubsystem::Tick(float)
{
    UWorld* World = GetWorld();
    if (!World || !World->IsGameWorld() || World->GetNetMode() != NM_Standalone) return;
    if (ObservedWorld.Get() != World)
    {
        if (Menu) { Menu->DeactivateWidget(); Menu->RemoveFromParent(); }
        if (HUD) HUD->RemoveFromParent();
        Menu = nullptr;
        HUD = nullptr;
        ObservedWorld = World;
        bDismissed = false;
    }
    if (IsFrontend(World))
    {
        Flow.ArriveAtLobby();
        if (!bDismissed) ShowMenu();
    }
    else if (IsTrainingWorld())
    {
        APlayerController* Player = UGameplayStatics::GetPlayerController(World, 0);
        APawn* Pawn = Player ? Player->GetPawn() : nullptr;
        UHeroTrainingComponent* Combat = Pawn ? Pawn->FindComponentByClass<UHeroTrainingComponent>() : nullptr;
        Flow.MatchReady(Combat && Combat->IsReady(), OpposingBots(World));
        if (Player && !HUD)
        {
            HUD = CreateWidget<UHeroTrainingHUD>(Player, UHeroTrainingHUD::StaticClass());
            if (HUD) { HUD->AddToPlayerScreen(30); HUD->SetVisibility(ESlateVisibility::HitTestInvisible); }
        }
        if (Flow.Screen == NovanodeHeroes::TrainingScreen::Paused) ShowMenu();
    }
    RefreshMenu();
}

void UHeroTrainingSubsystem::ShowMenu()
{
    if (Menu && Menu->IsActivated()) return;
    ULocalPlayer* Local = GetGameInstance()->GetFirstGamePlayer();
    if (!Local || !UPrimaryGameLayout::GetPrimaryGameLayout(Local)) return;
    Menu = Cast<UHeroTrainingMenu>(UCommonUIExtensions::PushContentToLayer_ForPlayer(
        Local, TAG_TrainingMenuLayer, UHeroTrainingMenu::StaticClass()));
    RefreshMenu();
}

void UHeroTrainingSubsystem::RefreshMenu() { if (Menu) Menu->Refresh(); }
void UHeroTrainingSubsystem::OpenTraining() { if (Flow.OpenTraining()) RefreshMenu(); }
void UHeroTrainingSubsystem::ChooseHero(bool Mage)
{
    Flow.Choose(Mage ? NovanodeHeroes::TrainingHero::Mage : NovanodeHeroes::TrainingHero::Melee);
    RefreshMenu();
}

bool UHeroTrainingSubsystem::StartTraining()
{
    if (!GetWorld() || GetWorld()->GetNetMode() != NM_Standalone ||
        !Flow.Start(bExperienceRegistered && Data && Data->IsComplete())) return false;
    if (Menu) Menu->DeactivateWidget();
    UGameplayStatics::OpenLevel(this, FName(TrainingMap), true, TEXT("Experience=B_HeroTraining_v3?NumBots=3"));
    return true;
}

void UHeroTrainingSubsystem::TogglePause()
{
    if (!IsTrainingWorld()) return;
    if (Flow.Resume())
    {
        UGameplayStatics::SetGamePaused(this, false);
        if (Menu) Menu->DeactivateWidget();
        return;
    }
    if (Flow.Pause()) { UGameplayStatics::SetGamePaused(this, true); ShowMenu(); }
}

void UHeroTrainingSubsystem::ReturnToLobby()
{
    if (!IsTrainingWorld() || !Flow.Return()) return;
    UGameplayStatics::SetGamePaused(this, false);
    if (Menu) Menu->DeactivateWidget();
    UGameplayStatics::OpenLevel(this, FName(FrontendMap), true);
}

void UHeroTrainingSubsystem::Back()
{
    if (Flow.BackFromSelection()) RefreshMenu();
    else if (Flow.Screen == NovanodeHeroes::TrainingScreen::Paused) TogglePause();
}

void UHeroTrainingSubsystem::ShowOriginalModes()
{
    if (!IsFrontend(GetWorld()) || Flow.Screen != NovanodeHeroes::TrainingScreen::Lobby) return;
    bDismissed = true;
    if (Menu) Menu->DeactivateWidget();
}

FString UHeroTrainingSubsystem::GetStatusText() const
{
    if (!Data || !Data->IsComplete()) return TEXT("Training assets are not ready. Preparation/validation is required.");
    const TCHAR* Hero = IsMage() ? TEXT("MAGE") : TEXT("MELEE");
    if (IsTrainingWorld())
    {
        APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0);
        UAbilitySystemComponent* ASC = Pawn ? UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Pawn) : nullptr;
        const float Health = ASC ? ASC->GetNumericAttribute(ULyraHealthSet::GetHealthAttribute()) : 0.f;
        UHeroTrainingComponent* Combat = Pawn ? Pawn->FindComponentByClass<UHeroTrainingComponent>() : nullptr;
        return FString::Printf(TEXT("HERO TRAINING | %s | HP %.0f | opposing bots %d / 3\nAttack CD %.1fs | Dash CD %.1fs\nLMB / J: attack   Q / K: sword dash   Tab / Esc: menu\n%s"),
            Hero, Health, OpposingBots(GetWorld()), Combat ? Combat->GetCooldownRemaining(false) : 0.f,
            Combat ? Combat->GetCooldownRemaining(true) : 0.f, Flow.Screen == NovanodeHeroes::TrainingScreen::Loading ?
            TEXT("Waiting for the Lyra pawn and three opposing bots...") : TEXT("Local training — visual/feel review pending"));
    }
    if (Flow.Screen == NovanodeHeroes::TrainingScreen::HeroSelection)
        return Flow.HasSelection ? FString::Printf(TEXT("Selected: %s\nThree stock Lyra bots. Native health, damage and respawn."), Hero) :
            TEXT("Choose Melee or Mage, then Start Training.\nMage currently uses a provisional throw-style casting animation.");
    return TEXT("Local Lyra 5.8 training. Original Lyra modes remain available.");
}

UHeroTrainingMenu::UHeroTrainingMenu(const FObjectInitializer& Initializer) : Super(Initializer)
{
    bIsBackHandler = true;
    bIsModal = true;
}

UHeroTrainingSubsystem* UHeroTrainingMenu::Training() const
{
    return GetGameInstance() ? GetGameInstance()->GetSubsystem<UHeroTrainingSubsystem>() : nullptr;
}

UButton* UHeroTrainingMenu::AddButton(UVerticalBox* Panel, const TCHAR* Label, FName Callback)
{
    UButton* Button = WidgetTree->ConstructWidget<UButton>();
    UTextBlock* Text = WidgetTree->ConstructWidget<UTextBlock>();
    Text->SetText(FText::FromString(Label));
    Text->SetColorAndOpacity(FSlateColor(FLinearColor(.04f, .05f, .08f)));
    Text->SetMargin(FMargin(16.f, 10.f));
    Button->AddChild(Text);
    FScriptDelegate Delegate;
    Delegate.BindUFunction(this, Callback);
    Button->OnClicked.Add(Delegate);
    Panel->AddChildToVerticalBox(Button)->SetPadding(FMargin(0.f, 4.f));
    return Button;
}

TSharedRef<SWidget> UHeroTrainingMenu::RebuildWidget()
{
    if (!WidgetTree->RootWidget)
    {
        UBorder* Background = WidgetTree->ConstructWidget<UBorder>();
        Background->SetBrushColor(FLinearColor(.015f, .025f, .05f, .98f));
        Background->SetPadding(FMargin(48.f));
        Background->SetHorizontalAlignment(HAlign_Center);
        Background->SetVerticalAlignment(VAlign_Center);
        UVerticalBox* Panel = WidgetTree->ConstructWidget<UVerticalBox>();
        Background->AddChild(Panel);
        WidgetTree->RootWidget = Background;
        Title = WidgetTree->ConstructWidget<UTextBlock>();
        Title->SetText(FText::FromString(TEXT("NOVANODE — LYRA 5.8")));
        Panel->AddChildToVerticalBox(Title)->SetPadding(FMargin(0.f, 0.f, 0.f, 20.f));
        Status = WidgetTree->ConstructWidget<UTextBlock>();
        Status->SetAutoWrapText(true);
        Panel->AddChildToVerticalBox(Status)->SetPadding(FMargin(0.f, 0.f, 0.f, 20.f));
        TrainingButton = AddButton(Panel, TEXT("Hero Training"), GET_FUNCTION_NAME_CHECKED(UHeroTrainingMenu, OpenTraining));
        MeleeButton = AddButton(Panel, TEXT("Choose Melee — sword combo and dash"), GET_FUNCTION_NAME_CHECKED(UHeroTrainingMenu, ChooseMelee));
        MageButton = AddButton(Panel, TEXT("Choose Mage — arcane projectile"), GET_FUNCTION_NAME_CHECKED(UHeroTrainingMenu, ChooseMage));
        StartButton = AddButton(Panel, TEXT("Start Training — 3 bots"), GET_FUNCTION_NAME_CHECKED(UHeroTrainingMenu, Start));
        ResumeButton = AddButton(Panel, TEXT("Resume Training"), GET_FUNCTION_NAME_CHECKED(UHeroTrainingMenu, Resume));
        ReturnButton = AddButton(Panel, TEXT("Return to Lobby"), GET_FUNCTION_NAME_CHECKED(UHeroTrainingMenu, ReturnToLobby));
        BackButton = AddButton(Panel, TEXT("Back"), GET_FUNCTION_NAME_CHECKED(UHeroTrainingMenu, Back));
        OriginalButton = AddButton(Panel, TEXT("Original Lyra modes"), GET_FUNCTION_NAME_CHECKED(UHeroTrainingMenu, OriginalModes));
    }
    Refresh();
    return Super::RebuildWidget();
}

void UHeroTrainingMenu::Refresh()
{
    UHeroTrainingSubsystem* Session = Training();
    if (!Session || !Title || !Status) return;
    using NovanodeHeroes::TrainingScreen;
    const TrainingScreen Screen = Session->GetFlow().Screen;
    const bool Lobby = Screen == TrainingScreen::Lobby;
    const bool Selection = Screen == TrainingScreen::HeroSelection;
    const bool Paused = Screen == TrainingScreen::Paused;
    Title->SetText(FText::FromString(Lobby ? TEXT("NOVANODE — LYRA 5.8") : Selection ? TEXT("HERO TRAINING — CHOOSE YOUR HERO") : TEXT("HERO TRAINING — PAUSED")));
    Status->SetText(FText::FromString(Session->GetStatusText()));
    Visible(TrainingButton, Lobby);
    Visible(OriginalButton, Lobby);
    Visible(MeleeButton, Selection);
    Visible(MageButton, Selection);
    Visible(StartButton, Selection);
    Visible(BackButton, Selection);
    Visible(ResumeButton, Paused);
    Visible(ReturnButton, Paused);
    StartButton->SetIsEnabled(Selection && Session->GetFlow().HasSelection && Session->GetData() && Session->GetData()->IsComplete());
}

TOptional<FUIInputConfig> UHeroTrainingMenu::GetDesiredInputConfig() const
{
    return FUIInputConfig(ECommonInputMode::Menu, EMouseCaptureMode::NoCapture);
}

UWidget* UHeroTrainingMenu::NativeGetDesiredFocusTarget() const
{
    const UHeroTrainingSubsystem* Session = Training();
    if (!Session) return nullptr;
    using NovanodeHeroes::TrainingScreen;
    return Session->GetFlow().Screen == TrainingScreen::Lobby ? TrainingButton.Get() :
        Session->GetFlow().Screen == TrainingScreen::Paused ? ResumeButton.Get() : MeleeButton.Get();
}

bool UHeroTrainingMenu::NativeOnHandleBackAction() { Back(); return true; }
void UHeroTrainingMenu::OpenTraining() { if (Training()) Training()->OpenTraining(); }
void UHeroTrainingMenu::ChooseMelee() { if (Training()) Training()->ChooseHero(false); }
void UHeroTrainingMenu::ChooseMage() { if (Training()) Training()->ChooseHero(true); }
void UHeroTrainingMenu::Start() { if (Training()) Training()->StartTraining(); }
void UHeroTrainingMenu::Resume() { if (Training()) Training()->TogglePause(); }
void UHeroTrainingMenu::ReturnToLobby() { if (Training()) Training()->ReturnToLobby(); }
void UHeroTrainingMenu::Back() { if (Training()) Training()->Back(); }
void UHeroTrainingMenu::OriginalModes() { if (Training()) Training()->ShowOriginalModes(); }

TSharedRef<SWidget> UHeroTrainingHUD::RebuildWidget()
{
    if (!WidgetTree->RootWidget)
    {
        UVerticalBox* Panel = WidgetTree->ConstructWidget<UVerticalBox>();
        Status = WidgetTree->ConstructWidget<UTextBlock>();
        Status->SetColorAndOpacity(FSlateColor(FLinearColor(.3f, .9f, 1.f)));
        Panel->AddChildToVerticalBox(Status)->SetPadding(FMargin(25.f, 18.f));
        WidgetTree->RootWidget = Panel;
    }
    return Super::RebuildWidget();
}

void UHeroTrainingHUD::NativeTick(const FGeometry& Geometry, float Delta)
{
    Super::NativeTick(Geometry, Delta);
    UHeroTrainingSubsystem* Session = GetGameInstance() ? GetGameInstance()->GetSubsystem<UHeroTrainingSubsystem>() : nullptr;
    if (Status && Session) Status->SetText(FText::FromString(Session->GetStatusText()));
}
