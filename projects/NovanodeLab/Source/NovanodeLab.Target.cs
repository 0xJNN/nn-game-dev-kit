using UnrealBuildTool;
using System.Collections.Generic;

public class NovanodeLabTarget : TargetRules
{
    public NovanodeLabTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("NovanodeLab");
    }
}
