using UnrealBuildTool;

public class NovanodeTraining : ModuleRules
{
    public NovanodeTraining(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "GameFeatures", "ModularGameplay", "LyraGame",
            "CommonUI", "CommonGame", "CommonUser", "GameplayTags", "GameplayAbilities",
            "UMG", "EnhancedInput", "InputCore", "AIModule"
        });
        PrivateDependencyModuleNames.AddRange(new[] { "Slate", "SlateCore", "Json", "AssetRegistry", "Projects" });
        if (Target.bBuildEditor)
        {
            PrivateDependencyModuleNames.AddRange(new[] { "UnrealEd", "AssetTools", "KismetCompiler" });
        }
    }
}
