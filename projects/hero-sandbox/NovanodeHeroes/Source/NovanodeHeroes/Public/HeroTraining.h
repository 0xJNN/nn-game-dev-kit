#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/LyraGameplayAbility_FromEquipment.h"
#include "CommonActivatableWidget.h"
#include "Components/ActorComponent.h"
#include "Engine/DataAsset.h"
#include "GameFramework/Actor.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "GameplayEffect.h"
#include "HeroCombatRules.h"
#include "HeroTrainingFlow.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "HeroTraining.generated.h"

class UAbilitySystemComponent;
class UAnimMontage;
class UButton;
class UEnhancedInputComponent;
class UInputAction;
class UInputMappingContext;
class ULyraEquipmentDefinition;
class ULyraEquipmentInstance;
class USkeletalMesh;
class USphereComponent;
class UStaticMeshComponent;
class UTextBlock;

UCLASS(BlueprintType)
class NOVANODEHEROES_API UHeroTrainingData : public UPrimaryDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<TObjectPtr<UAnimMontage>> SwordMontages;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<UAnimMontage> CastMontage;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<UAnimMontage> DashMontage;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TSubclassOf<ULyraEquipmentDefinition> SwordEquipment;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TSubclassOf<ULyraEquipmentDefinition> MageEquipment;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<USkeletalMesh> TargetMesh;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FName AttackSlot;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float SwordLengthCm = 120.f;
    bool IsComplete() const;
};

// Exists in every game instance, but does nothing without -HeroTrainingV3 and
// standalone play. Neither the original Lyra frontend nor its assets are edited.
UCLASS()
class NOVANODEHEROES_API UHeroTrainingSubsystem : public UGameInstanceSubsystem, public FTickableGameObject
{
    GENERATED_BODY()
public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
    virtual void Tick(float Delta) override;
    virtual bool IsTickable() const override;
    virtual bool IsTickableWhenPaused() const override { return true; }
    virtual TStatId GetStatId() const override;
    void RegisterExperience();
    void OpenTraining();
    void ChooseHero(bool Mage);
    bool StartTraining();
    void TogglePause();
    void ReturnToLobby();
    void Back();
    void ShowOriginalModes();
    bool IsTrainingWorld() const;
    bool IsMage() const { return Flow.Hero == NovanodeHeroes::TrainingHero::Mage; }
    const NovanodeHeroes::TrainingFlow& GetFlow() const { return Flow; }
    UHeroTrainingData* GetData() const { return Data; }
    FString GetStatusText() const;
private:
    void ShowMenu();
    void RefreshMenu();
    bool bEnabled = false;
    bool bDismissed = false;
    bool bExperienceRegistered = false;
    NovanodeHeroes::TrainingFlow Flow;
    TWeakObjectPtr<UWorld> ObservedWorld;
    UPROPERTY(Transient) TObjectPtr<UHeroTrainingData> Data;
    UPROPERTY(Transient) TObjectPtr<class UHeroTrainingMenu> Menu;
    UPROPERTY(Transient) TObjectPtr<class UHeroTrainingHUD> HUD;
};

UCLASS()
class NOVANODEHEROES_API UHeroTrainingHUD : public UUserWidget
{
    GENERATED_BODY()
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
    virtual void NativeTick(const FGeometry& Geometry, float Delta) override;
private:
    UPROPERTY(Transient) TObjectPtr<UTextBlock> Status;
};

UCLASS()
class NOVANODEHEROES_API UHeroTrainingMenu : public UCommonActivatableWidget
{
    GENERATED_BODY()
public:
    UHeroTrainingMenu(const FObjectInitializer& Initializer);
    void Refresh();
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
    virtual bool NativeOnHandleBackAction() override;
    virtual UWidget* NativeGetDesiredFocusTarget() const override;
    virtual TOptional<FUIInputConfig> GetDesiredInputConfig() const override;
private:
    UHeroTrainingSubsystem* Training() const;
    UButton* AddButton(class UVerticalBox* Panel, const TCHAR* Label, FName Callback);
    UFUNCTION() void OpenTraining();
    UFUNCTION() void ChooseMelee();
    UFUNCTION() void ChooseMage();
    UFUNCTION() void Start();
    UFUNCTION() void Resume();
    UFUNCTION() void ReturnToLobby();
    UFUNCTION() void Back();
    UFUNCTION() void OriginalModes();
    UPROPERTY(Transient) TObjectPtr<UTextBlock> Title;
    UPROPERTY(Transient) TObjectPtr<UTextBlock> Status;
    UPROPERTY(Transient) TObjectPtr<UButton> TrainingButton;
    UPROPERTY(Transient) TObjectPtr<UButton> MeleeButton;
    UPROPERTY(Transient) TObjectPtr<UButton> MageButton;
    UPROPERTY(Transient) TObjectPtr<UButton> StartButton;
    UPROPERTY(Transient) TObjectPtr<UButton> ResumeButton;
    UPROPERTY(Transient) TObjectPtr<UButton> ReturnButton;
    UPROPERTY(Transient) TObjectPtr<UButton> BackButton;
    UPROPERTY(Transient) TObjectPtr<UButton> OriginalButton;
};

