#include "HeroTraining.h"

#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Equipment/LyraEquipmentDefinition.h"
#include "GameFeatureAction_AddComponents.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameStateBase.h"
#include "Components/SkeletalMeshComponent.h"
#include "UObject/Package.h"
#include "UObject/UnrealType.h"

namespace
{
constexpr const TCHAR* Root = TEXT("/NovanodeHeroes/TrainingV3/");

bool Owned(const UObject* Object) { return Object && Object->GetOutermost()->GetName().StartsWith(Root); }

TArray<UObject*> ObjectArray(UObject* Object, FName Field)
{
    TArray<UObject*> Result;
    FArrayProperty* Property = Object ? FindFProperty<FArrayProperty>(Object->GetClass(), Field) : nullptr;
    FObjectPropertyBase* Inner = Property ? CastField<FObjectPropertyBase>(Property->Inner) : nullptr;
    if (!Inner) return Result;
    FScriptArrayHelper Array(Property, Property->ContainerPtrToValuePtr<void>(Object));
    if (Array.Num() > 128) return Result;
    for (int32 Index = 0; Index < Array.Num(); ++Index)
        if (UObject* Value = Inner->GetObjectPropertyValue(Array.GetRawPtr(Index))) Result.Add(Value);
    return Result;
}

TArray<UObject*> ReferenceActions(UClass* Experience)
{
    UObject* Default = Experience ? Experience->GetDefaultObject() : nullptr;
    TArray<UObject*> Result = ObjectArray(Default, TEXT("Actions"));
    for (UObject* Set : ObjectArray(Default, TEXT("ActionSets"))) Result.Append(ObjectArray(Set, TEXT("Actions")));
    return Result;
}

UObject* ObjectField(UObject* Object, FName Field)
{
    FObjectPropertyBase* Property = Object ? FindFProperty<FObjectPropertyBase>(Object->GetClass(), Field) : nullptr;
    return Property ? Property->GetObjectPropertyValue_InContainer(Object) : nullptr;
}

FArrayProperty* ComponentList(UGameFeatureAction_AddComponents* Action)
{
    return Action ? FindFProperty<FArrayProperty>(Action->GetClass(), TEXT("ComponentList")) : nullptr;
}

FString CanonicalBone(FString Name)
{
    int32 Colon = INDEX_NONE;
    if (Name.FindLastChar(TEXT(':'), Colon)) Name = Name.Mid(Colon + 1);
    FString Result;
    for (TCHAR Character : Name) if (FChar::IsAlnum(Character)) Result.AppendChar(FChar::ToLower(Character));
    return Result;
}
}

USkeletalMesh* UHeroTrainingEditorTools::GetPlayerRetargetMesh(UClass* ReferenceExperience)
{
    UObject* PawnData = ObjectField(ReferenceExperience ? ReferenceExperience->GetDefaultObject() : nullptr, TEXT("DefaultPawnData"));
    UClass* PawnClass = Cast<UClass>(ObjectField(PawnData, TEXT("PawnClass")));
    const ACharacter* Pawn = PawnClass ? Cast<ACharacter>(PawnClass->GetDefaultObject()) : nullptr;
    USkeletalMesh* Mesh = Pawn && Pawn->GetMesh() ? Pawn->GetMesh()->GetSkeletalMeshAsset() : nullptr;
    return Mesh && Mesh->GetRefSkeleton().GetNum() >= 50 ? Mesh : nullptr;
}

UClass* UHeroTrainingEditorTools::GetStockBotComponentClass(UClass* ReferenceExperience)
{
    UClass* Base = LoadClass<UActorComponent>(nullptr, TEXT("/Script/LyraGame.LyraBotCreationComponent"));
    UClass* Result = nullptr;
    int32 Count = 0;
    for (UObject* Candidate : ReferenceActions(ReferenceExperience))
    {
        auto* Action = Cast<UGameFeatureAction_AddComponents>(Candidate);
        FArrayProperty* Entries = ComponentList(Action);
        if (!Entries) continue;
        FScriptArrayHelper Array(Entries, Entries->ContainerPtrToValuePtr<void>(Action));
        for (int32 Index = 0; Index < Array.Num(); ++Index)
        {
            const auto* Entry = reinterpret_cast<const FGameFeatureComponentEntry*>(Array.GetRawPtr(Index));
            UClass* Component = Entry->ComponentClass.LoadSynchronous();
            if (Base && Component && Component->IsChildOf(Base)) { Result = Component; ++Count; }
        }
    }
    return Count == 1 ? Result : nullptr;
}

