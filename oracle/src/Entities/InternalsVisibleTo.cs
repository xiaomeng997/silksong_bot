// The offline checks in oracle/tests/EntitiesCheck call the pure helpers directly (Entities, and the M2 exports:
// MenuExporter, GateWatch, SceneDumper.IsSubScene, HeroExporter.TagDmgLeft, HitTap.OwnDamage, FrameExporter.HfAgeCap).
[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("EntitiesCheck")]
