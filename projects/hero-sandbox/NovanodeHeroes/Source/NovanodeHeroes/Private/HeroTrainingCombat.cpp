#include "HeroTraining.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystem/Attributes/LyraCombatSet.h"
#include "AbilitySystem/Attributes/LyraHealthSet.h"
#include "AbilitySystem/Executions/LyraDamageExecution.h"
#include "AbilitySystem/LyraAbilitySystemComponent.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimMontage.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/GameInstance.h"
#include "Engine/LocalPlayer.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Equipment/LyraEquipmentDefinition.h"
#include "Equipment/LyraEquipmentInstance.h"
#include "Equipment/LyraEquipmentManagerComponent.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "GameplayEffectComponents/TargetTagsGameplayEffectComponent.h"
#include "GenericTeamAgentInterface.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "NativeGameplayTags.h"
#include "Sound/SoundBase.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingPrimaryInput, "InputTag.Novanode.Training.Primary");
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingDashInput, "InputTag.Novanode.Training.Dash");
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingDamage, "Novanode.Training.Data.Damage");
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingCooldownDuration, "Novanode.Training.Data.Cooldown");
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingPrimaryCD, "Novanode.Training.Cooldown.Primary");
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingDashCD, "Novanode.Training.Cooldown.Dash");
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_TrainingAction, "Ability.Type.Action.NovanodeTraining");

namespace
{
UAbilitySystemComponent* PawnASC(AActor* Actor)
{
    UAbilitySystemComponent* Result = Actor ? UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Actor) : nullptr;
    const APawn* Pawn = Cast<APawn>(Actor);
    if (!Result && Pawn && Pawn->GetPlayerState())
        Result = UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Pawn->GetPlayerState());
    return Result;
}

FGenericTeamId PlayerTeam(const APawn* Pawn)
{
    const IGenericTeamAgentInterface* Team = Pawn ? Cast<IGenericTeamAgentInterface>(Pawn->GetPlayerState()) : nullptr;
    return Team ? Team->GetGenericTeamId() : FGenericTeamId::NoTeam;
}

void Feedback(UWorld* World, FVector Location, bool Spell)
{
    USoundBase* Sound = LoadObject<USoundBase>(nullptr, Spell ?
        TEXT("/NovanodeHeroes/Audio/S_Cast.S_Cast") : TEXT("/NovanodeHeroes/Audio/S_Slash.S_Slash"));
    if (World && Sound) UGameplayStatics::PlaySoundAtLocation(World, Sound, Location, .35f);
}

FGameplayTag NativeWeaponBlock() { return FGameplayTag::RequestGameplayTag(TEXT("Ability.Weapon.NoFiring"), false); }
}

UHeroTrainingDamageEffect::UHeroTrainingDamageEffect()
{
    DurationPolicy = EGameplayEffectDurationType::Instant;
    FGameplayEffectExecutionDefinition Execution;
    Execution.CalculationClass = ULyraDamageExecution::StaticClass();
    // Override the captured value for this execution only. Never change the
    // source's global BaseDamage or write Health directly to make a hit work.
    FGameplayEffectExecutionScopedModifierInfo Damage;
    Damage.CapturedAttribute = FGameplayEffectAttributeCaptureDefinition(ULyraCombatSet::GetBaseDamageAttribute(),
        EGameplayEffectAttributeCaptureSource::Source, true);
    Damage.ModifierOp = EGameplayModOp::Override;
    FSetByCallerFloat Amount;
    Amount.DataTag = TAG_TrainingDamage;
    Damage.ModifierMagnitude = FGameplayEffectModifierMagnitude(Amount);
    Execution.CalculationModifiers.Add(Damage);
    Executions.Add(Execution);
}

UHeroTrainingPrimaryCooldown::UHeroTrainingPrimaryCooldown()
{
    DurationPolicy = EGameplayEffectDurationType::HasDuration;
    FSetByCallerFloat Seconds;
    Seconds.DataTag = TAG_TrainingCooldownDuration;
    DurationMagnitude = FGameplayEffectModifierMagnitude(Seconds);
    FInheritedTagContainer Tags;
    Tags.AddTag(TAG_TrainingPrimaryCD);
    FindOrAddComponent<UTargetTagsGameplayEffectComponent>().SetAndApplyTargetTagChanges(Tags);
}

