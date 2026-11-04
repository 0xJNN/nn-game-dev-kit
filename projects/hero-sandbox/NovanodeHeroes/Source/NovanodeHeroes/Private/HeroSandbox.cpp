#include "HeroSandbox.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InputComponent.h"
#include "Components/SphereComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/Engine.h"
#include "Engine/AssetManager.h"
#include "Engine/DataAsset.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/WorldSettings.h"
#include "GameplayEffectExtension.h"
#include "HAL/PlatformMisc.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Modules/ModuleManager.h"
#include "NativeGameplayTags.h"
#include "Net/UnrealNetwork.h"
#include "Sound/SoundBase.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "UObject/ConstructorHelpers.h"
#include "UObject/UnrealType.h"
#include "UObject/SoftObjectPtr.h"

class FNovanodeHeroesModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        UAssetManager::CallOrRegister_OnCompletedInitialScan(FSimpleMulticastDelegate::FDelegate::CreateLambda([]()
        {
            UClass* Experience = LoadClass<UPrimaryDataAsset>(nullptr, TEXT("/Script/LyraGame.LyraExperienceDefinition"));
            if (Experience)
                UAssetManager::Get().ScanPathForPrimaryAssets(FPrimaryAssetType(TEXT("LyraExperienceDefinition")),
                    TEXT("/NovanodeHeroes/Experiences"), Experience, true, false, true);
        }));
    }
};
IMPLEMENT_MODULE(FNovanodeHeroesModule, NovanodeHeroes)
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_HeroDamage, "Novanode.Data.Damage");

bool UHeroSandboxEditorTools::ConfigureOwnedMap(UWorld* World, UClass* ExperienceClass)
{
#if WITH_EDITOR
    if (!World || World->WorldType != EWorldType::Editor || !ExperienceClass ||
        !World->GetOutermost()->GetName().StartsWith(TEXT("/NovanodeHeroes/Maps/")) ||
        !ExperienceClass->GetPathName().StartsWith(TEXT("/NovanodeHeroes/Experiences/"))) return false;
    AWorldSettings* Settings = World->GetWorldSettings();
    FProperty* Field = Settings->GetClass()->FindPropertyByName(TEXT("DefaultGameplayExperience"));
    FClassProperty* Property = CastField<FClassProperty>(Field);
    FSoftClassProperty* SoftProperty = CastField<FSoftClassProperty>(Field);
    if ((!Property || !ExperienceClass->IsChildOf(Property->MetaClass)) &&
        (!SoftProperty || !ExperienceClass->IsChildOf(SoftProperty->MetaClass))) return false;
    Settings->Modify();
    if (SoftProperty) SoftProperty->SetPropertyValue_InContainer(Settings, FSoftObjectPtr(ExperienceClass));
    else Property->SetObjectPropertyValue_InContainer(Settings, ExperienceClass);
    Settings->MarkPackageDirty();
    return true;
#else
    return false;
#endif
}

namespace
{
void ApplyDummyDamage(UAbilitySystemComponent* Source, AHeroTargetDummy* Target, float Amount)
{
    if (!Source || !Target || !Target->HasAuthority() || Target->GetHealth() <= 0.f)
        return;
    FGameplayEffectContextHandle Context = Source->MakeEffectContext();
    FGameplayEffectSpecHandle Spec = Source->MakeOutgoingSpec(UHeroDamageEffect::StaticClass(), 1.f, Context);
    if (Spec.IsValid())
    {
        Spec.Data->SetSetByCallerMagnitude(TAG_HeroDamage, -FMath::Clamp(Amount, 0.f, 100.f));
        Source->ApplyGameplayEffectSpecToTarget(*Spec.Data.Get(), Target->GetAbilitySystemComponent());
    }
}

void PlayFeedback(UWorld* World, FVector Position, uint8 Kind)
{
    if (!World || World->GetNetMode() == NM_DedicatedServer)
        return;
    const TCHAR* Path = Kind == 0 ? TEXT("/NovanodeHeroes/Audio/S_Cast.S_Cast") :
        (Kind == 1 ? TEXT("/NovanodeHeroes/Audio/S_Slash.S_Slash") : TEXT("/NovanodeHeroes/Audio/S_Impact.S_Impact"));
    if (USoundBase* Sound = LoadObject<USoundBase>(nullptr, Path))
        UGameplayStatics::PlaySoundAtLocation(World, Sound, Position, 0.35f);
    if (Kind == 2)
        World->SpawnActor<AHeroImpactFX>(Position, FRotator::ZeroRotator);
}

float ServerTime(const UWorld* World)
{
    if (const AGameStateBase* State = World->GetGameState())
        return static_cast<float>(State->GetServerWorldTimeSeconds());
    return World->GetTimeSeconds();
}
}

