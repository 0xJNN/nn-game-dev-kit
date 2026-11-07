#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "TrainingReflectionAdapter.generated.h"

class UCommonSession_HostSessionRequest;
class UGameFeatureAction_AddComponents;

// Deliberately narrow: no arbitrary field writes, function dispatch or package saves.
UCLASS()
class NOVANODETRAINING_API UTrainingReflectionAdapter : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static FString InspectInstalledSchema();

    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static FString PrepareOwnedAssets();

    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static FString VerifyOwnedAssets();

    UFUNCTION(BlueprintCallable, Category="Novanode|Training")
    static FString RepairOwnedMapId();

    static bool HasComponentEntrySchema();
    static bool HasHostingSignature(UObject* Definition);
    static UCommonSession_HostSessionRequest* CreateOfflineRequest(UObject* Definition, UObject* Context);
    static bool AddComponent(UGameFeatureAction_AddComponents* Action, UClass* Actor, UClass* Component,
        bool Client = true, bool Server = true);
};
