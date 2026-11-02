#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "LabState.h"
#include "StudioGameMode.generated.h"

class AStaticMeshActor;
class UMaterialInterface;
class UMaterialInstanceDynamic;

UCLASS()
class NOVANODELAB_API AStudioGameMode : public AGameModeBase
{
    GENERATED_BODY()

public:
    AStudioGameMode();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void RestartPlayer(AController* Player) override;
    void InteractWith(AActor* Actor);
    FString InteractionPrompt(AActor* Actor) const;
    const FLabState& GetLabState() const { return State; }
    FString Notice = TEXT("Explore the lab. Look at a console and press E.");

private:
    FLabState State;
    UPROPERTY() TObjectPtr<UMaterialInterface> Surface;
    UPROPERTY() TObjectPtr<AStaticMeshActor> Door;
    UPROPERTY() TObjectPtr<AStaticMeshActor> PowerIndicator;
    UPROPERTY() TObjectPtr<AStaticMeshActor> ReferenceBob;
    UPROPERTY() TObjectPtr<AStaticMeshActor> ReferenceConsole;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;
    TMap<FString, UMaterialInstanceDynamic*> MaterialCache;
    float Elapsed = 0.f;
    AStaticMeshActor* Box(const FVector& Position, const FVector& Size, const FLinearColor& Color,
        float Emission = 0.f, bool Collision = true);
    UMaterialInstanceDynamic* Material(const FLinearColor& Color, float Emission);
    void Sign(const FString& Text, const FVector& Position, float Size, const FRotator& Rotation);
    void BuildRoom();
    void WriteSmokeReport();
};