UHeroHealthSet::UHeroHealthSet() { InitHealth(100.f); }
void UHeroHealthSet::PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data)
{
    Super::PostGameplayEffectExecute(Data);
    if (Data.EvaluatedData.Attribute == GetHealthAttribute())
        SetHealth(FMath::Clamp(GetHealth(), 0.f, 100.f));
}
void UHeroHealthSet::OnRep_Health(const FGameplayAttributeData& Old)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UHeroHealthSet, Health, Old);
}
void UHeroHealthSet::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME_CONDITION_NOTIFY(UHeroHealthSet, Health, COND_None, REPNOTIFY_Always);
}

UHeroDamageEffect::UHeroDamageEffect()
{
    DurationPolicy = EGameplayEffectDurationType::Instant;
    FGameplayModifierInfo Modifier;
    Modifier.Attribute = UHeroHealthSet::GetHealthAttribute();
    Modifier.ModifierOp = EGameplayModOp::Additive;
    FSetByCallerFloat Value;
    Value.DataTag = TAG_HeroDamage;
    Modifier.ModifierMagnitude = FGameplayEffectModifierMagnitude(Value);
    Modifiers.Add(Modifier);
}

AHeroTargetDummy::AHeroTargetDummy()
{
    bReplicates = true;
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickInterval = 0.1f;
    Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
    SetRootComponent(Body);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    Body->SetStaticMesh(Cylinder.Object);
    Body->SetRelativeScale3D(FVector(.7f, .7f, 1.5f));
    Body->SetCollisionObjectType(ECC_Pawn);
    Body->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Body->SetCollisionResponseToAllChannels(ECR_Block);
    Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("HealthLabel"));
    Label->SetupAttachment(Body);
    Label->SetRelativeLocation(FVector(0.f, 0.f, 95.f));
    Label->SetRelativeRotation(FRotator(0.f, 180.f, 0.f));
    Label->SetWorldSize(20.f);
    Label->SetHorizontalAlignment(EHTA_Center);
    AbilitySystem = CreateDefaultSubobject<UAbilitySystemComponent>(TEXT("AbilitySystem"));
    AbilitySystem->SetIsReplicated(true);
    AbilitySystem->SetReplicationMode(EGameplayEffectReplicationMode::Minimal);
    Attributes = CreateDefaultSubobject<UHeroHealthSet>(TEXT("Health"));
}
void AHeroTargetDummy::BeginPlay()
{
    Super::BeginPlay();
    AbilitySystem->InitAbilityActorInfo(this, this);
    AbilitySystem->AddAttributeSetSubobject(Attributes.Get());
    if (HasAuthority()) ResetHealth();
}
float AHeroTargetDummy::GetHealth() const { return Attributes->GetHealth(); }
void AHeroTargetDummy::ResetHealth()
{
    if (HasAuthority()) AbilitySystem->SetNumericAttributeBase(UHeroHealthSet::GetHealthAttribute(), 100.f);
    ResetAt = 0.0;
}
void AHeroTargetDummy::Tick(float Delta)
{
    Super::Tick(Delta);
    Label->SetText(FText::FromString(FString::Printf(TEXT("TARGET  %.0f / 100"), GetHealth())));
    Label->SetTextRenderColor(GetHealth() > 0.f ? FColor::Cyan : FColor::Orange);
    APlayerController* Viewer = UGameplayStatics::GetPlayerController(this, 0);
    if (Viewer && Viewer->IsLocalController() && Viewer->PlayerCameraManager)
        UHeroSandboxEditorTools::FaceOwnedText(Label, Viewer->PlayerCameraManager->GetCameraLocation());
    if (HasAuthority() && GetHealth() <= 0.f)
    {
        if (ResetAt == 0.0) ResetAt = GetWorld()->GetTimeSeconds() + 3.0;
        if (GetWorld()->GetTimeSeconds() >= ResetAt) ResetHealth();
    }
}

