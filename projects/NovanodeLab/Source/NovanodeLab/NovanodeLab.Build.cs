using UnrealBuildTool;

public class NovanodeLab : ModuleRules
{
    public NovanodeLab(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "InputCore", "Json", "JsonUtilities"
        });
    }
}