UCLASS(ClassGroup=(Novanode), meta=(BlueprintSpawnableComponent))
class NOVANODEHEROES_API UHeroTrainingComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UHeroTrainingComponent();
    virtual void TickComponent(float Delta, ELevelTick Tick, FActorComponentTickFunction* Function) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    bool ExecutePrimary();
    bool ExecuteDash();
    bool IsReady() const;
    float GetCooldownRemaining(bool Dash) const;
    bool DealDamage(AActor* Target, float Amount, const FHitResult& Hit);
    int32 NativeDamageApplications = 0;
    int32 BodyMontagesPlayed = 0;
private:
    void InitializeEquipment();
    void BindInput();
    void PressPrimary();
    void ReleasePrimary();
    void PressDash();
    void ReleaseDash();
    void MenuInput();
    bool PlayBodyMontage(UAnimMontage* Montage, float Duration);
    void SweepMelee();
    void SpawnSpell();
    void ApplyCooldown(bool Dash, float Duration);
    UHeroTrainingSubsystem* Training() const;
    NovanodeHeroes::CombatRules Rules;
    double SwingAt = -100.;
    TArray<uint32> InputBindings;
    TWeakObjectPtr<UEnhancedInputComponent> BoundInput;
    UPROPERTY(Transient) TObjectPtr<UInputMappingContext> Mapping;
    UPROPERTY(Transient) TObjectPtr<UInputAction> PrimaryAction;
    UPROPERTY(Transient) TObjectPtr<UInputAction> DashAction;
    UPROPERTY(Transient) TObjectPtr<UInputAction> MenuAction;
    UPROPERTY(Transient) TObjectPtr<UAbilitySystemComponent> ASC;
    UPROPERTY(Transient) TObjectPtr<ULyraEquipmentInstance> Equipment;
    UPROPERTY(Transient) TObjectPtr<UAnimMontage> ActiveBodyMontage;
    FTimerHandle CastTimer;
};

UCLASS()
class NOVANODEHEROES_API UHeroTrainingPrimaryAbility : public ULyraGameplayAbility_FromEquipment
{
    GENERATED_BODY()
public:
    UHeroTrainingPrimaryAbility();
    virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* Info,
        const FGameplayAbilityActivationInfo Activation, const FGameplayEventData* Event) override;
};

UCLASS()
class NOVANODEHEROES_API UHeroTrainingDashAbility : public ULyraGameplayAbility_FromEquipment
{
    GENERATED_BODY()
public:
    UHeroTrainingDashAbility();
    virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* Info,
        const FGameplayAbilityActivationInfo Activation, const FGameplayEventData* Event) override;
};

UCLASS()
class NOVANODEHEROES_API UHeroTrainingDamageEffect : public UGameplayEffect
{
    GENERATED_BODY()
public:
    UHeroTrainingDamageEffect();
};

UCLASS()
class NOVANODEHEROES_API UHeroTrainingPrimaryCooldown : public UGameplayEffect
{
    GENERATED_BODY()
public:
    UHeroTrainingPrimaryCooldown();
};

UCLASS()
class NOVANODEHEROES_API UHeroTrainingDashCooldown : public UGameplayEffect
{
    GENERATED_BODY()
public:
    UHeroTrainingDashCooldown();
};

UCLASS()
class NOVANODEHEROES_API AHeroTrainingProjectile : public AActor
{
    GENERATED_BODY()
public:
    AHeroTrainingProjectile();
    UPROPERTY(Transient) TObjectPtr<UHeroTrainingComponent> Source;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UProjectileMovementComponent> Movement;
protected:
    virtual void BeginPlay() override;
private:
    UFUNCTION() void OnHit(UPrimitiveComponent* Component, AActor* Other, UPrimitiveComponent* OtherComponent,
        FVector Impulse, const FHitResult& Hit);
    UPROPERTY() TObjectPtr<USphereComponent> Collision;
    bool bConsumed = false;
};

UCLASS()
class NOVANODEHEROES_API AHeroTrainingSwordWeapon : public AActor
{
    GENERATED_BODY()
public:
    AHeroTrainingSwordWeapon();
};

UCLASS()
class NOVANODEHEROES_API AHeroTrainingMageWeapon : public AActor
{
    GENERATED_BODY()
public:
    AHeroTrainingMageWeapon();
};

UCLASS(ClassGroup=(Novanode), meta=(BlueprintSpawnableComponent))
class NOVANODEHEROES_API UHeroTrainingTeamsComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UHeroTrainingTeamsComponent();
    virtual void TickComponent(float Delta, ELevelTick Tick, FActorComponentTickFunction* Function) override;
};

// Narrow editor adapter. Sample pointers stay engine-local; no graphs or assets
// are exported. Every mutation is restricted to the new TrainingV3 namespace.
UCLASS()
class NOVANODEHEROES_API UHeroTrainingEditorTools : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static USkeletalMesh* GetPlayerRetargetMesh(UClass* ReferenceExperience);
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static UClass* GetStockBotComponentClass(UClass* ReferenceExperience);
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static bool ConfigureExperience(UClass* OwnedExperience, UClass* ReferenceExperience, UClass* OwnedBots);
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static bool ConfigureAbilitySet(UObject* OwnedSet);
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static bool ConfigureEquipment(UClass* OwnedEquipment, UObject* OwnedSet, bool Mage, USkeletalMesh* TargetMesh);
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static FName ResolveBone(USkeletalMesh* Mesh, const TArray<FString>& Candidates);
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static FName GetAttackSlot(USkeletalMesh* Mesh);
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static UAnimMontage* CreateOwnedMontage(class UAnimSequence* Sequence, const FString& Name, FName Slot);
};