AHeroImpactFX::AHeroImpactFX()
{
    PrimaryActorTick.bCanEverTick = true;
    Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Burst"));
    SetRootComponent(Mesh);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    Mesh->SetStaticMesh(Sphere.Object);
    Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Mesh->SetCastShadow(false);
    InitialLifeSpan = .25f;
}
void AHeroImpactFX::Tick(float Delta)
{
    Super::Tick(Delta);
    Age += Delta;
    Mesh->SetWorldScale3D(FVector(.15f + Age * 2.f));
}

AHeroSpellProjectile::AHeroSpellProjectile()
{
    bReplicates = true;
    SetReplicateMovement(true);
    Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
    SetRootComponent(Collision);
    Collision->InitSphereRadius(12.f);
    Collision->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Collision->SetCollisionObjectType(ECC_WorldDynamic);
    Collision->SetCollisionResponseToAllChannels(ECR_Ignore);
    Collision->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
    Collision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
    auto* Visual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ArcaneOrb"));
    Visual->SetupAttachment(Collision);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    Visual->SetStaticMesh(Sphere.Object);
    Visual->SetRelativeScale3D(FVector(.24f));
    Visual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Visual->SetCastShadow(false);
    Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
    Movement->InitialSpeed = 1800.f;
    Movement->MaxSpeed = 1800.f;
    Movement->ProjectileGravityScale = 0.f;
    Movement->bRotationFollowsVelocity = true;
    InitialLifeSpan = 3.f;
}
void AHeroSpellProjectile::BeginPlay()
{
    Super::BeginPlay();
    Collision->IgnoreActorWhenMoving(GetOwner(), true);
    if (HasAuthority()) Collision->OnComponentHit.AddDynamic(this, &AHeroSpellProjectile::OnHit);
    else Movement->Deactivate(); // Only the server simulates; clients receive movement replication.
}
void AHeroSpellProjectile::OnHit(UPrimitiveComponent*, AActor* Other, UPrimitiveComponent*, FVector, const FHitResult& Hit)
{
    if (!HasAuthority() || bConsumed || Other == GetOwner()) return;
    bConsumed = true;
    ApplyDummyDamage(SourceASC, Cast<AHeroTargetDummy>(Other), Damage);
    MulticastImpact(Hit.ImpactPoint);
    Destroy();
}
void AHeroSpellProjectile::MulticastImpact_Implementation(FVector Location) { PlayFeedback(GetWorld(), Location, 2); }

