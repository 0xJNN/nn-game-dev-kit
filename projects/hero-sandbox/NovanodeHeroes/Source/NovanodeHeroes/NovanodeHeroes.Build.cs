using UnrealBuildTool;

public class NovanodeHeroes : ModuleRules
{
    public NovanodeHeroes(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "InputCore", "GameplayAbilities",
            "GameplayTags", "GameplayTasks", "NetCore", "Json", "GameFeatures",
            "LyraGame", "EnhancedInput", "UMG", "CommonUI", "CommonGame", "AIModule", "AssetRegistry"
        });
        PrivateDependencyModuleNames.AddRange(new[] { "Slate", "SlateCore" });
    }
}