UHeroTrainingDashCooldown::UHeroTrainingDashCooldown()
{
    DurationPolicy = EGameplayEffectDurationType::HasDuration;
    FSetByCallerFloat Seconds;
    Seconds.DataTag = TAG_TrainingCooldownDuration;
    DurationMagnitude = FGameplayEffectModifierMagnitude(Seconds);
    FInheritedTagContainer Tags;
    Tags.AddTag(TAG_TrainingDashCD);
    FindOrAddComponent<UTargetTagsGameplayEffectComponent>().SetAndApplyTargetTagChanges(Tags);
}

UHeroTrainingComponent::UHeroTrainingComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
}

UHeroTrainingSubsystem* UHeroTrainingComponent::Training() const
{
    return GetWorld() && GetWorld()->GetGameInstance() ? GetWorld()->GetGameInstance()->GetSubsystem<UHeroTrainingSubsystem>() : nullptr;
}

bool UHeroTrainingComponent::IsReady() const
{
    const ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    const UHeroTrainingSubsystem* Session = Training();
    return Session && Session->IsTrainingWorld() && Pawn && Pawn->IsPlayerControlled() &&
        ASC && Equipment && ASC->GetAvatarActor() == Pawn && Pawn->GetCharacterMovement()->MovementMode != MOVE_None &&
        !ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag(TEXT("Status.Death"), false));
}

void UHeroTrainingComponent::InitializeEquipment()
{
    ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    UHeroTrainingSubsystem* Session = Training();
    if (!Pawn || !Pawn->IsPlayerControlled() || !Pawn->HasAuthority() || !Session || !Session->IsTrainingWorld() ||
        !Session->GetData() || !Session->GetData()->IsComplete() || Equipment) return;
    ASC = PawnASC(Pawn);
    ULyraEquipmentManagerComponent* Manager = Pawn->FindComponentByClass<ULyraEquipmentManagerComponent>();
    if (!ASC || ASC->GetAvatarActor() != Pawn || !Manager) return;
    // Native equipment owns grant/removal of our abilities and spawned visuals.
    // Only this opt-in human pawn gives up its default shooter equipment.
    const TArray<ULyraEquipmentInstance*> Existing = Manager->GetEquipmentInstancesOfType(ULyraEquipmentInstance::StaticClass());
    for (ULyraEquipmentInstance* Item : Existing) Manager->UnequipItem(Item);
    Rules.Select(Session->IsMage() ? NovanodeHeroes::Kit::Mage : NovanodeHeroes::Kit::Sword);
    Equipment = Manager->EquipItem(Session->IsMage() ? Session->GetData()->MageEquipment : Session->GetData()->SwordEquipment);
    if (Equipment && NativeWeaponBlock().IsValid()) ASC->AddLooseGameplayTag(NativeWeaponBlock());
}

void UHeroTrainingComponent::BindInput()
{
    ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    APlayerController* Player = Pawn ? Cast<APlayerController>(Pawn->GetController()) : nullptr;
    UEnhancedInputComponent* Input = Pawn ? Cast<UEnhancedInputComponent>(Pawn->InputComponent) : nullptr;
    UEnhancedInputLocalPlayerSubsystem* Inputs = Player && Player->GetLocalPlayer() ?
        Player->GetLocalPlayer()->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr;
    if (!IsReady() || !Player || !Player->IsLocalController() || !Input || !Inputs || BoundInput.IsValid()) return;
    Mapping = NewObject<UInputMappingContext>(this);
    PrimaryAction = NewObject<UInputAction>(this);
    DashAction = NewObject<UInputAction>(this);
    MenuAction = NewObject<UInputAction>(this);
    Mapping->MapKey(PrimaryAction, EKeys::LeftMouseButton);
    Mapping->MapKey(PrimaryAction, EKeys::J);
    Mapping->MapKey(DashAction, EKeys::Q);
    Mapping->MapKey(DashAction, EKeys::K);
    Mapping->MapKey(MenuAction, EKeys::Tab);
    Mapping->MapKey(MenuAction, EKeys::Escape);
    InputBindings.Add(Input->BindAction(PrimaryAction, ETriggerEvent::Started, this, &UHeroTrainingComponent::PressPrimary).GetHandle());
    InputBindings.Add(Input->BindAction(PrimaryAction, ETriggerEvent::Completed, this, &UHeroTrainingComponent::ReleasePrimary).GetHandle());
    InputBindings.Add(Input->BindAction(DashAction, ETriggerEvent::Started, this, &UHeroTrainingComponent::PressDash).GetHandle());
    InputBindings.Add(Input->BindAction(DashAction, ETriggerEvent::Completed, this, &UHeroTrainingComponent::ReleaseDash).GetHandle());
    InputBindings.Add(Input->BindAction(MenuAction, ETriggerEvent::Started, this, &UHeroTrainingComponent::MenuInput).GetHandle());
    Inputs->AddMappingContext(Mapping, 100);
    BoundInput = Input;
}

