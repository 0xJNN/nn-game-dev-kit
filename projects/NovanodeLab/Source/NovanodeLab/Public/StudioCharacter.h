#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "StudioCharacter.generated.h"

class UCameraComponent;

UCLASS()
class NOVANODELAB_API AStudioCharacter : public ACharacter
{
    GENERATED_BODY()

public:
    AStudioCharacter();
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    AActor* TraceInteraction() const;

private:
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UCameraComponent> Camera;
    void MoveForward(float Value);
    void MoveRight(float Value);
    void Interact();
    void ReleaseMouse();
};
