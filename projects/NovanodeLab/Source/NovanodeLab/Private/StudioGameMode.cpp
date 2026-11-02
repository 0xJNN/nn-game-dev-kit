#include "StudioGameMode.h"
#include "StudioCharacter.h"
#include "StudioHUD.h"
#include "CollisionQueryParams.h"
#include "Components/RectLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/RectLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HAL/PlatformMisc.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "TimerManager.h"

namespace Palette
{
    const FLinearColor Shell(0.035f, 0.055f, 0.085f);
    const FLinearColor Panel(0.10f, 0.15f, 0.20f);
    const FLinearColor Teal(0.07f, 0.72f, 0.65f);
    const FLinearColor Amber(1.0f, 0.38f, 0.08f);
    const FLinearColor White(0.65f, 0.82f, 0.95f);
}

AStudioGameMode::AStudioGameMode()
{
    PrimaryActorTick.bCanEverTick = true;
    DefaultPawnClass = AStudioCharacter::StaticClass();
    HUDClass = AStudioHUD::StaticClass();
}

void AStudioGameMode::RestartPlayer(AController* Player)
{
    RestartPlayerAtTransform(Player, FTransform(FRotator::ZeroRotator, FVector(-550, 0, 100)));
}

UMaterialInstanceDynamic* AStudioGameMode::Material(const FLinearColor& Color, float Emission)
{
    const FString Key = FString::Printf(TEXT("%.3f/%.3f/%.3f/%.3f"), Color.R, Color.G, Color.B, Emission);
    if (auto* Found = MaterialCache.Find(Key)) { return *Found; }
    auto* Instance = UMaterialInstanceDynamic::Create(Surface, this);
    Instance->SetVectorParameterValue(TEXT("BaseColor"), Color);
    Instance->SetVectorParameterValue(TEXT("Emissive"), Color * Emission);
    Instance->SetScalarParameterValue(TEXT("Roughness"), Emission > 0.f ? 0.35f : 0.65f);
    Instance->SetScalarParameterValue(TEXT("Metallic"), 0.25f);
    Materials.Add(Instance);
    MaterialCache.Add(Key, Instance);
    return Instance;
}

AStaticMeshActor* AStudioGameMode::Box(const FVector& Position, const FVector& Size,
    const FLinearColor& Color, float Emission, bool Collision)
{
    auto* Actor = GetWorld()->SpawnActor<AStaticMeshActor>(Position, FRotator::ZeroRotator);
    auto* Mesh = Actor->GetStaticMeshComponent();
    Mesh->SetMobility(EComponentMobility::Movable);
    Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
    Mesh->SetWorldScale3D(Size / 100.f); // Engine primitives and coordinates use centimeters.
    if (Surface) { Mesh->SetMaterial(0, Material(Color, Emission)); }
    Mesh->SetCollisionProfileName(Collision ? TEXT("BlockAll") : TEXT("NoCollision"));
    Actor->SetActorEnableCollision(Collision);
    return Actor;
}

