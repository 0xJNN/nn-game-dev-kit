#include "HeroSandbox.h"
#include "HeroPresentationRules.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "Camera/PlayerCameraManager.h"
#include "Camera/CameraActor.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/DefaultPawn.h"
#include "GameFeatureAction_AddComponents.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Serialization/JsonSerializer.h"
#include "Materials/MaterialInterface.h"
#include "UnrealClient.h"
#include "UObject/UnrealType.h"

namespace
{
int32 CountFrameworkComponent(const AActor* Actor, const TCHAR* PublicClassPath)
{
    UClass* Class = FindObject<UClass>(nullptr, PublicClassPath);
    if (!Actor || !Class) return 0;
    TInlineComponentArray<UActorComponent*> Components(Actor);
    return Components.FilterByPredicate([Class](const UActorComponent* Component)
        { return Component && Component->IsA(Class); }).Num();
}

int32 MeshVertexCount(const USkeletalMeshComponent* Component)
{
    const USkeletalMesh* Mesh = Component ? Component->GetSkeletalMeshAsset() : nullptr;
    const FSkeletalMeshRenderData* Data = Mesh ? Mesh->GetResourceForRendering() : nullptr;
    return Data && !Data->LODRenderData.IsEmpty() ? Data->LODRenderData[0].GetNumVertices() : 0;
}

TArray<UObject*> ObjectArray(UObject* Object, const FName Field)
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

bool WriteReport(const TSharedRef<FJsonObject>& Report, const FString& Output)
{
    FString Json;
    FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&Json));
    return FFileHelper::SaveStringToFile(Json, *Output);
}
}

int32 UHeroSandboxEditorTools::AddOwnedCosmeticAssemblyAction(UClass* ExperienceClass, UClass* ReferenceExperienceClass)
{
#if WITH_EDITOR
    UClass* Base = FindObject<UClass>(nullptr, TEXT("/Script/LyraGame.LyraExperienceDefinition"));
    UClass* ControllerParts = FindObject<UClass>(nullptr, TEXT("/Script/LyraGame.LyraControllerComponent_CharacterParts"));
    if (!Base || !ControllerParts || !ExperienceClass || !ReferenceExperienceClass ||
        !ExperienceClass->IsChildOf(Base) || !ReferenceExperienceClass->IsChildOf(Base) ||
        !ExperienceClass->GetPathName().StartsWith(TEXT("/NovanodeHeroes/Experiences/B_HeroSandbox_v2."))) return 0;
    UObject* Destination = ExperienceClass->GetDefaultObject();
    if (!ObjectArray(Destination, TEXT("Actions")).IsEmpty()) return 0; // Never append twice or replace authored actions.
    UObject* Reference = ReferenceExperienceClass->GetDefaultObject();
    TArray<UObject*> Candidates = ObjectArray(Reference, TEXT("Actions"));
    for (UObject* Set : ObjectArray(Reference, TEXT("ActionSets"))) Candidates.Append(ObjectArray(Set, TEXT("Actions")));
    TArray<FGameFeatureComponentEntry> Selected;
    for (UObject* Candidate : Candidates)
    {
        auto* Action = Cast<UGameFeatureAction_AddComponents>(Candidate);
        FArrayProperty* Entries = Action ? FindFProperty<FArrayProperty>(Action->GetClass(), TEXT("ComponentList")) : nullptr;
        if (!Entries) continue;
        FScriptArrayHelper Array(Entries, Entries->ContainerPtrToValuePtr<void>(Action));
        for (int32 Index = 0; Index < Array.Num(); ++Index)
        {
            const auto* Entry = reinterpret_cast<const FGameFeatureComponentEntry*>(Array.GetRawPtr(Index));
            UClass* Component = Entry->ComponentClass.LoadSynchronous();
            if (Component && Component->IsChildOf(ControllerParts)) Selected.Add(*Entry);
        }
    }
    // Only the documented character-parts controller component. No bot, match,
    // scoreboard, weapon grant, UI or arbitrary experience logic is copied.
    if (Selected.Num() != 1) return 0;
    auto* NewAction = NewObject<UGameFeatureAction_AddComponents>(Destination);
    FArrayProperty* Entries = FindFProperty<FArrayProperty>(NewAction->GetClass(), TEXT("ComponentList"));
    FArrayProperty* Actions = FindFProperty<FArrayProperty>(Destination->GetClass(), TEXT("Actions"));
    FObjectPropertyBase* Inner = Actions ? CastField<FObjectPropertyBase>(Actions->Inner) : nullptr;
    if (!Entries || !Inner) return 0;
    FScriptArrayHelper EntryArray(Entries, Entries->ContainerPtrToValuePtr<void>(NewAction));
    const int32 EntryIndex = EntryArray.AddValue();
    *reinterpret_cast<FGameFeatureComponentEntry*>(EntryArray.GetRawPtr(EntryIndex)) = Selected[0];
    Destination->Modify();
    FScriptArrayHelper ActionArray(Actions, Actions->ContainerPtrToValuePtr<void>(Destination));
    Inner->SetObjectPropertyValue(ActionArray.GetRawPtr(ActionArray.AddValue()), NewAction);
    Destination->MarkPackageDirty();
    return 1;
#else
    return 0;
#endif
}

