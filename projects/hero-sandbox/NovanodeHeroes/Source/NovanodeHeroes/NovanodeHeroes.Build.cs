using UnrealBuildTool;

public class NovanodeHeroes : ModuleRules
{
    public NovanodeHeroes(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "InputCore", "GameplayAbilities",
            "GameplayTags", "GameplayTasks", "NetCore", "Json", "GameFeatures"
        });
    }
}