UHeroCombatComponent::UHeroCombatComponent()
{
    SetIsReplicatedByDefault(true);
    PrimaryComponentTick.bCanEverTick = true;
}
void UHeroCombatComponent::BeginPlay()
{
    Super::BeginPlay();
    ACharacter* Character = Cast<ACharacter>(GetOwner());
    if (!Character || GetNetMode() == NM_DedicatedServer) return;
    Weapon = NewObject<UStaticMeshComponent>(Character, TEXT("HeroWeapon"));
    Weapon->SetupAttachment(Character->GetMesh(), TEXT("hand_r"));
    Weapon->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Weapon->RegisterComponent();
    Orb = NewObject<UStaticMeshComponent>(Character, TEXT("HeroStaffOrb"));
    Orb->SetupAttachment(Weapon);
    Orb->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere")));
    Orb->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Orb->RegisterComponent();
    UpdateWeapon();
}
void UHeroCombatComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (GetOwner()->HasAuthority() && ASC)
    {
        if (PrimaryHandle.IsValid()) ASC->ClearAbility(PrimaryHandle);
        if (DashHandle.IsValid()) ASC->ClearAbility(DashHandle);
    }
    if (Weapon) Weapon->DestroyComponent();
    if (Orb) Orb->DestroyComponent();
    Super::EndPlay(Reason);
}
bool UHeroCombatComponent::Ready() const
{
    const ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    return Pawn && Pawn->GetController() && ASC && ASC->GetAvatarActor() == Pawn &&
        Pawn->GetCharacterMovement()->MovementMode != MOVE_None &&
        !ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag(TEXT("Status.Death"), false));
}
void UHeroCombatComponent::InitializeAbilities()
{
    if (ASC) return;
    ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    if (!Pawn) return;
    UAbilitySystemComponent* Found = UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Pawn);
    if (!Found && Pawn->GetPlayerState()) Found = UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Pawn->GetPlayerState());
    if (!Found || Found->GetAvatarActor() != Pawn) return;
    ASC = Found;
    if (Pawn->HasAuthority())
    {
        PrimaryHandle = ASC->GiveAbility(FGameplayAbilitySpec(UHeroPrimaryAbility::StaticClass(), 1, INDEX_NONE, this));
        DashHandle = ASC->GiveAbility(FGameplayAbilitySpec(UHeroDashAbility::StaticClass(), 1, INDEX_NONE, this));
    }
}
void UHeroCombatComponent::BindInput()
{
    ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    if (!Pawn || !Pawn->IsLocallyControlled() || !Pawn->InputComponent || BoundInput == Pawn->InputComponent) return;
    UInputComponent* Input = Pawn->InputComponent;
    Input->BindKey(EKeys::One, IE_Pressed, this, &UHeroCombatComponent::SelectMage);
    Input->BindKey(EKeys::Two, IE_Pressed, this, &UHeroCombatComponent::SelectSword);
    Input->BindKey(EKeys::J, IE_Pressed, this, &UHeroCombatComponent::PrimaryInput);
    Input->BindKey(EKeys::K, IE_Pressed, this, &UHeroCombatComponent::DashInput);
    BoundInput = Input;
}
void UHeroCombatComponent::SelectMage() { ServerSelect(0); }
void UHeroCombatComponent::SelectSword() { ServerSelect(1); }
void UHeroCombatComponent::PrimaryInput() { ServerUse(false); }
void UHeroCombatComponent::DashInput() { ServerUse(true); }
void UHeroCombatComponent::ServerSelect_Implementation(uint8 Kit)
{
    const double Now = GetWorld()->GetTimeSeconds();
    if (Kit > 1 || !Ready() || Now - LastSelectRequest < .1) return;
    LastSelectRequest = Now;
    Rules.Select(Kit == 0 ? NovanodeHeroes::Kit::Mage : NovanodeHeroes::Kit::Sword);
    SelectedKit = Kit;
    Combo = 0;
    SwingStartedAt = -100.f;
}
void UHeroCombatComponent::ServerUse_Implementation(bool bDash)
{
    const double Now = GetWorld()->GetTimeSeconds();
    if (!Ready() || Now - LastUseRequest < .08) return;
    LastUseRequest = Now;
    ASC->TryActivateAbility(bDash ? DashHandle : PrimaryHandle, false);
}
bool UHeroCombatComponent::ExecutePrimary()
{
    if (!GetOwner()->HasAuthority() || !Ready()) return false;
    const double Now = GetWorld()->GetTimeSeconds();
    if (!Rules.TryPrimary(Now)) return false;
    ++PrimaryExecutions;
    PrimaryReadyAt = static_cast<float>(Rules.PrimaryReadyAt);
    Combo = Rules.Combo;
    SwingStartedAt = static_cast<float>(Now);
    ACharacter* Pawn = CastChecked<ACharacter>(GetOwner());
    if (SelectedKit == 0)
    {
        // Spawn from the pawn, not a client-supplied position; collision prevents shooting through cover.
        FVector Eye; FRotator Aim;
        Pawn->GetActorEyesViewPoint(Eye, Aim);
        FActorSpawnParameters Params;
        Params.Owner = Pawn;
        Params.Instigator = Pawn;
        Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::DontSpawnIfColliding;
        const FVector Muzzle = Eye + Aim.Vector() * 80.f;
        FHitResult Cover;
        FCollisionQueryParams MuzzleQuery(SCENE_QUERY_STAT(HeroMuzzle), false, Pawn);
        if (GetWorld()->SweepSingleByChannel(Cover, Eye, Muzzle, FQuat::Identity, ECC_Visibility,
            FCollisionShape::MakeSphere(12.f), MuzzleQuery)) return false;
        AHeroSpellProjectile* Projectile = GetWorld()->SpawnActor<AHeroSpellProjectile>(Muzzle, Aim, Params);
        if (Projectile)
        {
            ++ProjectilesSpawned;
            Projectile->SourceASC = ASC;
            Projectile->Damage = Rules.Damage();
        }
        MulticastFeedback(Eye, 0);
    }
    else MulticastFeedback(Pawn->GetActorLocation(), 1);
    return true;
}
bool UHeroCombatComponent::ExecuteDash()
{
    if (!GetOwner()->HasAuthority() || !Ready() || !Rules.TryDash(GetWorld()->GetTimeSeconds())) return false;
    DashReadyAt = static_cast<float>(Rules.DashReadyAt);
    ACharacter* Pawn = CastChecked<ACharacter>(GetOwner());
    FVector Direction = Pawn->GetActorForwardVector();
    Direction.Z = 0.f;
    // CharacterMovement handles collision/replication. This is not a teleport or predicted dash.
    Pawn->LaunchCharacter(Direction.GetSafeNormal() * 850.f + FVector(0.f, 0.f, 80.f), true, false);
    MulticastFeedback(Pawn->GetActorLocation(), 1);
    return true;
}
void UHeroCombatComponent::SweepSword()
{
    if (!GetOwner()->HasAuthority() || SelectedKit != 1 || !Ready()) return;
    const float Age = GetWorld()->GetTimeSeconds() - SwingStartedAt;
    if (Age < .10f || Age > .27f) return;
    const AActor* Owner = GetOwner();
    const FVector Start = Owner->GetActorLocation() + Owner->GetActorForwardVector() * 45.f;
    const FVector End = Start + Owner->GetActorForwardVector() * 160.f;
    TArray<FHitResult> Hits;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(HeroSword), false, Owner);
    FCollisionObjectQueryParams Objects;
    Objects.AddObjectTypesToQuery(ECC_Pawn);
    GetWorld()->SweepMultiByObjectType(Hits, Start, End, FQuat::Identity, Objects, FCollisionShape::MakeSphere(55.f), Query);
    for (const FHitResult& Hit : Hits)
    {
        AHeroTargetDummy* Dummy = Cast<AHeroTargetDummy>(Hit.GetActor());
        if (!Dummy || Dummy->GetHealth() <= 0.f) continue;
        ++SwordTargetMatches;
        FHitResult Cover;
        const bool Blocked = GetWorld()->LineTraceSingleByChannel(Cover, Start, Dummy->GetActorLocation(), ECC_Visibility, Query);
        if (Blocked && Cover.GetActor() != Dummy) continue;
        if (Rules.FirstHit(Dummy->GetUniqueID()))
        {
            ApplyDummyDamage(ASC, Dummy, Rules.Damage());
            MulticastFeedback(Hit.ImpactPoint, 2);
        }
    }
}
void UHeroCombatComponent::UpdateWeapon()
{
    if (!Weapon) return;
    if (SelectedKit == 0)
    {
        Weapon->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")));
        Weapon->SetRelativeScale3D(FVector(.045f, .045f, .8f));
        Weapon->SetRelativeLocation(FVector(0.f, 0.f, 25.f));
        Orb->SetVisibility(true);
        Orb->SetRelativeLocation(FVector(0.f, 0.f, 52.f));
        Orb->SetWorldScale3D(FVector(.16f));
    }
    else
    {
        UStaticMesh* Sword = LoadObject<UStaticMesh>(nullptr, TEXT("/NovanodeHeroes/Imported/SM_Claymore.SM_Claymore"));
        bUsingImportedSword = Sword != nullptr;
        Weapon->SetStaticMesh(Sword ? Sword : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
        Weapon->SetRelativeScale3D(Sword ? FVector(1.f) : FVector(.06f, .12f, 1.f));
        Weapon->SetRelativeLocation(FVector(0.f, 0.f, 35.f));
        Orb->SetVisibility(false);
    }
}
void UHeroCombatComponent::TickComponent(float Delta, ELevelTick Tick, FActorComponentTickFunction* Function)
{
    Super::TickComponent(Delta, Tick, Function);
    const float Now = GetWorld()->GetTimeSeconds();
    if (Now - LastBindAttempt > .25)
    {
        LastBindAttempt = Now;
        InitializeAbilities();
        BindInput();
    }
    SweepSword();
    if (Weapon)
    {
        const bool bWantsSword = SelectedKit == 1;
        const bool bHasSword = Weapon->GetStaticMesh() && Weapon->GetStaticMesh()->GetName() != TEXT("Cylinder");
        if (bWantsSword != bHasSword) UpdateWeapon();
        const float Age = ServerTime(GetWorld()) - SwingStartedAt;
        const float Alpha = FMath::Clamp(Age / .38f, 0.f, 1.f);
        const float Swing = bWantsSword && Age >= 0.f && Age < .38f ? FMath::Sin(Alpha * PI) * (Combo == 2 ? -85.f : 85.f) : 0.f;
        Weapon->SetRelativeRotation(FRotator(Swing, 0.f, 0.f));
    }
    const ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    if (Pawn && Pawn->IsLocallyControlled() && GEngine)
    {
        const float Remaining = FMath::Max(0.f, PrimaryReadyAt - ServerTime(GetWorld()));
        GEngine->AddOnScreenDebugMessage(0x4E4E, .1f, FColor::Cyan,
            FString::Printf(TEXT("HERO LAB | 1 Mage / 2 Sword | J Attack | K Dash | %s | CD %.1fs | Combo %d"),
                SelectedKit == 0 ? TEXT("MAGE") : TEXT("SWORD"), Remaining, Combo));
    }
}
void UHeroCombatComponent::MulticastFeedback_Implementation(FVector Location, uint8 Kind) { PlayFeedback(GetWorld(), Location, Kind); }
void UHeroCombatComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(UHeroCombatComponent, SelectedKit);
    DOREPLIFETIME(UHeroCombatComponent, Combo);
    DOREPLIFETIME(UHeroCombatComponent, PrimaryReadyAt);
    DOREPLIFETIME(UHeroCombatComponent, DashReadyAt);
    DOREPLIFETIME(UHeroCombatComponent, SwingStartedAt);
}

