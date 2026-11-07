#include "TrainingLobby.h"
#include "TrainingReflectionAdapter.h"

#include "CommonButtonBase.h"
#include "CommonUIExtensions.h"
#include "Dom/JsonObject.h"
#include "Engine/AssetManager.h"
#include "Engine/GameInstance.h"
#include "GameFramework/PlayerController.h"
#include "Serialization/JsonSerializer.h"
#include "TimerManager.h"
#include "UObject/StructOnScope.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UObjectIterator.h"
#include "UObject/UnrealType.h"

namespace
{
constexpr const TCHAR* DefinitionPath = TEXT("/NovanodeTraining/Experiences/DA_HeroTraining.DA_HeroTraining");
constexpr const TCHAR* FrontWidgetPath = TEXT("/Game/UI/Menu/W_LyraFrontEnd.W_LyraFrontEnd_C");
constexpr const TCHAR* SelectionWidgetPath = TEXT("/Game/UI/Menu/Experiences/W_ExperienceSelectionScreen.W_ExperienceSelectionScreen_C");
constexpr const TCHAR* HostWidgetPath = TEXT("/Game/UI/Menu/Experiences/W_HostSessionScreen.W_HostSessionScreen_C");
const TCHAR* CallbackNames[] = {
    TEXT("BndEvt__BW_LyraFrontEnd_StartGameButton_K2Node_ComponentBoundEvent_0_CommonButtonBaseClicked__DelegateSignature"),
    TEXT("BndEvt__W_ExperienceSelectionScreen_W_ExperienceList_K2Node_ComponentBoundEvent_0_OnExperienceSelected__DelegateSignature"),
    TEXT("BndEvt__W_ExperienceSelectionScreen_HostButton_K2Node_ComponentBoundEvent_2_CommonButtonBaseClicked__DelegateSignature"),
    TEXT("BndEvt__W_HostSessionScreen_W_ExperienceList_K2Node_ComponentBoundEvent_0_OnExperienceSelected__DelegateSignature")
};

bool NativeOfflineMode(UClass* Class, UObject* Instance = nullptr)
{
    FProperty* Property = Class ? FindFProperty<FProperty>(Class, TEXT("OnlineMode")) : nullptr;
    auto* EnumProperty = CastField<FEnumProperty>(Property);
    auto* ByteProperty = CastField<FByteProperty>(Property);
    UEnum* Enum = EnumProperty ? EnumProperty->GetEnum() : ByteProperty ? ByteProperty->Enum.Get() : nullptr;
    if (!Enum || Enum->GetName() != TEXT("ECommonSessionOnlineMode")) return false;
    const int64 Offline = Enum->GetValueByNameString(TEXT("Offline"));
    if (Offline == INDEX_NONE) return false;
    if (Instance)
    {
        void* Address = Property->ContainerPtrToValuePtr<void>(Instance);
        if (EnumProperty) EnumProperty->GetUnderlyingProperty()->SetIntPropertyValue(Address, Offline);
        else ByteProperty->SetPropertyValue(Address, static_cast<uint8>(Offline));
    }
    return true;
}

FObjectPropertyBase* ObjectParameter(UFunction* Function)
{
    FObjectPropertyBase* Result = nullptr;
    if (!Function) return nullptr;
    for (TFieldIterator<FProperty> It(Function); It; ++It)
        if (It->HasAnyPropertyFlags(CPF_Parm))
        {
            if (Result || It->HasAnyPropertyFlags(CPF_ReturnParm | CPF_OutParm)) return nullptr;
            Result = CastField<FObjectPropertyBase>(*It);
            if (!Result) return nullptr;
        }
    return Result;
}

UCommonActivatableWidget* ActiveNativeWidget(UWorld* World, UClass* Class)
{
    for (TObjectIterator<UCommonActivatableWidget> It; It; ++It)
        if (It->GetWorld() == World && It->GetClass() == Class && It->IsActivated()) return *It;
    return nullptr;
}
}