void AStudioGameMode::Sign(const FString& Text, const FVector& Position, float Size,
    const FRotator& Rotation)
{
    auto* Actor = GetWorld()->SpawnActor<AActor>();
    auto* Label = NewObject<UTextRenderComponent>(Actor);
    Actor->SetRootComponent(Label);
    Actor->AddInstanceComponent(Label);
    Label->RegisterComponent();
    Label->SetWorldLocation(Position);
    Label->SetWorldRotation(Rotation);
    Label->SetText(FText::FromString(Text));
    Label->SetWorldSize(Size);
    Label->SetHorizontalAlignment(EHorizTextAligment::EHTA_Center);
    Label->SetTextRenderColor(Palette::Teal.ToFColor(true));
    Label->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void AStudioGameMode::BuildRoom()
{
    // Authored modular layout: airlock, perimeter equipment bays, and reference instrument island.
    Box(FVector(0, 0, -15), FVector(1440, 1240, 30), Palette::Shell);
    for (int X = -600; X <= 600; X += 200)
    {
        for (int Y = -500; Y <= 500; Y += 200)
        {
            Box(FVector(X, Y, 1), FVector(197, 197, 3), Palette::Panel);
        }
    }
    for (int Side : {-1, 1})
    {
        Box(FVector(0, Side * 610, 185), FVector(1440, 20, 370), Palette::Shell);
        Box(FVector(Side * 710, 0, 185), FVector(20, 1240, 370), Palette::Shell);
        Box(FVector(0, Side * 594, 25), FVector(1380, 4, 3), Palette::Teal, 3.f, false);
        Box(FVector(0, Side * 590, 320), FVector(1360, 8, 12), Palette::White, 2.f, false);
        for (int X = -600; X <= 600; X += 200)
        {
            Box(FVector(X, Side * 592, 180), FVector(12, 25, 340), Palette::Panel);
        }
    }
    Box(FVector(0, 0, 380), FVector(1440, 1240, 20), Palette::Shell);
    // Segmented airlock partition; the central opening remains a real traversable collision gate.
    for (int Side : {-1, 1})
    {
        Box(FVector(-300, Side * 365, 165), FVector(28, 470, 330), Palette::Panel);
        Box(FVector(-320, Side * 140, 140), FVector(34, 14, 280), Palette::Teal, 1.f);
    }
    Box(FVector(-300, 0, 300), FVector(30, 280, 45), Palette::Panel);
    Door = Box(FVector(-300, 0, 140), FVector(16, 250, 280), Palette::Shell);
    Door->Tags.Add(TEXT("Door"));
    Sign(TEXT("N O V A N O D E\nRESEARCH / 01"), FVector(-322, 0, 235), 16, FRotator(0, 180, 0));
    Sign(TEXT("NOVANODE / APPLIED SYSTEMS"), FVector(695, 0, 290), 30, FRotator(0, 180, 0));

    // Main benches have separate legs, fascia, instrument shelves, and cable/service channels.
    for (int Side : {-1, 1})
    {
        for (int X = -50; X <= 550; X += 300)
        {
            const float Y = Side * 450.f;
            Box(FVector(X, Y, 91), FVector(250, 110, 8), Palette::Panel);
            Box(FVector(X, Y + Side * 42, 75), FVector(240, 10, 6), Palette::Teal, 2.f, false);
            for (int Leg : {-1, 1})
            {
                Box(FVector(X + Leg * 100, Y, 44), FVector(14, 85, 88), Palette::Shell);
            }
            Box(FVector(X, Y + Side * 25, 145), FVector(145, 16, 85), Palette::Shell);
            for (int Row = 0; Row < 5; ++Row)
            {
                Box(FVector(X - 50 + Row * 25, Y - Side * 4, 143), FVector(14, 3, 42),
                    Row % 2 ? Palette::Teal : Palette::White, 1.f, false);
            }
        }
    }
    PowerIndicator = Box(FVector(-80, -280, 110), FVector(100, 55, 90), Palette::Panel);
    PowerIndicator->Tags.Add(TEXT("Power"));
    Box(FVector(-133, -280, 115), FVector(3, 42, 46), Palette::Amber, 2.f, false);
    Sign(TEXT("01 / POWER"), FVector(-137, -280, 180), 13, FRotator(0, 180, 0));

    Box(FVector(300, 170, 35), FVector(260, 220, 70), Palette::Shell);
    Box(FVector(300, 170, 73), FVector(264, 224, 6), Palette::Panel);
    Box(FVector(300, 170, 78), FVector(220, 180, 2), Palette::Teal, 1.f, false);
    for (int Y : {80, 260})
    {
        Box(FVector(300, Y, 170), FVector(14, 14, 190), Palette::Panel);
    }
    Box(FVector(300, 170, 262), FVector(14, 200, 12), Palette::Panel);
    Box(FVector(300, 170, 210), FVector(3, 3, 100), Palette::White, 0.f, false);
    ReferenceBob = Box(FVector(300, 170, 160), FVector(22, 22, 22), Palette::Amber, 0.5f, false);
    ReferenceConsole = Box(FVector(145, 170, 105), FVector(45, 100, 60), Palette::Panel);
    ReferenceConsole->Tags.Add(TEXT("Reference"));
    Sign(TEXT("02 / REFERENCE\nL=1m / g=9.81"), FVector(118, 170, 165), 12, FRotator(0, 180, 0));

    for (int X : {-450, 100, 550})
    {
        for (int Y : {-250, 250})
        {
            Box(FVector(X, Y, 365), FVector(220, 50, 5), Palette::White, 3.f, false);
            auto* Light = GetWorld()->SpawnActor<ARectLight>(FVector(X, Y, 350), FRotator(-90, 0, 0));
            auto* Component = Light->GetRectLightComponent();
            Component->SetMobility(EComponentMobility::Movable);
            Component->SetIntensity(2200.f);
            Component->SetSourceWidth(200.f);
            Component->SetSourceHeight(45.f);
            Component->SetLightColor(Palette::White);
            Component->SetAttenuationRadius(900.f);
        }
    }
}

void AStudioGameMode::BeginPlay()
{
    Super::BeginPlay();
    Surface = LoadObject<UMaterialInterface>(nullptr,
        TEXT("/Game/Generated/Materials/M_StudioSurface.M_StudioSurface"));
    BuildRoom();
    FString Report;
    if (FParse::Value(FCommandLine::Get(), TEXT("NovanodeSmokeReport="), Report))
    {
        FTimerHandle Handle;
        GetWorldTimerManager().SetTimer(Handle, this, &AStudioGameMode::WriteSmokeReport, 0.5f, false);
    }
}

void AStudioGameMode::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    Elapsed += DeltaSeconds;
    if (Door)
    {
        const FVector Target(-300, State.DoorOpen ? 260.f : 0.f, 140);
        Door->SetActorLocation(FMath::VInterpTo(Door->GetActorLocation(), Target, DeltaSeconds, 4.f));
    }
    if (ReferenceBob && State.ExperimentComplete && State.PowerOn)
    {
        const float Offset = FMath::Sin(Elapsed * 2.f * PI / State.PeriodSeconds) * 14.f;
        ReferenceBob->SetActorLocation(FVector(300, 170 + Offset, 160));
    }
}