UHeroPrimaryAbility::UHeroPrimaryAbility()
{
    InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerActor;
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
}
void UHeroPrimaryAbility::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* Info,
    const FGameplayAbilityActivationInfo Activation, const FGameplayEventData*)
{
    UHeroCombatComponent* Combat = Info && Info->AvatarActor.IsValid() ? Info->AvatarActor->FindComponentByClass<UHeroCombatComponent>() : nullptr;
    const bool bOK = Combat && CommitAbility(Handle, Info, Activation) && Combat->ExecutePrimary();
    EndAbility(Handle, Info, Activation, true, !bOK);
}
UHeroDashAbility::UHeroDashAbility()
{
    InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerActor;
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
}
void UHeroDashAbility::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* Info,
    const FGameplayAbilityActivationInfo Activation, const FGameplayEventData*)
{
    UHeroCombatComponent* Combat = Info && Info->AvatarActor.IsValid() ? Info->AvatarActor->FindComponentByClass<UHeroCombatComponent>() : nullptr;
    const bool bOK = Combat && CommitAbility(Handle, Info, Activation) && Combat->ExecuteDash();
    EndAbility(Handle, Info, Activation, true, !bOK);
}

AHeroSandboxDirector::AHeroSandboxDirector()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickInterval = .25f;
}
void AHeroSandboxDirector::BeginPlay()
{
    Super::BeginPlay();
    if (!HasAuthority()) return;
    for (int32 Index = 0; Index < 3; ++Index)
    {
        AHeroTargetDummy* Dummy = GetWorld()->SpawnActor<AHeroTargetDummy>(
            FVector(350.f + Index * 300.f, (Index - 1) * 250.f, 100.f), FRotator::ZeroRotator);
        if (Dummy && TargetMaterial) Dummy->Body->SetMaterial(0, TargetMaterial);
    }
}
void AHeroSandboxDirector::Tick(float Delta)
{
    Super::Tick(Delta);
    if (!HasAuthority()) return;
    for (TActorIterator<ACharacter> It(GetWorld()); It; ++It)
    {
        ACharacter* Pawn = *It;
        if (!Pawn->IsPlayerControlled() || Pawn->FindComponentByClass<UHeroCombatComponent>()) continue;
        UHeroCombatComponent* Component = NewObject<UHeroCombatComponent>(Pawn);
        Pawn->AddInstanceComponent(Component);
        Component->RegisterComponent();
    }
    RunOwnedSmoke();
    RunPresentationProbe();
}