bool UHeroSandboxEditorTools::ValidateOwnedCosmeticAssemblyAction(UClass* ExperienceClass)
{
    if (!ExperienceClass || !ExperienceClass->GetPathName().StartsWith(TEXT("/NovanodeHeroes/Experiences/B_HeroSandbox_v2."))) return false;
    UClass* Base = FindObject<UClass>(nullptr, TEXT("/Script/LyraGame.LyraControllerComponent_CharacterParts"));
    const TArray<UObject*> Actions = ObjectArray(ExperienceClass->GetDefaultObject(), TEXT("Actions"));
    auto* Action = Actions.Num() == 1 ? Cast<UGameFeatureAction_AddComponents>(Actions[0]) : nullptr;
    FArrayProperty* Entries = Action ? FindFProperty<FArrayProperty>(Action->GetClass(), TEXT("ComponentList")) : nullptr;
    if (!Base || !Entries) return false;
    FScriptArrayHelper Array(Entries, Entries->ContainerPtrToValuePtr<void>(Action));
    if (Array.Num() != 1) return false;
    const auto* Entry = reinterpret_cast<const FGameFeatureComponentEntry*>(Array.GetRawPtr(0));
    UClass* Component = Entry->ComponentClass.LoadSynchronous();
    UClass* Receiver = Entry->ActorClass.LoadSynchronous();
    return Entry->bServerComponent && Component && Component->IsChildOf(Base) &&
        Receiver && Receiver->IsChildOf(AController::StaticClass());
}

void UHeroSandboxEditorTools::FaceOwnedText(UTextRenderComponent* Text, const FVector& Viewer)
{
    if (!Text) return;
    const FVector Here = Text->GetComponentLocation();
    const double Yaw = NovanodeHeroes::TextFacingYaw(Here.X, Here.Y, Viewer.X, Viewer.Y, Text->GetComponentRotation().Yaw);
    Text->SetWorldRotation(FRotator(0., Yaw, 0.));
}
AHeroFacingTextActor::AHeroFacingTextActor()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickInterval = .1f;
}
void AHeroFacingTextActor::FaceEntry(FVector Viewer) { UHeroSandboxEditorTools::FaceOwnedText(GetTextRender(), Viewer); }
void AHeroFacingTextActor::BeginPlay()
{
    Super::BeginPlay();
    if (GetTextRender()->Text.ToString() == TEXT("PRESS PLAY | experience loads automatically"))
        GetTextRender()->SetText(FText::FromString(TEXT("PLAY SESSION | J ATTACK  K DASH | 1 MAGE  2 SWORD")));
}
void AHeroFacingTextActor::Tick(float Delta)
{
    Super::Tick(Delta);
    APlayerController* Player = UGameplayStatics::GetPlayerController(this, 0);
    if (Player && Player->IsLocalController() && Player->PlayerCameraManager)
        UHeroSandboxEditorTools::FaceOwnedText(GetTextRender(), Player->PlayerCameraManager->GetCameraLocation());
}

