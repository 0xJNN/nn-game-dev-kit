#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "AbilitySystemComponent.h"
#include "AttributeSet.h"
#include "Abilities/GameplayAbility.h"
#include "Components/ActorComponent.h"
#include "GameFramework/Actor.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "GameplayEffect.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Engine/TextRenderActor.h"
#include "HeroCombatRules.h"
#include "HeroSandbox.generated.h"

class ACharacter;
class USphereComponent;
class UStaticMeshComponent;
class UTextRenderComponent;
class UInputComponent;
class UMaterialInterface;

UCLASS()
class NOVANODEHEROES_API UHeroSandboxEditorTools : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    // Python treats the sample's EditDefaultsOnly field as instance-readonly.
    // This narrow local adapter writes ONLY our own map, never the class CDO.
    UFUNCTION(BlueprintCallable, Category="Novanode|Preparation")
    static bool ConfigureOwnedMap(UWorld* World, UClass* ExperienceClass);
    UFUNCTION(BlueprintCallable, Category="Novanode|Preparation")
    static int32 AddOwnedCosmeticAssemblyAction(UClass* ExperienceClass, UClass* ReferenceExperienceClass);
    UFUNCTION(BlueprintCallable, Category="Novanode|Preparation")
    static bool ValidateOwnedCosmeticAssemblyAction(UClass* ExperienceClass);
    static void FaceOwnedText(UTextRenderComponent* Text, const FVector& Viewer);
};

UCLASS()
class NOVANODEHEROES_API AHeroFacingTextActor : public ATextRenderActor
{
    GENERATED_BODY()
public:
    AHeroFacingTextActor();
    virtual void BeginPlay() override;
    virtual void Tick(float Delta) override;
    UFUNCTION(BlueprintCallable) void FaceEntry(FVector Viewer);
};

// A deliberately isolated original-text scene, never a screenshot of Lyra or
// restricted marketplace art. Refuses capture if foreign visual assets exist.
UCLASS()
class NOVANODEHEROES_API AHeroTextCalibrationActor : public AActor
{
    GENERATED_BODY()
public:
    AHeroTextCalibrationActor();
    virtual void Tick(float Delta) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    void FinishCapture();
    double StartedAt = 0.;
    bool bRequested = false;
    bool bCameraPrepared = false;
    int32 CalibrationDefaultPawnVisualsRemoved = 0;
    int32 CalibrationCameraVisualsRemoved = 0;
    FDelegateHandle ScreenshotHandle;
};

UCLASS()
class NOVANODEHEROES_API UHeroHealthSet : public UAttributeSet
{
    GENERATED_BODY()
public:
    UHeroHealthSet();
    UPROPERTY(ReplicatedUsing=OnRep_Health) FGameplayAttributeData Health;
    GAMEPLAYATTRIBUTE_PROPERTY_GETTER(UHeroHealthSet, Health)
    GAMEPLAYATTRIBUTE_VALUE_GETTER(Health)
    GAMEPLAYATTRIBUTE_VALUE_SETTER(Health)
    GAMEPLAYATTRIBUTE_VALUE_INITTER(Health)
    virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
    UFUNCTION() void OnRep_Health(const FGameplayAttributeData& Old);
};

UCLASS()
class NOVANODEHEROES_API UHeroDamageEffect : public UGameplayEffect
{
    GENERATED_BODY()
public:
    UHeroDamageEffect();
};

UCLASS()
class NOVANODEHEROES_API AHeroTargetDummy : public AActor, public IAbilitySystemInterface
{
    GENERATED_BODY()
public:
    AHeroTargetDummy();
    virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override { return AbilitySystem; }
    virtual void BeginPlay() override;
    virtual void Tick(float Delta) override;
    void ResetHealth();
    UFUNCTION(BlueprintPure) float GetHealth() const;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UAbilitySystemComponent> AbilitySystem;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UHeroHealthSet> Attributes;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Body;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UTextRenderComponent> Label;
private:
    double ResetAt = 0.0;
};

UCLASS()
class NOVANODEHEROES_API AHeroImpactFX : public AActor
{
    GENERATED_BODY()
public:
    AHeroImpactFX();
    virtual void Tick(float Delta) override;
private:
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Mesh;
    float Age = 0.f;
};

