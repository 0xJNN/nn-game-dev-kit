#include "TrainingReflectionAdapter.h"

#include "CommonSessionSubsystem.h"
#include "Components/ActorComponent.h"
#include "GameFramework/Actor.h"
#include "Dom/JsonObject.h"
#include "GameFeatureAction_AddComponents.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/StructOnScope.h"
#include "UObject/UnrealType.h"

namespace
{
UClass* DefinitionClass()
{
    return LoadClass<UObject>(nullptr, TEXT("/Script/LyraGame.LyraUserFacingExperienceDefinition"));
}
}

bool UTrainingReflectionAdapter::HasComponentEntrySchema()
{
    const FArrayProperty* List = FindFProperty<FArrayProperty>(
        UGameFeatureAction_AddComponents::StaticClass(), TEXT("ComponentList"));
    const FStructProperty* Entry = List ? CastField<FStructProperty>(List->Inner) : nullptr;
    if (!Entry || Entry->Struct != FGameFeatureComponentEntry::StaticStruct() ||
        Entry->Struct->GetStructureSize() != sizeof(FGameFeatureComponentEntry)) return false;
    const auto* Actor = FindFProperty<FSoftClassProperty>(Entry->Struct, TEXT("ActorClass"));
    const auto* Component = FindFProperty<FSoftClassProperty>(Entry->Struct, TEXT("ComponentClass"));
    return Actor && Actor->MetaClass == AActor::StaticClass() && Component &&
        Component->MetaClass == UActorComponent::StaticClass() &&
        FindFProperty<FBoolProperty>(Entry->Struct, TEXT("bClientComponent")) &&
        FindFProperty<FBoolProperty>(Entry->Struct, TEXT("bServerComponent")) &&
        FindFProperty<FByteProperty>(Entry->Struct, TEXT("AdditionFlags"));
}

bool UTrainingReflectionAdapter::HasHostingSignature(UObject* Definition)
{
    UClass* Type = DefinitionClass();
    UFunction* Function = Definition && Type && Definition->IsA(Type) ?
        Definition->FindFunction(TEXT("CreateHostingRequest")) : nullptr;
    if (!Function || Function->NumParms != 2 || !Function->HasAnyFunctionFlags(FUNC_Const)) return false;
    int32 Inputs = 0, Returns = 0;
    for (TFieldIterator<FProperty> It(Function); It; ++It)
    {
        if (!It->HasAnyPropertyFlags(CPF_Parm)) continue;
        const auto* Object = CastField<FObjectProperty>(*It);
        if (!Object || Object->ArrayDim != 1) return false;
        if (Object->HasAnyPropertyFlags(CPF_ReturnParm))
        {
            if (Object->PropertyClass != UCommonSession_HostSessionRequest::StaticClass()) return false;
            ++Returns;
        }
        else
        {
            if (Object->GetFName() != TEXT("WorldContextObject") || Object->PropertyClass != UObject::StaticClass() ||
                Object->HasAnyPropertyFlags(CPF_OutParm | CPF_ReferenceParm)) return false;
            ++Inputs;
        }
    }
    return Inputs == 1 && Returns == 1;
}

UCommonSession_HostSessionRequest* UTrainingReflectionAdapter::CreateOfflineRequest(UObject* Definition, UObject* Context)
{
    if (!Context || !HasHostingSignature(Definition)) return nullptr;
    UFunction* Function = Definition->FindFunctionChecked(TEXT("CreateHostingRequest"));
    FStructOnScope Parameters(Function);
    auto* Input = FindFProperty<FObjectProperty>(Function, TEXT("WorldContextObject"));
    auto* Output = CastField<FObjectProperty>(Function->GetReturnProperty());
    Input->SetObjectPropertyValue_InContainer(Parameters.GetStructMemory(), Context);
    Definition->ProcessEvent(Function, Parameters.GetStructMemory());
    auto* Request = Cast<UCommonSession_HostSessionRequest>(
        Output->GetObjectPropertyValue_InContainer(Parameters.GetStructMemory()));
    if (!Request || !Request->MapID.IsValid()) return nullptr;
    Request->OnlineMode = ECommonSessionOnlineMode::Offline;
    Request->bUseLobbies = false;
    Request->MaxPlayerCount = 1;
    return Request;
}

bool UTrainingReflectionAdapter::AddComponent(UGameFeatureAction_AddComponents* Action, UClass* Actor,
    UClass* Component, bool Client, bool Server)
{
    if (!Action || !HasComponentEntrySchema() || !Actor || Actor == AActor::StaticClass() ||
        !Actor->IsChildOf(AActor::StaticClass()) || !Component ||
        !Component->IsChildOf(UActorComponent::StaticClass())) return false;
    const auto* List = FindFProperty<FArrayProperty>(Action->GetClass(), TEXT("ComponentList"));
    FScriptArrayHelper Entries(List, List->ContainerPtrToValuePtr<void>(Action));
    FGameFeatureComponentEntry Entry;
    Entry.ActorClass = Actor;
    Entry.ComponentClass = Component;
    Entry.bClientComponent = Client;
    Entry.bServerComponent = Server;
    *reinterpret_cast<FGameFeatureComponentEntry*>(Entries.GetRawPtr(Entries.AddValue())) = Entry;
    return true;
}

FString UTrainingReflectionAdapter::InspectInstalledSchema()
{
    const bool Components = HasComponentEntrySchema();
    UClass* Type = DefinitionClass();
    const bool Hosting = Type && HasHostingSignature(Type->GetDefaultObject());
    UClass* Frontend = LoadClass<UActorComponent>(nullptr, TEXT("/Script/LyraGame.LyraFrontendStateComponent"));
    auto* MainScreen = Frontend ? FindFProperty<FSoftClassProperty>(Frontend, TEXT("MainScreenClass")) : nullptr;
    const bool Editable = MainScreen && MainScreen->HasAnyPropertyFlags(CPF_Edit);
    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("component_entry_schema"), Components);
    Result->SetBoolField(TEXT("hosting_signature"), Hosting);
    Result->SetBoolField(TEXT("editable_frontend_main_screen"), Editable);
    Result->SetStringField(TEXT("state"), Components && Hosting && Editable ? TEXT("schema_verified") : TEXT("blocked"));
    Result->SetBoolField(TEXT("gameplay_verified"), false);
    FString Json;
    FJsonSerializer::Serialize(Result, TJsonWriterFactory<>::Create(&Json));
    return Json;
}