bool UHeroTrainingEditorTools::ConfigureExperience(UClass* OwnedExperience, UClass* ReferenceExperience, UClass* OwnedBots)
{
#if WITH_EDITOR
    if (!Owned(OwnedExperience) || !Owned(OwnedBots) || !ReferenceExperience ||
        !ReferenceExperience->GetPathName().StartsWith(TEXT("/ShooterCore/Experiences/B_ShooterGame_Elimination."))) return false;
    UClass* BotBase = LoadClass<UActorComponent>(nullptr, TEXT("/Script/LyraGame.LyraBotCreationComponent"));
    if (!BotBase || !OwnedBots->IsChildOf(BotBase)) return false;
    UObject* Destination = OwnedExperience->GetDefaultObject();
    FArrayProperty* Actions = FindFProperty<FArrayProperty>(Destination->GetClass(), TEXT("Actions"));
    FObjectPropertyBase* Inner = Actions ? CastField<FObjectPropertyBase>(Actions->Inner) : nullptr;
    if (!Inner || !ObjectArray(Destination, TEXT("Actions")).IsEmpty() || !ObjectArray(Destination, TEXT("ActionSets")).IsEmpty()) return false;
    const TArray<UObject*> Reference = ReferenceActions(ReferenceExperience);
    if (Reference.Num() != 8 || !ComponentList(NewObject<UGameFeatureAction_AddComponents>(GetTransientPackage()))) return false;
    FScriptArrayHelper Output(Actions, Actions->ContainerPtrToValuePtr<void>(Destination));
    int32 ReplacedBots = 0;
    for (UObject* Candidate : Reference)
    {
        UObject* Copy = DuplicateObject(Candidate, Destination);
        if (!Copy) return false;
        if (auto* Action = Cast<UGameFeatureAction_AddComponents>(Copy))
        {
            FArrayProperty* Entries = ComponentList(Action);
            if (!Entries) return false;
            FScriptArrayHelper Array(Entries, Entries->ContainerPtrToValuePtr<void>(Action));
            for (int32 Index = 0; Index < Array.Num(); ++Index)
            {
                auto* Entry = reinterpret_cast<FGameFeatureComponentEntry*>(Array.GetRawPtr(Index));
                UClass* Component = Entry->ComponentClass.LoadSynchronous();
                if (Component && Component->IsChildOf(BotBase)) { Entry->ComponentClass = OwnedBots; ++ReplacedBots; }
            }
        }
        Inner->SetObjectPropertyValue(Output.GetRawPtr(Output.AddValue()), Copy);
    }
    if (ReplacedBots != 1) return false;
    auto* Addition = NewObject<UGameFeatureAction_AddComponents>(Destination);
    FArrayProperty* Entries = ComponentList(Addition);
    FScriptArrayHelper Array(Entries, Entries->ContainerPtrToValuePtr<void>(Addition));
    FGameFeatureComponentEntry Human;
    Human.ActorClass = ACharacter::StaticClass();
    Human.ComponentClass = UHeroTrainingComponent::StaticClass();
    Human.bClientComponent = true;
    Human.bServerComponent = true;
    *reinterpret_cast<FGameFeatureComponentEntry*>(Array.GetRawPtr(Array.AddValue())) = Human;
    FGameFeatureComponentEntry Teams;
    Teams.ActorClass = AGameStateBase::StaticClass();
    Teams.ComponentClass = UHeroTrainingTeamsComponent::StaticClass();
    Teams.bClientComponent = false;
    Teams.bServerComponent = true;
    *reinterpret_cast<FGameFeatureComponentEntry*>(Array.GetRawPtr(Array.AddValue())) = Teams;
    Inner->SetObjectPropertyValue(Output.GetRawPtr(Output.AddValue()), Addition);
    Destination->MarkPackageDirty();
    return true;
#else
    return false;
#endif
}