void UHeroTrainingComponent::PressPrimary()
{
    UHeroTrainingSubsystem* Session = Training();
    if (!IsReady() || !Session || Session->GetFlow().Screen != NovanodeHeroes::TrainingScreen::Playing) return;
    if (ULyraAbilitySystemComponent* Lyra = Cast<ULyraAbilitySystemComponent>(ASC)) Lyra->AbilityInputTagPressed(TAG_TrainingPrimaryInput);
}
void UHeroTrainingComponent::ReleasePrimary()
{
    if (ULyraAbilitySystemComponent* Lyra = Cast<ULyraAbilitySystemComponent>(ASC)) Lyra->AbilityInputTagReleased(TAG_TrainingPrimaryInput);
}
void UHeroTrainingComponent::PressDash()
{
    UHeroTrainingSubsystem* Session = Training();
    if (!IsReady() || !Session || Session->GetFlow().Screen != NovanodeHeroes::TrainingScreen::Playing) return;
    if (ULyraAbilitySystemComponent* Lyra = Cast<ULyraAbilitySystemComponent>(ASC)) Lyra->AbilityInputTagPressed(TAG_TrainingDashInput);
}
void UHeroTrainingComponent::ReleaseDash()
{
    if (ULyraAbilitySystemComponent* Lyra = Cast<ULyraAbilitySystemComponent>(ASC)) Lyra->AbilityInputTagReleased(TAG_TrainingDashInput);
}
void UHeroTrainingComponent::MenuInput() { if (Training()) Training()->TogglePause(); }

void UHeroTrainingComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    GetWorld()->GetTimerManager().ClearTimer(CastTimer);
    ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    if (Pawn && ActiveBodyMontage && Pawn->GetMesh()->GetAnimInstance())
        Pawn->GetMesh()->GetAnimInstance()->Montage_Stop(.1f, ActiveBodyMontage);
    if (UEnhancedInputComponent* Input = BoundInput.Get())
        for (uint32 Handle : InputBindings) Input->RemoveBindingByHandle(Handle);
    APlayerController* Player = Pawn ? Cast<APlayerController>(Pawn->GetController()) : nullptr;
    if (Player && Player->GetLocalPlayer())
        if (UEnhancedInputLocalPlayerSubsystem* Inputs = Player->GetLocalPlayer()->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
            if (Mapping) Inputs->RemoveMappingContext(Mapping);
    if (ASC && Equipment && NativeWeaponBlock().IsValid()) ASC->RemoveLooseGameplayTag(NativeWeaponBlock());
    if (Pawn && Pawn->HasAuthority() && Equipment)
        if (ULyraEquipmentManagerComponent* Manager = Pawn->FindComponentByClass<ULyraEquipmentManagerComponent>()) Manager->UnequipItem(Equipment);
    Equipment = nullptr;
    ASC = nullptr;
    Super::EndPlay(Reason);
}

bool UHeroTrainingComponent::PlayBodyMontage(UAnimMontage* Montage, float Duration)
{
    ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    UAnimInstance* Animation = Pawn && Pawn->GetMesh() ? Pawn->GetMesh()->GetAnimInstance() : nullptr;
    if (!Animation || !Montage || Duration <= 0.f || !Montage->GetSkeleton() ||
        !Pawn->GetMesh()->GetSkeletalMeshAsset() || Montage->GetSkeleton() != Pawn->GetMesh()->GetSkeletalMeshAsset()->GetSkeleton()) return false;
    const float Played = Animation->Montage_Play(Montage, Montage->GetPlayLength() / Duration);
    if (Played <= 0.f) return false;
    ActiveBodyMontage = Montage;
    ++BodyMontagesPlayed;
    return true;
}

