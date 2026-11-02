using UnrealBuildTool;
using System.Collections.Generic;

public class NovanodeLabEditorTarget : TargetRules
{
    public NovanodeLabEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("NovanodeLab");
    }
}