void AHeroSandboxDirector::RunOwnedSmoke()
{
    FString Output;
    if (GetNetMode() != NM_Standalone || !FParse::Value(FCommandLine::Get(), TEXT("HeroSandboxSmoke="), Output)) return;
    const double Now = GetWorld()->GetTimeSeconds();
    ACharacter* Pawn = UGameplayStatics::GetPlayerCharacter(this, 0);
    UHeroCombatComponent* Combat = Pawn ? Pawn->FindComponentByClass<UHeroCombatComponent>() : nullptr;
    if (SmokeStage == 0 && Combat && Now > 3.f)
    {
        for (TActorIterator<AHeroTargetDummy> It(GetWorld()); It; ++It)
            if (It->GetActorLocation().X < 400.f) SmokeTarget = *It;
        if (!SmokeTarget) return;
        Pawn->SetActorLocation(FVector(0.f, -250.f, 100.f));
        FVector Eye; FRotator Rotation;
        Pawn->GetActorEyesViewPoint(Eye, Rotation);
        Pawn->GetController()->SetControlRotation((SmokeTarget->GetActorLocation() - Eye).Rotation());
        Pawn->SetActorRotation(FRotator::ZeroRotator);
        Combat->ServerSelect(0);
        Combat->ServerUse(false);
        SmokeStage = 1;
        SmokeNextAt = Now + 1.2;
    }
    else if (SmokeStage == 1 && Now >= SmokeNextAt && Combat && SmokeTarget)
    {
        SmokeHealthAfterSpell = SmokeTarget->GetHealth();
        bSmokeSpell = FMath::IsNearlyEqual(SmokeHealthAfterSpell, 75.f);
        Pawn->SetActorLocation(FVector(200.f, -250.f, 100.f));
        Pawn->SetActorRotation(FRotator::ZeroRotator);
        Combat->ServerSelect(1);
        SmokeStage = 2;
        SmokeNextAt = Now + .3;
    }
    else if (SmokeStage >= 2 && SmokeStage <= 4 && Now >= SmokeNextAt && Combat && SmokeTarget)
    {
        if (SmokeStage == 3)
        {
            SmokeHealthAfterFirst = SmokeTarget->GetHealth();
            bSmokeFirstHit = FMath::IsNearlyEqual(SmokeHealthAfterFirst, 55.f);
        }
        if (SmokeStage == 4)
        {
            SmokeHealthAfterSecond = SmokeTarget->GetHealth();
            bSmokeSecondHit = FMath::IsNearlyEqual(SmokeHealthAfterSecond, 35.f);
        }
        Combat->ServerUse(false);
        ++SmokeStage;
        SmokeNextAt = Now + .55;
    }
    else if (SmokeStage == 5 && Now >= SmokeNextAt && Combat && SmokeTarget)
    {
        SmokeHealthAfterThird = SmokeTarget->GetHealth();
        bSmokeThirdHit = FMath::IsNearlyEqual(SmokeHealthAfterThird, 5.f);
        SmokeDashStart = Pawn->GetActorLocation();
        Combat->ServerUse(true);
        SmokeStage = 6;
        SmokeNextAt = Now + .5;
    }
    else if (SmokeStage == 6 && Now >= SmokeNextAt && Combat)
    {
        bSmokeDash = FVector::Dist2D(SmokeDashStart, Pawn->GetActorLocation()) > 30.f;
        SmokeStage = 7;
    }
    if (Now > 35.f || SmokeStage == 7)
    {
        const bool bPassed = bSmokeSpell && bSmokeFirstHit && bSmokeSecondHit && bSmokeThirdHit && bSmokeDash;
        const FString Json = FString::Printf(TEXT("{\"passed\":%s,\"spell_25_damage\":%s,\"sword_first_20_once\":%s,\"sword_second_20\":%s,\"sword_third_30\":%s,\"dash_displaced\":%s,\"stage\":%d,\"world_seconds\":%.3f,\"health_after_spell\":%.1f,\"health_after_first\":%.1f,\"health_after_second\":%.1f,\"health_after_third\":%.1f,\"primary_executions\":%d,\"projectiles_spawned\":%d,\"sword_target_matches\":%d,\"multiplayer_verified\":false,\"visual_verified\":false}"),
            bPassed ? TEXT("true") : TEXT("false"), bSmokeSpell ? TEXT("true") : TEXT("false"),
            bSmokeFirstHit ? TEXT("true") : TEXT("false"), bSmokeSecondHit ? TEXT("true") : TEXT("false"),
            bSmokeThirdHit ? TEXT("true") : TEXT("false"), bSmokeDash ? TEXT("true") : TEXT("false"), SmokeStage, Now,
            SmokeHealthAfterSpell, SmokeHealthAfterFirst, SmokeHealthAfterSecond, SmokeHealthAfterThird,
            Combat ? Combat->PrimaryExecutions : 0, Combat ? Combat->ProjectilesSpawned : 0, Combat ? Combat->SwordTargetMatches : 0);
        FFileHelper::SaveStringToFile(Json, *Output);
        FPlatformMisc::RequestExit(false);
    }
}
