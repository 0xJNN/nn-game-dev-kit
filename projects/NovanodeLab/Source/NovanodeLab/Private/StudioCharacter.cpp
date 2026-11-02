#include "StudioCharacter.h"
#include "StudioGameMode.h"
#include "Camera/CameraComponent.h"
#include "CollisionQueryParams.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"

AStudioCharacter::AStudioCharacter()
{
    GetCapsuleComponent()->InitCapsuleSize(30.f, 88.f);
    GetCharacterMovement()->MaxWalkSpeed = 280.f;
    bUseControllerRotationYaw = true;
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("View"));
    Camera->SetupAttachment(GetCapsuleComponent());
    Camera->SetRelativeLocation(FVector(0, 0, 66));
    Camera->bUsePawnControlRotation = true;
    Camera->FieldOfView = 85.f;
}

void AStudioCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->BindAxis(TEXT("MoveForward"), this, &AStudioCharacter::MoveForward);
    Input->BindAxis(TEXT("MoveRight"), this, &AStudioCharacter::MoveRight);
    Input->BindAxis(TEXT("Turn"), this, &APawn::AddControllerYawInput);
    Input->BindAxis(TEXT("LookUp"), this, &APawn::AddControllerPitchInput);
    Input->BindAction(TEXT("Interact"), IE_Pressed, this, &AStudioCharacter::Interact);
    Input->BindAction(TEXT("ReleaseMouse"), IE_Pressed, this, &AStudioCharacter::ReleaseMouse);
}

void AStudioCharacter::MoveForward(float Value) { AddMovementInput(GetActorForwardVector(), Value); }
void AStudioCharacter::MoveRight(float Value) { AddMovementInput(GetActorRightVector(), Value); }

AActor* AStudioCharacter::TraceInteraction() const
{
    FHitResult Hit;
    FCollisionQueryParams Params;
    Params.AddIgnoredActor(this);
    const FVector Start = Camera->GetComponentLocation();
    GetWorld()->LineTraceSingleByChannel(Hit, Start, Start + Camera->GetForwardVector() * 350.f,
        ECC_Visibility, Params);
    return Hit.GetActor();
}

void AStudioCharacter::Interact()
{
    if (auto* Lab = GetWorld()->GetAuthGameMode<AStudioGameMode>())
    {
        Lab->InteractWith(TraceInteraction());
    }
}

void AStudioCharacter::ReleaseMouse()
{
    if (auto* PC = Cast<APlayerController>(GetController()))
    {
        PC->bShowMouseCursor = !PC->bShowMouseCursor;
        PC->SetIgnoreLookInput(PC->bShowMouseCursor);
    }
}