void UHeroTrainingComponent::ApplyCooldown(bool Dash, float Duration)
{
    if (!ASC) return;
    const TSubclassOf<UGameplayEffect> Class = Dash ? UHeroTrainingDashCooldown::StaticClass() : UHeroTrainingPrimaryCooldown::StaticClass();
    FGameplayEffectSpecHandle Spec = ASC->MakeOutgoingSpec(Class, 1.f, ASC->MakeEffectContext());
    if (!Spec.IsValid()) return;
    Spec.Data->SetSetByCallerMagnitude(TAG_TrainingCooldownDuration, Duration);
    ASC->ApplyGameplayEffectSpecToSelf(*Spec.Data.Get());
}

float UHeroTrainingComponent::GetCooldownRemaining(bool Dash) const
{
    if (!ASC) return 0.f;
    const FGameplayTagContainer Tags(Dash ? TAG_TrainingDashCD : TAG_TrainingPrimaryCD);
    const TArray<float> Times = ASC->GetActiveEffectsTimeRemaining(FGameplayEffectQuery::MakeQuery_MatchAnyOwningTags(Tags));
    float Remaining = 0.f;
    for (float Value : Times) Remaining = FMath::Max(Remaining, Value);
    return Remaining;
}

bool UHeroTrainingComponent::ExecutePrimary()
{
    if (!GetOwner()->HasAuthority() || !IsReady() || GetCooldownRemaining(false) > 0.f) return false;
    const double Now = GetWorld()->GetTimeSeconds();
    const NovanodeHeroes::CombatRules Before = Rules;
    if (!Rules.TryPrimary(Now)) return false;
    UHeroTrainingData* Data = Training()->GetData();
    const bool Mage = Rules.Selected == NovanodeHeroes::Kit::Mage;
    UAnimMontage* Montage = Mage ? Data->CastMontage.Get() : Data->SwordMontages[Rules.Combo - 1].Get();
    const float Duration = Mage ? .6f : (Rules.Combo == 3 ? .65f : .42f);
    if (!PlayBodyMontage(Montage, Duration)) { Rules = Before; return false; }
    ApplyCooldown(false, static_cast<float>(Rules.PrimaryReadyAt - Now));
    if (Mage) GetWorld()->GetTimerManager().SetTimer(CastTimer, this, &UHeroTrainingComponent::SpawnSpell, .22f, false);
    else SwingAt = Now;
    Feedback(GetWorld(), GetOwner()->GetActorLocation(), Mage);
    return true;
}

void UHeroTrainingComponent::SpawnSpell()
{
    ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    if (!Pawn || !IsReady() || !Pawn->HasAuthority()) return;
    FVector Eye;
    FRotator Aim;
    Pawn->GetActorEyesViewPoint(Eye, Aim);
    const FVector Muzzle = Eye + Aim.Vector() * 85.f;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(TrainingMuzzle), false, Pawn);
    FHitResult Cover;
    if (GetWorld()->SweepSingleByChannel(Cover, Eye, Muzzle, FQuat::Identity, ECC_Visibility,
        FCollisionShape::MakeSphere(12.f), Query)) return;
    FActorSpawnParameters Params;
    Params.Owner = Pawn;
    Params.Instigator = Pawn;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::DontSpawnIfColliding;
    AHeroTrainingProjectile* Projectile = GetWorld()->SpawnActor<AHeroTrainingProjectile>(Muzzle, Aim, Params);
    if (Projectile) Projectile->Source = this;
}

bool UHeroTrainingComponent::ExecuteDash()
{
    if (!GetOwner()->HasAuthority() || !IsReady() || GetCooldownRemaining(true) > 0.f) return false;
    const NovanodeHeroes::CombatRules Before = Rules;
    if (!Rules.TryDash(GetWorld()->GetTimeSeconds())) return false;
    if (!PlayBodyMontage(Training()->GetData()->DashMontage, .38f)) { Rules = Before; return false; }
    ApplyCooldown(true, 2.5f);
    ACharacter* Pawn = CastChecked<ACharacter>(GetOwner());
    FVector Direction = Pawn->GetLastMovementInputVector();
    if (Direction.IsNearlyZero()) Direction = Pawn->GetActorForwardVector();
    Direction.Z = 0.f;
    Pawn->LaunchCharacter(Direction.GetSafeNormal() * 850.f + FVector(0.f, 0.f, 80.f), true, false);
    SwingAt = -100.;
    return true;
}