AHeroTextCalibrationActor::AHeroTextCalibrationActor() { PrimaryActorTick.bCanEverTick = true; }
void AHeroTextCalibrationActor::Tick(float Delta)
{
    Super::Tick(Delta);
    FString Output;
    if (!FParse::Value(FCommandLine::Get(), TEXT("HeroTextCapture="), Output)) return;
    if (StartedAt == 0.) StartedAt = FPlatformTime::Seconds();
    const double Elapsed = FPlatformTime::Seconds() - StartedAt;
    if (Elapsed > 35.)
    {
        TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
        Report->SetStringField(TEXT("state"), TEXT("capture_unknown_timeout_preserve_and_reconcile"));
        WriteReport(Report, Output + TEXT(".json"));
        FPlatformMisc::RequestExit(false);
        return;
    }
    if (bRequested || Elapsed < 4.) return;
    bool bAllowed = GetWorld()->GetOutermost()->GetName() == TEXT("/NovanodeHeroes/Maps/L_TextCalibration_v2") &&
        GetGameInstance() && GetGameInstance()->GetClass() == UGameInstance::StaticClass();
    if (bAllowed && !bCameraPrepared)
    {
        APlayerController* Player = UGameplayStatics::GetPlayerController(this, 0);
        TArray<ACameraActor*> Cameras;
        for (TActorIterator<ACameraActor> It(GetWorld()); It; ++It) Cameras.Add(*It);
        if (Player && Cameras.Num() == 1)
        {
            // GameModeBase otherwise creates an unrelated engine default-pawn
            // sphere. This original-text fixture is camera-only, not gameplay.
            // Remove ONLY their visual component in this owned test world,
            // retaining possession so no spectator/respawn camera is created.
            for (TActorIterator<ADefaultPawn> It(GetWorld()); It; ++It)
                if (It->GetClass() == ADefaultPawn::StaticClass())
                {
                    TInlineComponentArray<UStaticMeshComponent*> Visuals(*It);
                    for (UStaticMeshComponent* Visual : Visuals) Visual->DestroyComponent();
                    ++CalibrationDefaultPawnVisualsRemoved;
                }
            // Camera actors in an editor build also own a hidden editor camera
            // mesh. It is not part of this two-text fixture. Remove only hidden
            // or editor-only ENGINE helper geometry, not arbitrary scene assets.
            TInlineComponentArray<UStaticMeshComponent*> CameraVisuals(Cameras[0]);
            for (UStaticMeshComponent* Visual : CameraVisuals)
                if ((Visual->IsEditorOnly() || Visual->bHiddenInGame) && Visual->GetStaticMesh() &&
                    Visual->GetStaticMesh()->GetPathName().StartsWith(TEXT("/Engine/")))
                {
                    Visual->DestroyComponent();
                    ++CalibrationCameraVisualsRemoved;
                }
            Player->SetViewTarget(Cameras[0]);
            bCameraPrepared = true;
            return; // Let component removal reach the renderer before capture.
        }
    }
    bAllowed = bAllowed && bCameraPrepared;
    int32 Texts = 0, ForeignSkeletal = 0, ForeignStatic = 0, ForeignMaterials = 0, ForeignFonts = 0;
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        TInlineComponentArray<USkeletalMeshComponent*> Skeletal(*It);
        for (const USkeletalMeshComponent* Mesh : Skeletal)
            if (Mesh->GetSkeletalMeshAsset()) { bAllowed = false; ++ForeignSkeletal; }
        TInlineComponentArray<UStaticMeshComponent*> Static(*It);
        for (const UStaticMeshComponent* Mesh : Static)
        {
            if (Mesh->GetStaticMesh() && !Mesh->GetStaticMesh()->GetPathName().StartsWith(TEXT("/Engine/BasicShapes/")))
                { bAllowed = false; ++ForeignStatic; }
            for (int32 Index = 0; Index < Mesh->GetNumMaterials(); ++Index)
                if (const UMaterialInterface* Material = Mesh->GetMaterial(Index))
                    if (!Material->GetPathName().StartsWith(TEXT("/Engine/")) &&
                        !Material->GetPathName().StartsWith(TEXT("/NovanodeHeroes/PresentationV2/")))
                        { bAllowed = false; ++ForeignMaterials; }
        }
        TInlineComponentArray<UTextRenderComponent*> Components(*It);
        Texts += Components.Num();
        for (const UTextRenderComponent* Text : Components)
        {
            FObjectPropertyBase* FontProperty = FindFProperty<FObjectPropertyBase>(Text->GetClass(), TEXT("Font"));
            UObject* Font = FontProperty ? FontProperty->GetObjectPropertyValue_InContainer(Text) : nullptr;
            if (!Font || !Font->GetPathName().StartsWith(TEXT("/Engine/"))) { bAllowed = false; ++ForeignFonts; }
        }
    }
    if (!bAllowed || Texts != 2)
    {
        TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
        Report->SetStringField(TEXT("state"), TEXT("capture_refused_foreign_visuals_or_wrong_scene"));
        Report->SetNumberField(TEXT("text_components"), Texts);
        Report->SetNumberField(TEXT("foreign_skeletal_meshes"), ForeignSkeletal);
        Report->SetNumberField(TEXT("foreign_static_meshes"), ForeignStatic);
        Report->SetNumberField(TEXT("foreign_materials"), ForeignMaterials);
        Report->SetNumberField(TEXT("foreign_fonts"), ForeignFonts);
        Report->SetBoolField(TEXT("camera_prepared"), bCameraPrepared);
        Report->SetNumberField(TEXT("calibration_default_pawn_visuals_removed"), CalibrationDefaultPawnVisualsRemoved);
        Report->SetNumberField(TEXT("calibration_camera_visuals_removed"), CalibrationCameraVisualsRemoved);
        WriteReport(Report, Output + TEXT(".json"));
        FPlatformMisc::RequestExit(false);
        return;
    }
    // Do not save a black loading-screen frame and call it a text verification.
    if (!GEngine || !GEngine->GameViewport || GEngine->GameViewport->bDisableWorldRendering) return;
    bRequested = true;
    ScreenshotHandle = FScreenshotRequest::OnScreenshotRequestProcessed().AddUObject(this, &AHeroTextCalibrationActor::FinishCapture);
    FScreenshotRequest::RequestScreenshot(Output, false, false);
}
void AHeroTextCalibrationActor::FinishCapture()
{
    FString Output;
    if (!FParse::Value(FCommandLine::Get(), TEXT("HeroTextCapture="), Output)) return;
    TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
    const bool bSaved = IFileManager::Get().FileSize(*Output) > 0;
    Report->SetStringField(TEXT("state"), bSaved ? TEXT("original_text_calibration_captured") : TEXT("capture_missing_unknown"));
    Report->SetBoolField(TEXT("foreign_visuals_excluded"), true);
    Report->SetNumberField(TEXT("calibration_default_pawn_visuals_removed"), CalibrationDefaultPawnVisualsRemoved);
    Report->SetNumberField(TEXT("calibration_camera_visuals_removed"), CalibrationCameraVisualsRemoved);
    Report->SetBoolField(TEXT("visual_verified"), false);
    WriteReport(Report, Output + TEXT(".json"));
    FPlatformMisc::RequestExit(false);
}
void AHeroTextCalibrationActor::EndPlay(const EEndPlayReason::Type Reason)
{
    if (ScreenshotHandle.IsValid()) FScreenshotRequest::OnScreenshotRequestProcessed().Remove(ScreenshotHandle);
    Super::EndPlay(Reason);
}