UObject* UTrainingReflectionAdapter::ConfigureNativeFrontendDefinition()
{
    UObject* Definition = LoadObject<UObject>(nullptr, DefinitionPath);
    if (!Definition) return nullptr;
    UClass* Class = Definition->GetClass();
    auto* Title = FindFProperty<FTextProperty>(Class, TEXT("TileTitle"));
    auto* Subtitle = FindFProperty<FTextProperty>(Class, TEXT("TileSubTitle"));
    auto* Description = FindFProperty<FTextProperty>(Class, TEXT("TileDescription"));
    auto* Players = FindFProperty<FIntProperty>(Class, TEXT("MaxPlayerCount"));
    auto* Show = FindFProperty<FBoolProperty>(Class, TEXT("bShowInFrontEnd"));
    if (!Title || !Subtitle || !Description || !Players || !Show || !HasHostingSignature(Definition)) return nullptr;
    // Owned asset instance only. Never MarkPackageDirty/SavePackage or change native frontend assets.
    Title->SetPropertyValue_InContainer(Definition, FText::FromString(TEXT("Hero Training")));
    Subtitle->SetPropertyValue_InContainer(Definition, FText::FromString(TEXT("Local practice / 3 rivals")));
    Description->SetPropertyValue_InContainer(Definition,
        FText::FromString(TEXT("Choose Melee or Mage after loading. Hero combat/items are still pending integration.")));
    Players->SetPropertyValue_InContainer(Definition, 1);
    Show->SetPropertyValue_InContainer(Definition, true);
    return Definition;
}

bool UTrainingReflectionAdapter::SetNativeButtonLabel(UCommonButtonBase* Button, const FText& Label)
{
    if (!Button || Button->GetClass()->GetPathName() != TEXT("/Game/UI/Menu/W_LyraMenuButton.W_LyraMenuButton_C")) return false;
    UFunction* Function = Button->FindFunction(TEXT("SetButtonText"));
    auto* Text = Function ? FindFProperty<FTextProperty>(Function, TEXT("InText")) : nullptr;
    int32 Count = 0;
    if (Function) for (TFieldIterator<FProperty> It(Function); It; ++It) if (It->HasAnyPropertyFlags(CPF_Parm)) ++Count;
    if (!Text || Count != 1 || Text->HasAnyPropertyFlags(CPF_ReturnParm) ||
        (Text->HasAnyPropertyFlags(CPF_OutParm) && !Text->HasAnyPropertyFlags(CPF_ConstParm))) return false;
    FStructOnScope Params(Function);
    Text->SetPropertyValue_InContainer(Params.GetStructMemory(), Label);
    Button->ProcessEvent(Function, Params.GetStructMemory());
    return true;
}

bool UTrainingReflectionAdapter::InvokeNativeFrontendCallback(UObject* Widget, int32 Callback, UObject* Argument)
{
    if (!Widget || Callback < 0 || Callback > 3 || !Argument) return false;
    const TCHAR* ExpectedClass = Callback == 0 ? FrontWidgetPath : Callback == 3 ? HostWidgetPath : SelectionWidgetPath;
    if (Widget->GetClass()->GetPathName() != ExpectedClass) return false;
    UFunction* Function = Widget->FindFunction(CallbackNames[Callback]);
    FObjectPropertyBase* Parameter = ObjectParameter(Function);
    if (!Parameter || !Argument->IsA(Parameter->PropertyClass)) return false;
    // Probe-only equivalent of choosing Offline on the ORIGINAL host screen.
    if (Callback == 3 && !NativeOfflineMode(Widget->GetClass(), Widget)) return false;
    FStructOnScope Params(Function);
    Parameter->SetObjectPropertyValue_InContainer(Params.GetStructMemory(), Argument);
    Widget->ProcessEvent(Function, Params.GetStructMemory());
    return true;
}

FString UTrainingReflectionAdapter::InspectNativeFrontend()
{
    TStrongObjectPtr<UObject> Definition(ConfigureNativeFrontendDefinition());
    UClass* Front = LoadClass<UCommonActivatableWidget>(nullptr, FrontWidgetPath);
    UClass* Selection = LoadClass<UCommonActivatableWidget>(nullptr, SelectionWidgetPath);
    UClass* Host = LoadClass<UCommonActivatableWidget>(nullptr, HostWidgetPath);
    UClass* Button = LoadClass<UCommonButtonBase>(nullptr, TEXT("/Game/UI/Menu/W_LyraMenuButton.W_LyraMenuButton_C"));
    UFunction* LabelFunction = Button ? Button->FindFunctionByName(TEXT("SetButtonText")) : nullptr;
    const bool ButtonSchema = LabelFunction && FindFProperty<FTextProperty>(LabelFunction, TEXT("InText"));
    TArray<FPrimaryAssetId> Definitions;
    UAssetManager::Get().GetPrimaryAssetIdList(FPrimaryAssetType(TEXT("LyraUserFacingExperienceDefinition")), Definitions);
    const bool Registered = Definitions.Contains(FPrimaryAssetId(TEXT("LyraUserFacingExperienceDefinition"), TEXT("DA_HeroTraining")));
    bool Callbacks = Front && Selection && Host && NativeOfflineMode(Host);
    TArray<TSharedPtr<FJsonValue>> Schemas;
    for (int32 Index = 0; Index < 4; ++Index)
    {
        UClass* Class = Index == 0 ? Front : Index == 3 ? Host : Selection;
        FObjectPropertyBase* Parameter = ObjectParameter(Class ? Class->FindFunctionByName(CallbackNames[Index]) : nullptr);
        Callbacks &= Parameter != nullptr;
        Schemas.Add(MakeShared<FJsonValueString>(Parameter ? Parameter->PropertyClass->GetPathName() : TEXT("missing")));
    }
    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("state"), Definition.IsValid() && Registered && Callbacks && ButtonSchema ?
        TEXT("native_frontend_schema_verified") : TEXT("blocked"));
    Result->SetBoolField(TEXT("definition_registered"), Registered);
    Result->SetBoolField(TEXT("definition_configured_in_memory"), Definition.IsValid());
    Result->SetBoolField(TEXT("native_button_loaded"), Button != nullptr);
    Result->SetBoolField(TEXT("native_button_text_schema"), ButtonSchema);
    Result->SetBoolField(TEXT("native_host_offline_schema"), Host && NativeOfflineMode(Host));
    Result->SetArrayField(TEXT("callback_parameter_classes"), Schemas);
    Result->SetBoolField(TEXT("assets_saved"), false);
    Result->SetBoolField(TEXT("visual_verified"), false);
    FString Json;
    FJsonSerializer::Serialize(Result, TJsonWriterFactory<>::Create(&Json));
    return Json;
}

