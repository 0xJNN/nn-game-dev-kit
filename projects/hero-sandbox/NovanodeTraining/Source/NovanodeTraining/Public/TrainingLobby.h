#pragma once

#include "CoreMinimal.h"
#include "CommonActivatableWidget.h"
#include "Components/GameStateComponent.h"
#include "Engine/World.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "TrainingFlow.h"
#include "TrainingLobby.generated.h"

class AAIController;
class UCommonButtonBase;
class UTextBlock;
class UVerticalBox;
class UInputAction;
class UInputMappingContext;
class UEnhancedInputComponent;
class ULyraExperienceDefinition;
struct FActorInitStateChangedParams;
struct FOnlineResultInformation;
class UTrainingScreen;

UCLASS()
class NOVANODETRAINING_API UTrainingLobbySubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
    void LobbyActivated();
    bool OpenSelection();
    bool Choose(bool Mage);
    bool Host();
    bool UsesNativeFrontend() const { return bNativeFrontend; }
    bool IsChoosingHero() const { return bNativeChoosing || Flow.State == NovanodeTraining::Screen::Selection; }
    void NativeMatchStarted();
    void ReturnToLobby();
    void MatchReady(const NovanodeTraining::MatchEvidence& Evidence);
    void MatchEnded(bool Clean);
    void Back();
    void OpenPause();
    void Resume();
    void SetMenuBlocking(bool Block);
    const NovanodeTraining::Flow& GetFlow() const { return Flow; }
    FString GetStatus() const { return Status; }
    FSimpleMulticastDelegate OnChanged;

private:
    void HostComplete(const FOnlineResultInformation& Result);
    void Refresh();
    void WriteProbe(bool Passed, const TCHAR* Reason);
    void ProbeWorldInitialized(UWorld* World, const UWorld::InitializationValues Values);
    void NativeProbeStep();
    void ReleaseNativeSelectionPause();
    NovanodeTraining::Flow Flow;
    FString Status;
    FString ProbePath;
    int32 ProbeMatches = 0;
    NovanodeTraining::LoopEvidence ProbeEvidence;
    FDelegateHandle HostHandle;
    FDelegateHandle ProbeWorldHandle;
    TWeakObjectPtr<UTrainingScreen> PauseScreen;
    TWeakObjectPtr<APawn> BlockedPawn;
    bool bMenuBlocking = false;
    bool bAddedInputBlock = false;
    bool bNativeFrontend = false;
    bool bNativeChoosing = false;
    bool bNativeProbeLobbyVisited = false;
    bool bNativeProbeSelected = false;
    bool bNativeProbeHosted = false;
    bool bNativeProbeConfirmed = false;
    int32 NativeMenuCallbacks = 0;
    int32 NativeExperienceCallbacks = 0;
    int32 NativeHostCallbacks = 0;
    int32 NativeOfflineHostCallbacks = 0;
    TWeakObjectPtr<UWorld> NativePausedWorld;
    TWeakObjectPtr<UTrainingScreen> NativeSelection;
    UPROPERTY(Transient) TObjectPtr<UObject> NativeDefinition;
};

// Instanced only by the owned match experience's AddComponents action.
UCLASS(Blueprintable, meta=(BlueprintSpawnableComponent))
class NOVANODETRAINING_API UTrainingMatchComponent : public UGameStateComponent
{
    GENERATED_BODY()
public:
    UTrainingMatchComponent(const FObjectInitializer& Initializer);
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    UPROPERTY(EditDefaultsOnly) TSubclassOf<AAIController> BotControllerClass;
    UPROPERTY(EditDefaultsOnly) TObjectPtr<UInputAction> MenuAction;
    UPROPERTY(EditDefaultsOnly) TObjectPtr<UInputMappingContext> MenuMapping;
private:
    void ExperienceLoaded(const ULyraExperienceDefinition* Experience);
    void PawnReady(const FActorInitStateChangedParams& Params);
    void CheckReady();
    void Pause();
    void UnbindInput();
    FDelegateHandle PawnReadyHandle;
    TArray<TWeakObjectPtr<AAIController>> Bots;
    TSet<TWeakObjectPtr<APawn>> ReadyPawns;
    TWeakObjectPtr<UEnhancedInputComponent> BoundInput;
    uint32 InputHandle = 0;
    int32 HumanTeam = INDEX_NONE;
    int32 RivalTeam = INDEX_NONE;
    bool bStarted = false;
};

UENUM()
enum class ETrainingScreen : uint8 { Lobby, Selection, Pause };

UCLASS()
class NOVANODETRAINING_API UTrainingScreen : public UCommonActivatableWidget
{
    GENERATED_BODY()
public:
    UTrainingScreen(const FObjectInitializer& Initializer);
    UPROPERTY(EditDefaultsOnly) ETrainingScreen Screen = ETrainingScreen::Lobby;
    UPROPERTY(EditDefaultsOnly) TSoftClassPtr<UCommonActivatableWidget> OriginalMainScreen;
    virtual TOptional<FUIInputConfig> GetDesiredInputConfig() const override;
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
    virtual void NativeOnActivated() override;
    virtual void NativeOnDeactivated() override;
    virtual UWidget* NativeGetDesiredFocusTarget() const override;
    virtual bool NativeOnHandleBackAction() override;
private:
    UTrainingLobbySubsystem* Session() const;
    UCommonButtonBase* AddButton(UVerticalBox* Panel, const TCHAR* Label, FName Callback);
    void Refresh();
    UFUNCTION() void Training();
    UFUNCTION() void Melee();
    UFUNCTION() void Mage();
    UFUNCTION() void Start();
    UFUNCTION() void Back();
    UFUNCTION() void Original();
    UFUNCTION() void Resume();
    UFUNCTION() void Return();
    UPROPERTY(Transient) TObjectPtr<UTextBlock> Status;
    UPROPERTY(Transient) TObjectPtr<UCommonButtonBase> PrimaryButton;
    UPROPERTY(Transient) TObjectPtr<UCommonButtonBase> StartButton;
    FDelegateHandle ChangeHandle;
};