UCLASS()
class NOVANODEHEROES_API AHeroSpellProjectile : public AActor
{
    GENERATED_BODY()
public:
    AHeroSpellProjectile();
    virtual void BeginPlay() override;
    UPROPERTY(VisibleAnywhere) TObjectPtr<USphereComponent> Collision;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UProjectileMovementComponent> Movement;
    UPROPERTY() TObjectPtr<UAbilitySystemComponent> SourceASC;
    float Damage = 25.f;
    UFUNCTION() void OnHit(UPrimitiveComponent* HitComponent, AActor* Other, UPrimitiveComponent* OtherComp,
        FVector NormalImpulse, const FHitResult& Hit);
    UFUNCTION(NetMulticast, Unreliable) void MulticastImpact(FVector Location);
private:
    bool bConsumed = false;
};

UCLASS()
class NOVANODEHEROES_API UHeroCombatComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UHeroCombatComponent();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void TickComponent(float Delta, ELevelTick Tick, FActorComponentTickFunction* Function) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
    bool ExecutePrimary();
    bool ExecuteDash();
    void SelectMage();
    void SelectSword();
    void PrimaryInput();
    void DashInput();
    UFUNCTION(Server, Reliable) void ServerSelect(uint8 Kit);
    UFUNCTION(Server, Reliable) void ServerUse(bool bDash);
    UFUNCTION(NetMulticast, Unreliable) void MulticastFeedback(FVector Location, uint8 Kind);
    UPROPERTY(Replicated, BlueprintReadOnly) uint8 SelectedKit = 0;
    UPROPERTY(Replicated, BlueprintReadOnly) int32 Combo = 0;
    UPROPERTY(Replicated, BlueprintReadOnly) float PrimaryReadyAt = 0.f;
    UPROPERTY(Replicated, BlueprintReadOnly) float DashReadyAt = 0.f;
    UPROPERTY(Replicated) float SwingStartedAt = -100.f;
    int32 PrimaryExecutions = 0;
    int32 ProjectilesSpawned = 0;
    int32 SwordTargetMatches = 0;
private:
    bool Ready() const;
    void InitializeAbilities();
    void BindInput();
    void SweepSword();
    void UpdateWeapon();
    NovanodeHeroes::CombatRules Rules;
    UPROPERTY() TObjectPtr<UAbilitySystemComponent> ASC;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Weapon;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Orb;
    TWeakObjectPtr<UInputComponent> BoundInput;
    FGameplayAbilitySpecHandle PrimaryHandle;
    FGameplayAbilitySpecHandle DashHandle;
    double LastBindAttempt = -1.0;
    double LastSelectRequest = -1.0;
    double LastUseRequest = -1.0;
    bool bUsingImportedSword = false;
};

UCLASS()
class NOVANODEHEROES_API UHeroPrimaryAbility : public UGameplayAbility
{
    GENERATED_BODY()
public:
    UHeroPrimaryAbility();
    virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* Info,
        const FGameplayAbilityActivationInfo Activation, const FGameplayEventData* Trigger) override;
};

UCLASS()
class NOVANODEHEROES_API UHeroDashAbility : public UGameplayAbility
{
    GENERATED_BODY()
public:
    UHeroDashAbility();
    virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* Info,
        const FGameplayAbilityActivationInfo Activation, const FGameplayEventData* Trigger) override;
};

// Map-local integration: no global pawn patches, no loading into other experiences.
UCLASS()
class NOVANODEHEROES_API AHeroSandboxDirector : public AActor
{
    GENERATED_BODY()
public:
    AHeroSandboxDirector();
    virtual void BeginPlay() override;
    virtual void Tick(float Delta) override;
    UPROPERTY(EditAnywhere, Category="Novanode|Presentation") TObjectPtr<UMaterialInterface> TargetMaterial;
private:
    void RunOwnedSmoke();
    void RunPresentationProbe();
    double PresentationProbeStartedAt = 0.;
    UPROPERTY() TObjectPtr<AHeroTargetDummy> SmokeTarget;
    int32 SmokeStage = 0;
    double SmokeNextAt = 0.;
    FVector SmokeDashStart = FVector::ZeroVector;
    bool bSmokeSpell = false;
    bool bSmokeFirstHit = false;
    bool bSmokeSecondHit = false;
    bool bSmokeThirdHit = false;
    bool bSmokeDash = false;
    float SmokeHealthAfterSpell = -1.f;
    float SmokeHealthAfterFirst = -1.f;
    float SmokeHealthAfterSecond = -1.f;
    float SmokeHealthAfterThird = -1.f;
};