FString AStudioGameMode::InteractionPrompt(AActor* Actor) const
{
    if (!Actor) { return TEXT(""); }
    if (Actor->ActorHasTag(TEXT("Door"))) { return TEXT("E / OPEN AIRLOCK"); }
    if (Actor->ActorHasTag(TEXT("Power"))) { return TEXT("E / TOGGLE LAB POWER"); }
    if (Actor->ActorHasTag(TEXT("Reference"))) { return TEXT("E / RUN ANALYTICAL REFERENCE"); }
    return TEXT("");
}

void AStudioGameMode::InteractWith(AActor* Actor)
{
    if (!Actor) { return; }
    if (Actor->ActorHasTag(TEXT("Door")))
    {
        State.ToggleDoor();
        Door->SetActorEnableCollision(!State.DoorOpen);
        Notice = State.DoorOpen ? TEXT("Airlock open. Locate the power console.") : TEXT("Airlock closed.");
    }
    else if (Actor->ActorHasTag(TEXT("Power")))
    {
        State.TogglePower();
        if (Surface)
        {
            PowerIndicator->GetStaticMeshComponent()->SetMaterial(0,
                Material(State.PowerOn ? Palette::Teal : Palette::Panel, State.PowerOn ? 0.6f : 0.f));
        }
        Notice = State.PowerOn ? TEXT("Power online. Reference instrument ready.") : TEXT("Power offline.");
    }
    else if (Actor->ActorHasTag(TEXT("Reference")))
    {
        Notice = State.RunReference()
            ? FString::Printf(TEXT("Reference complete: T = %.4f seconds."), State.PeriodSeconds)
            : TEXT("Open the airlock and enable lab power first.");
    }
}

void AStudioGameMode::WriteSmokeReport()
{
    TArray<TSharedPtr<FJsonValue>> Checks;
    const auto Check = [&Checks](const FString& Name, bool Passed)
    {
        auto Item = MakeShared<FJsonObject>();
        Item->SetStringField(TEXT("name"), Name);
        Item->SetBoolField(TEXT("passed"), Passed);
        Checks.Add(MakeShared<FJsonValueObject>(Item));
    };
    Check(TEXT("authored material loaded"), Surface != nullptr);
    Check(TEXT("reference rejects missing prerequisites"), !State.RunReference());
    FHitResult Hit;
    const FVector Start(-400, 0, 120), End(-200, 0, 120);
    GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility);
    Check(TEXT("closed door blocks world-space ray"), Hit.GetActor() == Door);
    InteractWith(Door);
    FHitResult OpenHit;
    GetWorld()->LineTraceSingleByChannel(OpenHit, Start, End, ECC_Visibility);
    Check(TEXT("open door clears collision ray"), !OpenHit.bBlockingHit);
    InteractWith(PowerIndicator);
    InteractWith(ReferenceConsole);
    Check(TEXT("reference completes with correct period"), State.ExperimentComplete &&
        FMath::Abs(State.PeriodSeconds - 2.00606668) < 0.00001);
    bool Passed = true;
    for (const auto& Item : Checks) { Passed &= Item->AsObject()->GetBoolField(TEXT("passed")); }
    auto Report = MakeShared<FJsonObject>();
    Report->SetStringField(TEXT("status"), Passed ? TEXT("passed") : TEXT("failed"));
    Report->SetStringField(TEXT("human_approval"), TEXT("pending"));
    Report->SetStringField(TEXT("scope"), TEXT("runtime outcomes; not physical keyboard or visual acceptance"));
    Report->SetArrayField(TEXT("checks"), Checks);
    FString Output, Path;
    FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&Output));
    FParse::Value(FCommandLine::Get(), TEXT("NovanodeSmokeReport="), Path);
    if (!FFileHelper::SaveStringToFile(Output, *Path)) { UE_LOG(LogTemp, Error, TEXT("Cannot write smoke evidence")); }
    FPlatformMisc::RequestExit(false);
}