void AHeroSandboxDirector::RunPresentationProbe()
{
    FString Output;
    if (GetNetMode() != NM_Standalone || !FParse::Value(FCommandLine::Get(), TEXT("HeroPresentationProbe="), Output)) return;
    if (PresentationProbeStartedAt == 0.) PresentationProbeStartedAt = FPlatformTime::Seconds();
    const double Elapsed = FPlatformTime::Seconds() - PresentationProbeStartedAt;
    ACharacter* Pawn = UGameplayStatics::GetPlayerCharacter(this, 0);
    APlayerController* Controller = UGameplayStatics::GetPlayerController(this, 0);
    const bool bRenderedProbe = FParse::Param(FCommandLine::Get(), TEXT("HeroRenderedProbe"));
    if ((Elapsed < (bRenderedProbe ? 8. : 2.) || !Pawn || !Controller) && Elapsed < 20.) return;

    TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
    Report->SetStringField(TEXT("state"), TEXT("presentation_structure_observed_not_visual_approval"));
    Report->SetBoolField(TEXT("pawn_exists"), Pawn != nullptr);
    Report->SetBoolField(TEXT("pawn_possessed"), Pawn && Controller && Controller->GetPawn() == Pawn);
    Report->SetBoolField(TEXT("ability_system_present"), Pawn && UAbilitySystemBlueprintLibrary::GetAbilitySystemComponent(Pawn));
    Report->SetNumberField(TEXT("controller_character_parts_components"), CountFrameworkComponent(Controller, TEXT("/Script/LyraGame.LyraControllerComponent_CharacterParts")));
    Report->SetNumberField(TEXT("pawn_character_parts_components"), CountFrameworkComponent(Pawn, TEXT("/Script/LyraGame.LyraPawnComponent_CharacterParts")));
    Report->SetNumberField(TEXT("pawn_hero_components"), CountFrameworkComponent(Pawn, TEXT("/Script/LyraGame.LyraHeroComponent")));
    Report->SetNumberField(TEXT("pawn_equipment_components"), CountFrameworkComponent(Pawn, TEXT("/Script/LyraGame.LyraEquipmentManagerComponent")));
    Report->SetNumberField(TEXT("controller_weapon_state_components"), CountFrameworkComponent(Controller, TEXT("/Script/LyraGame.LyraWeaponStateComponent")));
    Report->SetBoolField(TEXT("camera_manager_present"), Controller && Controller->PlayerCameraManager);
    if (Pawn && Controller && Controller->PlayerCameraManager)
    {
        const FVector Camera = Controller->PlayerCameraManager->GetCameraLocation();
        Report->SetNumberField(TEXT("camera_to_pawn_distance_cm"), FVector::Distance(Camera, Pawn->GetActorLocation()));
        Report->SetNumberField(TEXT("camera_behind_pawn_dot_cm"), FVector::DotProduct(Pawn->GetActorLocation() - Camera, Pawn->GetActorForwardVector()));
        Report->SetBoolField(TEXT("camera_view_target_is_pawn"), Controller->GetViewTarget() == Pawn);
    }
    TArray<AActor*> Actors;
    if (Pawn)
    {
        Actors.Add(Pawn);
        TArray<AActor*> Attached;
        Pawn->GetAttachedActors(Attached, true, true);
        Actors.Append(Attached);
    }
    int32 SkeletalComponents = 0, GeometryComponents = 0, VisibleBodyComponents = 0, AttachedBodyActors = 0;
    int32 GeometryVertices = 0, VisibleCharacterBodies = 0, AnimatedCharacterBodies = 0, RecentlyRenderedBodies = 0;
    for (AActor* Actor : Actors)
    {
        TInlineComponentArray<USkeletalMeshComponent*> Components(Actor);
        bool bBodyActor = false;
        for (USkeletalMeshComponent* Component : Components)
        {
            ++SkeletalComponents;
            const int32 Vertices = MeshVertexCount(Component);
            if (Vertices > 0)
            {
                ++GeometryComponents;
                GeometryVertices += Vertices;
                bBodyActor = true;
                if (!Actor->IsHidden() && Component->IsVisible() && !Component->bHiddenInGame && !Component->bOwnerNoSee)
                {
                    ++VisibleBodyComponents;
                    if (Actor != Pawn && Vertices >= 256)
                    {
                        ++VisibleCharacterBodies;
                        if (Component->GetAnimInstance() || Component->LeaderPoseComponent.IsValid()) ++AnimatedCharacterBodies;
                        if (Component->WasRecentlyRendered(.5f)) ++RecentlyRenderedBodies;
                    }
                }
            }
        }
        if (Actor != Pawn && bBodyActor) ++AttachedBodyActors;
    }
    Report->SetNumberField(TEXT("skeletal_component_count"), SkeletalComponents);
    Report->SetNumberField(TEXT("skeletal_geometry_component_count"), GeometryComponents);
    Report->SetNumberField(TEXT("skeletal_geometry_vertices"), GeometryVertices);
    Report->SetNumberField(TEXT("owner_visible_body_components"), VisibleBodyComponents);
    Report->SetNumberField(TEXT("attached_body_actor_count"), AttachedBodyActors);
    Report->SetNumberField(TEXT("visible_character_body_components"), VisibleCharacterBodies);
    Report->SetNumberField(TEXT("animated_character_body_components"), AnimatedCharacterBodies);
    Report->SetNumberField(TEXT("recently_rendered_character_body_components"), RecentlyRenderedBodies);
    Report->SetBoolField(TEXT("rendered_probe_requested"), bRenderedProbe);
    Report->SetBoolField(TEXT("usable_character_body_present"), NovanodeHeroes::HasUsableBody(
        CountFrameworkComponent(Controller, TEXT("/Script/LyraGame.LyraControllerComponent_CharacterParts")),
        AttachedBodyActors, VisibleCharacterBodies, AnimatedCharacterBodies));
    int32 TextCount = 0, ReversedToEntryCount = 0;
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        TInlineComponentArray<UTextRenderComponent*> Texts(*It);
        for (const UTextRenderComponent* Text : Texts)
        {
            ++TextCount;
            // Direction check only, calibrated separately with original text rendering.
            if (Text->GetForwardVector().X < -.5f) ++ReversedToEntryCount;
        }
    }
    Report->SetNumberField(TEXT("world_text_components"), TextCount);
    Report->SetNumberField(TEXT("world_text_forward_negative_x"), ReversedToEntryCount);
    Report->SetBoolField(TEXT("visual_verified"), false);
    Report->SetBoolField(TEXT("shader_problem_established"), false);
    Report->SetBoolField(TEXT("sample_content_exported"), false);
    FString Json;
    FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&Json));
    FFileHelper::SaveStringToFile(Json, *Output);
    FPlatformMisc::RequestExit(false);
}