bool UHeroTrainingEditorTools::ConfigureAbilitySet(UObject* OwnedSet)
{
#if WITH_EDITOR
    if (!Owned(OwnedSet)) return false;
    FArrayProperty* Property = FindFProperty<FArrayProperty>(OwnedSet->GetClass(), TEXT("GrantedGameplayAbilities"));
    FStructProperty* Entry = Property ? CastField<FStructProperty>(Property->Inner) : nullptr;
    FClassProperty* Ability = Entry ? FindFProperty<FClassProperty>(Entry->Struct, TEXT("Ability")) : nullptr;
    FIntProperty* Level = Entry ? FindFProperty<FIntProperty>(Entry->Struct, TEXT("AbilityLevel")) : nullptr;
    FStructProperty* Input = Entry ? FindFProperty<FStructProperty>(Entry->Struct, TEXT("InputTag")) : nullptr;
    if (!Ability || !Level || !Input || Input->Struct != FGameplayTag::StaticStruct()) return false;
    FScriptArrayHelper Array(Property, Property->ContainerPtrToValuePtr<void>(OwnedSet));
    if (Array.Num() != 0) return false;
    for (int32 Index = 0; Index < 2; ++Index)
    {
        void* Row = Array.GetRawPtr(Array.AddValue());
        Ability->SetObjectPropertyValue_InContainer(Row, Index == 0 ? UHeroTrainingPrimaryAbility::StaticClass() : UHeroTrainingDashAbility::StaticClass());
        Level->SetPropertyValue_InContainer(Row, 1);
        *Input->ContainerPtrToValuePtr<FGameplayTag>(Row) = FGameplayTag::RequestGameplayTag(Index == 0 ?
            TEXT("InputTag.Novanode.Training.Primary") : TEXT("InputTag.Novanode.Training.Dash"));
    }
    OwnedSet->MarkPackageDirty();
    return true;
#else
    return false;
#endif
}

bool UHeroTrainingEditorTools::ConfigureEquipment(UClass* OwnedEquipment, UObject* OwnedSet, bool Mage, USkeletalMesh* TargetMesh)
{
#if WITH_EDITOR
    if (!Owned(OwnedEquipment) || !Owned(OwnedSet) || !OwnedEquipment->IsChildOf(ULyraEquipmentDefinition::StaticClass()) || !TargetMesh) return false;
    UObject* Default = OwnedEquipment->GetDefaultObject();
    FArrayProperty* Sets = FindFProperty<FArrayProperty>(Default->GetClass(), TEXT("AbilitySetsToGrant"));
    FObjectPropertyBase* Inner = Sets ? CastField<FObjectPropertyBase>(Sets->Inner) : nullptr;
    FArrayProperty* Actors = FindFProperty<FArrayProperty>(Default->GetClass(), TEXT("ActorsToSpawn"));
    FStructProperty* ActorType = Actors ? CastField<FStructProperty>(Actors->Inner) : nullptr;
    if (!Inner || !ActorType || ActorType->Struct != FLyraEquipmentActorToSpawn::StaticStruct()) return false;
    FScriptArrayHelper SetArray(Sets, Sets->ContainerPtrToValuePtr<void>(Default));
    FScriptArrayHelper ActorArray(Actors, Actors->ContainerPtrToValuePtr<void>(Default));
    if (SetArray.Num() || ActorArray.Num()) return false;
    const FName Hand = ResolveBone(TargetMesh, {TEXT("hand_r"), TEXT("RightHand"), TEXT("hand.R")});
    if (Hand.IsNone()) return false;
    FLyraEquipmentActorToSpawn Visual;
    Visual.ActorToSpawn = Mage ? AHeroTrainingMageWeapon::StaticClass() : AHeroTrainingSwordWeapon::StaticClass();
    Visual.AttachSocket = Hand;
    if (Mage) Visual.AttachTransform = FTransform(FRotator::ZeroRotator, FVector(0.f, 0.f, -30.f), FVector(.045f, .045f, .8f));
    else
    {
        UStaticMesh* Sword = LoadObject<UStaticMesh>(nullptr, TEXT("/NovanodeHeroes/Imported/SM_Claymore.SM_Claymore"));
        if (!Sword) return false;
        const FBox Bounds = Sword->GetBoundingBox();
        const FVector Size = Bounds.GetSize();
        if (!Bounds.IsValid || Size.Z < 1.f || Size.Z < FMath::Max(Size.X, Size.Y)) return false;
        const float Scale = 120.f / Size.Z;
        const FVector Handle(Bounds.GetCenter().X, Bounds.GetCenter().Y, Bounds.Min.Z + Size.Z * .12f);
        const FQuat Rotation = FQuat::FindBetweenNormals(FVector::UpVector, FVector::ForwardVector);
        Visual.AttachTransform = FTransform(Rotation, -Rotation.RotateVector(Handle * Scale), FVector(Scale));
    }
    Inner->SetObjectPropertyValue(SetArray.GetRawPtr(SetArray.AddValue()), OwnedSet);
    *reinterpret_cast<FLyraEquipmentActorToSpawn*>(ActorArray.GetRawPtr(ActorArray.AddValue())) = Visual;
    Default->MarkPackageDirty();
    return true;
#else
    return false;
#endif
}