bool UHeroTrainingComponent::DealDamage(AActor* Target, float Amount, const FHitResult& Hit)
{
    const APawn* SourcePawn = Cast<APawn>(GetOwner());
    const APawn* TargetPawn = Cast<APawn>(Target);
    UAbilitySystemComponent* TargetASC = PawnASC(Target);
    if (!GetOwner()->HasAuthority() || !IsReady() || !TargetPawn || Target == GetOwner() || !TargetASC ||
        !TargetASC->HasAttributeSetForAttribute(ULyraHealthSet::GetHealthAttribute()) ||
        TargetASC->GetNumericAttribute(ULyraHealthSet::GetHealthAttribute()) <= 0.f ||
        PlayerTeam(SourcePawn) == FGenericTeamId::NoTeam || PlayerTeam(TargetPawn) == FGenericTeamId::NoTeam ||
        PlayerTeam(SourcePawn) == PlayerTeam(TargetPawn)) return false;
    FGameplayEffectContextHandle Context = ASC->MakeEffectContext();
    Context.AddHitResult(Hit, true);
    Context.AddSourceObject(Equipment);
    FGameplayEffectSpecHandle Spec = ASC->MakeOutgoingSpec(UHeroTrainingDamageEffect::StaticClass(), 1.f, Context);
    if (!Spec.IsValid()) return false;
    Spec.Data->SetSetByCallerMagnitude(TAG_TrainingDamage, FMath::Clamp(Amount, 0.f, 100.f));
    const float Before = TargetASC->GetNumericAttribute(ULyraHealthSet::GetHealthAttribute());
    ASC->ApplyGameplayEffectSpecToTarget(*Spec.Data.Get(), TargetASC);
    const bool Damaged = TargetASC->GetNumericAttribute(ULyraHealthSet::GetHealthAttribute()) < Before;
    if (Damaged) ++NativeDamageApplications;
    return Damaged;
}

void UHeroTrainingComponent::SweepMelee()
{
    if (!IsReady() || !GetOwner()->HasAuthority() || Rules.Selected != NovanodeHeroes::Kit::Sword) return;
    const double Age = GetWorld()->GetTimeSeconds() - SwingAt;
    if (Age < .10 || Age > .27) return;
    const FVector Start = GetOwner()->GetActorLocation() + GetOwner()->GetActorForwardVector() * 45.f;
    const FVector End = Start + GetOwner()->GetActorForwardVector() * 160.f;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(TrainingSword), false, GetOwner());
    FCollisionObjectQueryParams Objects;
    Objects.AddObjectTypesToQuery(ECC_Pawn);
    TArray<FHitResult> Hits;
    GetWorld()->SweepMultiByObjectType(Hits, Start, End, FQuat::Identity, Objects, FCollisionShape::MakeSphere(55.f), Query);
    for (const FHitResult& Hit : Hits)
    {
        AActor* Target = Hit.GetActor();
        if (!Cast<APawn>(Target)) continue;
        FHitResult Cover;
        if (GetWorld()->LineTraceSingleByChannel(Cover, Start, Target->GetActorLocation(), ECC_Visibility, Query) && Cover.GetActor() != Target) continue;
        if (Rules.FirstHit(Target->GetUniqueID())) DealDamage(Target, Rules.Damage(), Hit);
    }
}

void UHeroTrainingComponent::TickComponent(float Delta, ELevelTick Tick, FActorComponentTickFunction* Function)
{
    Super::TickComponent(Delta, Tick, Function);
    const UHeroTrainingSubsystem* Session = Training();
    if (!Session || !Session->IsTrainingWorld()) return;
    InitializeEquipment();
    BindInput();
    SweepMelee();
    if (ASC && !IsReady())
    {
        GetWorld()->GetTimerManager().ClearTimer(CastTimer);
        SwingAt = -100.;
        ACharacter* Pawn = Cast<ACharacter>(GetOwner());
        if (Pawn && ActiveBodyMontage && Pawn->GetMesh()->GetAnimInstance())
            Pawn->GetMesh()->GetAnimInstance()->Montage_Stop(.1f, ActiveBodyMontage);
        ActiveBodyMontage = nullptr;
    }
}

