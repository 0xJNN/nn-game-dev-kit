#include "TrainingReflectionAdapter.h"
#include "TrainingLobby.h"

#if WITH_EDITOR
#include "AIController.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetToolsModule.h"
#include "Engine/Blueprint.h"
#include "Engine/AssetManagerTypes.h"
#include "Engine/World.h"
#include "Factories/BlueprintFactory.h"
#include "FileHelpers.h"
#include "GameFeatureAction_AddComponents.h"
#include "GameFeatureData.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/WorldSettings.h"
#include "InputAction.h"
#include "InputCoreTypes.h"
#include "InputMappingContext.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "UObject/UnrealType.h"

namespace
{
constexpr const TCHAR* OwnedRoot = TEXT("/NovanodeTraining/");
constexpr const TCHAR* FrontPath = TEXT("/Game/System/FrontEnd/B_LyraFrontEnd_Experience.B_LyraFrontEnd_Experience");
constexpr const TCHAR* ShooterPath = TEXT("/ShooterCore/Experiences/B_ShooterGame_Elimination.B_ShooterGame_Elimination_C");

bool Owned(const UObject* Object)
{
    return Object && Object->GetOutermost()->GetName().StartsWith(OwnedRoot);
}

TArray<UObject*> ObjectArray(UObject* Object, FName Name)
{
    auto* Property = Object ? FindFProperty<FArrayProperty>(Object->GetClass(), Name) : nullptr;
    auto* Inner = Property ? CastField<FObjectPropertyBase>(Property->Inner) : nullptr;
    TArray<UObject*> Result;
    if (!Inner) return Result;
    FScriptArrayHelper Array(Property, Property->ContainerPtrToValuePtr<void>(Object));
    for (int32 Index = 0; Index < Array.Num() && Index < 128; ++Index)
        Result.Add(Inner->GetObjectPropertyValue(Array.GetRawPtr(Index)));
    return Result;
}

bool SetObjects(UObject* Object, FName Name, const TArray<UObject*>& Values)
{
    if (!Owned(Object)) return false;
    auto* Property = FindFProperty<FArrayProperty>(Object->GetClass(), Name);
    auto* Inner = Property ? CastField<FObjectPropertyBase>(Property->Inner) : nullptr;
    if (!Inner) return false;
    FScriptArrayHelper Array(Property, Property->ContainerPtrToValuePtr<void>(Object));
    Array.EmptyValues();
    for (UObject* Value : Values) Inner->SetObjectPropertyValue(Array.GetRawPtr(Array.AddValue()), Value);
    return true;
}

TArray<FGameFeatureComponentEntry*> ComponentEntries(UObject* Action)
{
    TArray<FGameFeatureComponentEntry*> Result;
    if (!Cast<UGameFeatureAction_AddComponents>(Action) || !UTrainingReflectionAdapter::HasComponentEntrySchema()) return Result;
    auto* Property = FindFProperty<FArrayProperty>(Action->GetClass(), TEXT("ComponentList"));
    FScriptArrayHelper Array(Property, Property->ContainerPtrToValuePtr<void>(Action));
    for (int32 Index = 0; Index < Array.Num(); ++Index)
        Result.Add(reinterpret_cast<FGameFeatureComponentEntry*>(Array.GetRawPtr(Index)));
    return Result;
}

UObject* ObjectField(UObject* Object, FName Name)
{
    auto* Property = Object ? FindFProperty<FObjectPropertyBase>(Object->GetClass(), Name) : nullptr;
    return Property ? Property->GetObjectPropertyValue_InContainer(Object) : nullptr;
}

bool SetObject(UObject* Object, FName Name, UObject* Value)
{
    auto* Property = Owned(Object) ? FindFProperty<FObjectPropertyBase>(Object->GetClass(), Name) : nullptr;
    if (!Property || (Value && !Value->IsA(Property->PropertyClass))) return false;
    Property->SetObjectPropertyValue_InContainer(Object, Value);
    return true;
}

bool SetSoftClass(UObject* Object, FName Name, UClass* Value)
{
    auto* Property = Owned(Object) ? FindFProperty<FSoftClassProperty>(Object->GetClass(), Name) : nullptr;
    if (!Property || !Value || !Value->IsChildOf(Property->MetaClass)) return false;
    Property->SetPropertyValue_InContainer(Object, FSoftObjectPtr(Value));
    return true;
}

UBlueprint* Blueprint(const FString& Folder, const FString& Name, UClass* Parent, TArray<UObject*>& Created)
{
    if (!Parent) return nullptr;
    UBlueprintFactory* Factory = NewObject<UBlueprintFactory>();
    Factory->ParentClass = Parent;
    auto* Result = Cast<UBlueprint>(FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get().CreateAsset(
        Name, FString(OwnedRoot) + Folder, UBlueprint::StaticClass(), Factory));
    if (Result) Created.Add(Result);
    return Result;
}

template<class T> T* Data(const FString& Folder, const FString& Name, TArray<UObject*>& Created)
{
    UPackage* Package = CreatePackage(*(FString(OwnedRoot) + (Folder.IsEmpty() ? TEXT("") : Folder + TEXT("/")) + Name));
    T* Result = NewObject<T>(Package, *Name, RF_Public | RF_Standalone);
    FAssetRegistryModule::AssetCreated(Result);
    Created.Add(Result);
    return Result;
}

UObject* Duplicate(const TCHAR* Source, const FString& Folder, const FString& Name, TArray<UObject*>& Created)
{
    UObject* Original = LoadObject<UObject>(nullptr, Source);
    if (!Original) return nullptr;
    UObject* Result = FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get().DuplicateAsset(
        Name, FString(OwnedRoot) + Folder, Original);
    if (Result) Created.Add(Result);
    return Result;
}

bool EnableFeature(UObject* Experience)
{
    auto* Property = FindFProperty<FArrayProperty>(Experience->GetClass(), TEXT("GameFeaturesToEnable"));
    if (!Property || !CastField<FStrProperty>(Property->Inner)) return false;
    auto* Names = Property->ContainerPtrToValuePtr<TArray<FString>>(Experience);
    Names->AddUnique(TEXT("NovanodeTraining"));
    return true;
}
}
#endif