FName UHeroTrainingEditorTools::ResolveBone(USkeletalMesh* Mesh, const TArray<FString>& Candidates)
{
    if (!Mesh || Candidates.Num() > 24) return NAME_None;
    const FReferenceSkeleton& Skeleton = Mesh->GetRefSkeleton();
    for (const FString& Candidate : Candidates)
        for (int32 Index = 0; Index < Skeleton.GetNum(); ++Index)
            if (CanonicalBone(Skeleton.GetBoneName(Index).ToString()) == CanonicalBone(Candidate)) return Skeleton.GetBoneName(Index);
    return NAME_None;
}

FName UHeroTrainingEditorTools::GetAttackSlot(USkeletalMesh* Mesh)
{
    const USkeleton* Skeleton = Mesh ? Mesh->GetSkeleton() : nullptr;
    if (!Skeleton) return NAME_None;
    for (FName Candidate : {FName(TEXT("UpperBody")), FName(TEXT("FullBody")), FName(TEXT("DefaultSlot"))})
        for (const FAnimSlotGroup& Group : Skeleton->GetSlotGroups()) if (Group.SlotNames.Contains(Candidate)) return Candidate;
    return NAME_None;
}

UAnimMontage* UHeroTrainingEditorTools::CreateOwnedMontage(UAnimSequence* Sequence, const FString& Name, FName Slot)
{
#if WITH_EDITOR
    if (!Owned(Sequence) || !Sequence->GetSkeleton() || Slot.IsNone() || !Name.StartsWith(TEXT("AM_HeroTraining_")) ||
        Name.Contains(TEXT("/")) || Name.Contains(TEXT(".")) || Sequence->GetPlayLength() <= 0.f) return nullptr;
    const FString PackageName = FString(Root) + TEXT("Montages/") + Name;
    if (FindPackage(nullptr, *PackageName)) return nullptr;
    UAnimMontage* Temporary = UAnimMontage::CreateSlotAnimationAsDynamicMontage(Sequence, Slot, .08f, .1f, 1.f, 1);
    if (!Temporary) return nullptr;
    UPackage* Package = CreatePackage(*PackageName);
    UAnimMontage* Result = DuplicateObject<UAnimMontage>(Temporary, Package, *Name);
    if (!Result) return nullptr;
    Result->SetFlags(RF_Public | RF_Standalone);
    FAssetRegistryModule::AssetCreated(Result);
    Result->MarkPackageDirty();
    return Result;
#else
    return nullptr;
#endif
}