UHeroTrainingPrimaryAbility::UHeroTrainingPrimaryAbility()
{
    InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerActor;
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
    ActivationPolicy = ELyraAbilityActivationPolicy::OnInputTriggered;
    SetAssetTags(FGameplayTagContainer(TAG_TrainingAction));
}
void UHeroTrainingPrimaryAbility::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* Info,
    const FGameplayAbilityActivationInfo Activation, const FGameplayEventData*)
{
    UHeroTrainingComponent* Combat = Info && Info->AvatarActor.IsValid() ? Info->AvatarActor->FindComponentByClass<UHeroTrainingComponent>() : nullptr;
    const bool Success = Combat && CommitAbility(Handle, Info, Activation) && Combat->ExecutePrimary();
    EndAbility(Handle, Info, Activation, true, !Success);
}
UHeroTrainingDashAbility::UHeroTrainingDashAbility()
{
    InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerActor;
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
    ActivationPolicy = ELyraAbilityActivationPolicy::OnInputTriggered;
    SetAssetTags(FGameplayTagContainer(TAG_TrainingAction));
}
void UHeroTrainingDashAbility::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* Info,
    const FGameplayAbilityActivationInfo Activation, const FGameplayEventData*)
{
    UHeroTrainingComponent* Combat = Info && Info->AvatarActor.IsValid() ? Info->AvatarActor->FindComponentByClass<UHeroTrainingComponent>() : nullptr;
    const bool Success = Combat && CommitAbility(Handle, Info, Activation) && Combat->ExecuteDash();
    EndAbility(Handle, Info, Activation, true, !Success);
}

AHeroTrainingProjectile::AHeroTrainingProjectile()
{
    Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
    SetRootComponent(Collision);
    Collision->InitSphereRadius(12.f);
    Collision->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Collision->SetCollisionObjectType(ECC_WorldDynamic);
    Collision->SetCollisionResponseToAllChannels(ECR_Ignore);
    Collision->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
    Collision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
    UStaticMeshComponent* Visual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ArcaneOrb"));
    Visual->SetupAttachment(Collision);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    Visual->SetStaticMesh(Sphere.Object);
    Visual->SetRelativeScale3D(FVector(.24f));
    Visual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
    Movement->InitialSpeed = 1800.f;
    Movement->MaxSpeed = 1800.f;
    Movement->ProjectileGravityScale = 0.f;
    InitialLifeSpan = 3.f;
}
void AHeroTrainingProjectile::BeginPlay()
{
    Super::BeginPlay();
    Collision->IgnoreActorWhenMoving(GetOwner(), true);
    Collision->OnComponentHit.AddDynamic(this, &AHeroTrainingProjectile::OnHit);
}
void AHeroTrainingProjectile::OnHit(UPrimitiveComponent*, AActor* Other, UPrimitiveComponent*, FVector, const FHitResult& Hit)
{
    if (bConsumed || !HasAuthority() || Other == GetOwner()) return;
    bConsumed = true;
    if (IsValid(Source)) Source->DealDamage(Other, 25.f, Hit);
    Destroy();
}

AHeroTrainingSwordWeapon::AHeroTrainingSwordWeapon()
{
    UStaticMeshComponent* Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Claymore"));
    SetRootComponent(Mesh);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sword(TEXT("/NovanodeHeroes/Imported/SM_Claymore.SM_Claymore"));
    Mesh->SetStaticMesh(Sword.Object);
    Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}
AHeroTrainingMageWeapon::AHeroTrainingMageWeapon()
{
    UStaticMeshComponent* Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ProvisionalStaff"));
    SetRootComponent(Mesh);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    Mesh->SetStaticMesh(Cylinder.Object);
    Mesh->SetRelativeScale3D(FVector(.045f, .045f, .8f));
    Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

UHeroTrainingTeamsComponent::UHeroTrainingTeamsComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickInterval = .25f;
}
void UHeroTrainingTeamsComponent::TickComponent(float Delta, ELevelTick Tick, FActorComponentTickFunction* Function)
{
    Super::TickComponent(Delta, Tick, Function);
    const UHeroTrainingSubsystem* Session = GetWorld()->GetGameInstance()->GetSubsystem<UHeroTrainingSubsystem>();
    const AGameStateBase* State = Cast<AGameStateBase>(GetOwner());
    if (!Session || !Session->IsTrainingWorld() || !State || !State->HasAuthority()) return;
    for (APlayerState* Player : State->PlayerArray)
        if (IGenericTeamAgentInterface* Team = Cast<IGenericTeamAgentInterface>(Player))
        {
            const FGenericTeamId Desired(Player->IsABot() ? 1 : 0);
            if (Team->GetGenericTeamId() != Desired) Team->SetGenericTeamId(Desired);
        }
}