void UTrainingLobbySubsystem::NativeMatchStarted()
{
    if (!bNativeFrontend) return;
    if (!Flow.BeginNativeMatch())
    {
        UE_LOG(LogTemp, Error, TEXT("NovanodeTraining rejected duplicate native match lifecycle"));
        return;
    }
    bNativeProbeLobbyVisited = false;
    bNativeProbeSelected = false;
    bNativeProbeHosted = false;
    bNativeProbeConfirmed = false;
}

void UTrainingLobbySubsystem::ReleaseNativeSelectionPause()
{
    if (NativePausedWorld.IsValid() && NativePausedWorld.Get() == GetWorld())
        if (auto* Player = GetGameInstance()->GetFirstLocalPlayerController()) Player->SetPause(false);
    NativePausedWorld.Reset();
}

void UTrainingLobbySubsystem::NativeProbeStep()
{
    if (!bNativeFrontend || ProbePath.IsEmpty() || !GetWorld() ||
        (Flow.State != NovanodeTraining::Screen::Inactive && Flow.State != NovanodeTraining::Screen::Returning)) return;
    UClass* FrontClass = LoadClass<UCommonActivatableWidget>(nullptr, FrontWidgetPath);
    if (auto* Front = ActiveNativeWidget(GetWorld(), FrontClass))
    {
        if (!bNativeProbeLobbyVisited)
        {
            bNativeProbeLobbyVisited = true;
            ++ProbeEvidence.LobbyArrivals;
            if (ProbeMatches == 2) { WriteProbe(ProbeEvidence.Complete(), TEXT("original_lyra_two_matches_and_cleanup_verified")); return; }
            ++NativeMenuCallbacks;
            if (!UTrainingReflectionAdapter::InvokeNativeFrontendCallback(Front, 0, Front->GetWidgetFromName(TEXT("StartGameButton"))))
                WriteProbe(false, TEXT("native_play_callback_schema"));
        }
    }
    UClass* SelectionClass = LoadClass<UCommonActivatableWidget>(nullptr, SelectionWidgetPath);
    if (auto* Selection = ActiveNativeWidget(GetWorld(), SelectionClass))
    {
        if (!bNativeProbeSelected)
        {
            bNativeProbeSelected = true;
            ++NativeExperienceCallbacks;
            if (!UTrainingReflectionAdapter::InvokeNativeFrontendCallback(Selection, 1, NativeDefinition))
                WriteProbe(false, TEXT("native_experience_callback_schema"));
            return;
        }
        if (!bNativeProbeHosted)
        {
            bNativeProbeHosted = true;
            ++NativeHostCallbacks;
            if (!UTrainingReflectionAdapter::InvokeNativeFrontendCallback(Selection, 2, Selection->GetWidgetFromName(TEXT("HostButton"))))
                WriteProbe(false, TEXT("native_host_callback_schema"));
        }
    }
    UClass* HostClass = LoadClass<UCommonActivatableWidget>(nullptr, HostWidgetPath);
    if (!bNativeProbeConfirmed)
        if (auto* Host = ActiveNativeWidget(GetWorld(), HostClass))
        {
            bNativeProbeConfirmed = true;
            ++NativeOfflineHostCallbacks;
            if (!UTrainingReflectionAdapter::InvokeNativeFrontendCallback(Host, 3, NativeDefinition))
                WriteProbe(false, TEXT("native_offline_host_confirmation_schema"));
        }
}