FString UTrainingReflectionAdapter::PrepareOwnedAssets()
{
#if WITH_EDITOR
    if (!HasComponentEntrySchema()) return TEXT("{\"state\":\"blocked\",\"reason\":\"component_schema\"}");
    // A preparation is single-use. The launcher additionally refuses ANY pre-existing owned Content.
    UClass* SourceClass = LoadClass<UObject>(nullptr, ShooterPath);
    UObject* Shooter = SourceClass ? SourceClass->GetDefaultObject() : nullptr;
    UObject* PawnData = ObjectField(Shooter, TEXT("DefaultPawnData"));
    UClass* BotBase = LoadClass<UActorComponent>(nullptr, TEXT("/Script/LyraGame.LyraBotCreationComponent"));
    UClass* TeamBase = LoadClass<UActorComponent>(nullptr, TEXT("/Script/LyraGame.LyraTeamCreationComponent"));
    UClass* FrontBase = LoadClass<UActorComponent>(nullptr, TEXT("/Script/LyraGame.LyraFrontendStateComponent"));
    if (!Shooter || !PawnData || !BotBase || !TeamBase || !FrontBase) return TEXT("{\"state\":\"blocked\",\"reason\":\"reference_classes\"}");

    TArray<UObject*> Created;
    UClass* BotController = nullptr;
    TArray<UObject*> SafeActions;
    auto* Teams = NewObject<UGameFeatureAction_AddComponents>();
    for (UObject* Action : ObjectArray(Shooter, TEXT("Actions")))
        for (auto* Entry : ComponentEntries(Action))
        {
            UClass* Component = Entry->ComponentClass.LoadSynchronous();
            if (Component && Component->IsChildOf(BotBase))
                BotController = Cast<UClass>(ObjectField(Component->GetDefaultObject(), TEXT("BotControllerClass")));
            if (Component && Component->IsChildOf(TeamBase))
                AddComponent(Teams, Entry->ActorClass.LoadSynchronous(), Component, Entry->bClientComponent, Entry->bServerComponent);
        }
    // Selected compatible ActionSets remain REFERENCES, never flattened/copied.
    TArray<UObject*> Sets;
    const TSet<FString> AllowedSets = { TEXT("LAS_ShooterGame_SharedInput"), TEXT("LAS_ShooterGame_StandardComponents"), TEXT("LAS_ShooterGame_StandardHUD") };
    for (UObject* Set : ObjectArray(Shooter, TEXT("ActionSets")))
        if (Set && AllowedSets.Contains(Set->GetName()))
        {
            // A referenced set must not also spawn bots or override team creation.
            for (UObject* Action : ObjectArray(Set, TEXT("Actions")))
                for (auto* Entry : ComponentEntries(Action))
                    if (UClass* Component = Entry->ComponentClass.LoadSynchronous())
                        if (Component->IsChildOf(BotBase) || Component->IsChildOf(TeamBase))
                            return TEXT("{\"state\":\"blocked\",\"reason\":\"incompatible_action_set\"}");
            Sets.Add(Set);
        }
    if (!BotController || Sets.Num() != AllowedSets.Num()) return TEXT("{\"state\":\"blocked\",\"reason\":\"compatible_references\"}");

    UBlueprint* LobbyUI = Blueprint(TEXT("UI"), TEXT("W_TrainingLobby"), UTrainingScreen::StaticClass(), Created);
    UBlueprint* SelectionUI = Blueprint(TEXT("UI"), TEXT("W_HeroSelection"), UTrainingScreen::StaticClass(), Created);
    UBlueprint* PauseUI = Blueprint(TEXT("UI"), TEXT("W_TrainingPause"), UTrainingScreen::StaticClass(), Created);
    auto* Front = Cast<UBlueprint>(Duplicate(FrontPath, TEXT("Experiences"), TEXT("B_TrainingLobby"), Created));
    if (!LobbyUI || !SelectionUI || !PauseUI || !Front) return TEXT("{\"state\":\"blocked\",\"reason\":\"frontend_creation\"}");
    CastChecked<UTrainingScreen>(SelectionUI->GeneratedClass->GetDefaultObject())->Screen = ETrainingScreen::Selection;
    CastChecked<UTrainingScreen>(PauseUI->GeneratedClass->GetDefaultObject())->Screen = ETrainingScreen::Pause;
    int32 Replaced = 0;
    for (UObject* Action : ObjectArray(Front->GeneratedClass->GetDefaultObject(), TEXT("Actions")))
        for (auto* Entry : ComponentEntries(Action))
        {
            UClass* Component = Entry->ComponentClass.LoadSynchronous();
            if (!Component || !Component->IsChildOf(FrontBase)) continue;
            auto* Main = FindFProperty<FSoftClassProperty>(Component, TEXT("MainScreenClass"));
            if (!Main || !Main->HasAnyPropertyFlags(CPF_Edit)) continue;
            CastChecked<UTrainingScreen>(LobbyUI->GeneratedClass->GetDefaultObject())->OriginalMainScreen =
                TSoftClassPtr<UCommonActivatableWidget>(Main->GetPropertyValue_InContainer(Component->GetDefaultObject()).ToSoftObjectPath());
            UBlueprint* OwnedFront = Blueprint(TEXT("UI"), TEXT("B_TrainingFrontendState"), Component, Created);
            if (!OwnedFront || !SetSoftClass(OwnedFront->GeneratedClass->GetDefaultObject(), TEXT("MainScreenClass"), LobbyUI->GeneratedClass))
                return TEXT("{\"state\":\"blocked\",\"reason\":\"frontend_configuration\"}");
            Entry->ComponentClass = OwnedFront->GeneratedClass;
            ++Replaced;
        }
    if (Replaced != 1 || !EnableFeature(Front->GeneratedClass->GetDefaultObject()))
        return TEXT("{\"state\":\"blocked\",\"reason\":\"frontend_identity\"}");

    UClass* ExperienceBase = LoadClass<UObject>(nullptr, TEXT("/Script/LyraGame.LyraExperienceDefinition"));
    UBlueprint* Match = Blueprint(TEXT("Experiences"), TEXT("B_HeroTraining"), ExperienceBase, Created);
    UBlueprint* MatchComponent = Blueprint(TEXT("System"), TEXT("B_TrainingMatch"), UTrainingMatchComponent::StaticClass(), Created);
    if (!Match || !MatchComponent) return TEXT("{\"state\":\"blocked\",\"reason\":\"match_creation\"}");
    auto* MenuAction = Data<UInputAction>(TEXT("Input"), TEXT("IA_TrainingMenu"), Created);
    auto* MenuMapping = Data<UInputMappingContext>(TEXT("Input"), TEXT("IMC_TrainingMenu"), Created);
    MenuAction->ValueType = EInputActionValueType::Boolean;
    MenuMapping->MapKey(MenuAction, EKeys::Escape);
    auto* MatchDefaults = CastChecked<UTrainingMatchComponent>(MatchComponent->GeneratedClass->GetDefaultObject());
    MatchDefaults->BotControllerClass = BotController;
    MatchDefaults->MenuAction = MenuAction;
    MatchDefaults->MenuMapping = MenuMapping;
    UObject* Experience = Match->GeneratedClass->GetDefaultObject();
    auto* Components = NewObject<UGameFeatureAction_AddComponents>(Experience);
    if (!AddComponent(Components, AGameStateBase::StaticClass(), MatchComponent->GeneratedClass))
        return TEXT("{\"state\":\"blocked\",\"reason\":\"match_component\"}");
    if (!ComponentEntries(Teams).IsEmpty()) SafeActions.Add(DuplicateObject(Teams, Experience));
    SafeActions.Add(Components);
    if (!SetObject(Experience, TEXT("DefaultPawnData"), PawnData) || !SetObjects(Experience, TEXT("Actions"), SafeActions) ||
        !SetObjects(Experience, TEXT("ActionSets"), Sets) || !EnableFeature(Experience))
        return TEXT("{\"state\":\"blocked\",\"reason\":\"match_configuration\"}");

    auto* LobbyMap = Cast<UWorld>(Duplicate(TEXT("/Game/System/FrontEnd/Maps/L_LyraFrontEnd.L_LyraFrontEnd"), TEXT("Maps"), TEXT("L_TrainingLobby"), Created));
    auto* TrainingMap = Cast<UWorld>(Duplicate(TEXT("/ShooterCore/Maps/L_ShooterGym.L_ShooterGym"), TEXT("Maps"), TEXT("L_HeroTraining"), Created));
    if (!LobbyMap || !TrainingMap || !SetSoftClass(LobbyMap->GetWorldSettings(), TEXT("DefaultGameplayExperience"), Front->GeneratedClass) ||
        !SetSoftClass(TrainingMap->GetWorldSettings(), TEXT("DefaultGameplayExperience"), Match->GeneratedClass))
        return TEXT("{\"state\":\"blocked\",\"reason\":\"map_configuration\"}");

    UClass* DefinitionType = LoadClass<UObject>(nullptr, TEXT("/Script/LyraGame.LyraUserFacingExperienceDefinition"));
    UPackage* DefinitionPackage = CreatePackage(TEXT("/NovanodeTraining/Experiences/DA_HeroTraining"));
    UObject* Definition = NewObject<UObject>(DefinitionPackage, DefinitionType, TEXT("DA_HeroTraining"), RF_Public | RF_Standalone);
    FAssetRegistryModule::AssetCreated(Definition);
    Created.Add(Definition);
    auto* MapID = FindFProperty<FStructProperty>(DefinitionType, TEXT("MapID"));
    auto* ExperienceID = FindFProperty<FStructProperty>(DefinitionType, TEXT("ExperienceID"));
    if (!MapID || !ExperienceID || MapID->Struct != FPrimaryAssetId::StaticStruct() || ExperienceID->Struct != FPrimaryAssetId::StaticStruct())
        return TEXT("{\"state\":\"blocked\",\"reason\":\"definition_schema\"}");
    *MapID->ContainerPtrToValuePtr<FPrimaryAssetId>(Definition) = FPrimaryAssetId(TEXT("Map"), TEXT("L_HeroTraining"));
    *ExperienceID->ContainerPtrToValuePtr<FPrimaryAssetId>(Definition) = FPrimaryAssetId(TEXT("LyraExperienceDefinition"), TEXT("B_HeroTraining"));

    auto* Feature = Data<UGameFeatureData>(TEXT(""), TEXT("NovanodeTraining"), Created);
    // GameFeatureData must be at the plugin root, not a nested or generic global scan.
    TArray<FPrimaryAssetTypeInfo>& Types = Feature->GetPrimaryAssetTypesToScan();
    const auto AddType = [&Types](const TCHAR* Name, UClass* Base, const TCHAR* Directory, bool Blueprints)
    {
        FPrimaryAssetTypeInfo Info;
        Info.PrimaryAssetType = FPrimaryAssetType(Name);
        Info.SetAssetBaseClass(TSoftClassPtr<UObject>(Base));
        Info.bHasBlueprintClasses = Blueprints;
        FDirectoryPath Path;
        Path.Path = Directory;
        Info.GetDirectories().Add(Path);
        Info.Rules.CookRule = EPrimaryAssetCookRule::AlwaysCook;
        Types.Add(Info);
    };
    AddType(TEXT("LyraExperienceDefinition"), ExperienceBase, TEXT("/NovanodeTraining/Experiences"), true);
    AddType(TEXT("LyraUserFacingExperienceDefinition"), DefinitionType, TEXT("/NovanodeTraining/Experiences"), false);
    AddType(TEXT("Map"), UWorld::StaticClass(), TEXT("/NovanodeTraining/Maps"), false);
    TArray<UPackage*> Packages;
    for (UObject* Asset : Created)
    {
        if (!Owned(Asset)) return TEXT("{\"state\":\"blocked\",\"reason\":\"write_boundary\"}");
        Asset->MarkPackageDirty();
        Packages.AddUnique(Asset->GetOutermost());
    }
    if (!UEditorLoadingAndSavingUtils::SavePackages(Packages, false))
        return TEXT("{\"state\":\"blocked\",\"reason\":\"save_packages\"}");
    return TEXT("{\"state\":\"prepared\",\"visual_verified\":false,\"gameplay_verified\":false}");
#else
    return TEXT("{\"state\":\"blocked\",\"reason\":\"editor_required\"}");
#endif
}

FString UTrainingReflectionAdapter::VerifyOwnedAssets()
{
#if WITH_EDITOR
    UClass* Front = LoadClass<UObject>(nullptr, TEXT("/NovanodeTraining/Experiences/B_TrainingLobby.B_TrainingLobby_C"));
    UClass* Match = LoadClass<UObject>(nullptr, TEXT("/NovanodeTraining/Experiences/B_HeroTraining.B_HeroTraining_C"));
    UObject* Definition = LoadObject<UObject>(nullptr, TEXT("/NovanodeTraining/Experiences/DA_HeroTraining.DA_HeroTraining"));
    UGameFeatureData* Feature = LoadObject<UGameFeatureData>(nullptr, TEXT("/NovanodeTraining/NovanodeTraining.NovanodeTraining"));
    if (!Front || !Match || !Feature || !HasHostingSignature(Definition))
        return TEXT("{\"state\":\"blocked\",\"reason\":\"required_assets\"}");
    return TEXT("{\"state\":\"assets_loaded\",\"gameplay_verified\":false,\"visual_verified\":false}");
#else
    return TEXT("{\"state\":\"blocked\",\"reason\":\"editor_required\"}");
#endif
}
