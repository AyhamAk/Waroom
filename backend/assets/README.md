# WarRoom Asset Library

Tagged glTF library that the **Asset Lead** agent picks from before falling back to procedural primitives. Real models = the single biggest visible jump in game quality — it's the difference between "tech demo" and "looks like a game".

## Quick start

```bash
# from backend/
python -m assets.bootstrap          # ~6 small CC0 models, including animated Fox
python -m assets.bootstrap --extras # add Sponza, BrainStem, FlightHelmet (heavier)

# rebuild the index after dropping more files into library/
python -m assets.index_library
```

After bootstrap, `library.json` will populate and the next 3D Game Studio session will use real glTFs.

## Adding more assets

Drop glTF or `.glb` files into `library/<source>/`:

```
library/
├── khronos/         # Khronos sample models (downloaded via bootstrap)
├── kenney/          # drop Kenney.nl pack contents here
├── quaternius/      # drop Quaternius pack contents here
└── mixamo/          # drop Mixamo character + animations here
```

Then run `python -m assets.index_library` to rebuild `library.json`. Tag inference auto-runs from filenames + folder names.

### Sidecar metadata override

If you want explicit tags or to fix auto-inferred ones, drop a `<file>.glb.meta.json` next to the asset:

```json
{
  "type":    "character_rigged",
  "tags":    ["humanoid", "scifi", "robot"],
  "anims":   ["idle", "walk", "run"],
  "tris":    3120,
  "credit":  "<Original author + link>",
  "license": "CC0"
}
```

Sidecar values **always** win over inferred ones.

## Asset types (the type enum)

The Asset Lead picks by `type`. Use these exact names — anything else gets ignored.

| type | What it is |
|---|---|
| `character_rigged` | Player or named NPC with skeleton + animation clips |
| `enemy_rigged`     | Hostile NPC, usually with at least walk + attack |
| `weapon_handheld`  | First/third-person weapon model |
| `prop_static`      | Crates, barrels, lamps, decoration |
| `environment_tile` | Floor/wall/ceiling building blocks |
| `vfx`              | Particle sprites, decals (rarely glTFs) |
| `hdri`             | Equirectangular HDR environment map |

## Where the files end up at runtime

When the Asset Lead picks an id, the bridge `shutil.copy`'s the file into:

```
<workspace>/<game_session_id>/game/public/assets/<filename>.glb
```

Vite's static `public/` directory passes it through to the build, served at `/assets/<filename>.glb`. The runtime's `engine.assets.loadGltf(id, '/assets/...glb')` just works — animations clone via `engine.assets.spawn(id).anim`.

## License

Each entry stores its own `license` + `credit` in the index. Bootstrap-fetched models are CC BY 4.0 / CC0 / public domain (per the Khronos Sample Models repo). Anything you drop in must have its license recorded. The `credit` field is meant to be displayed in your in-game credits screen so authors are attributed properly.

## Recommended packs to drop in (manual)

- **Kenney.nl** — `nl/assets/<pack>` zips. Download, extract, drop into `library/kenney/`. Re-index. Best low-poly stylized base.
- **Quaternius.com** — character/monster/scifi/medieval packs. Download zips, extract `.glb` files into `library/quaternius/`. Re-index. Best for stylized characters.
- **Mixamo** (Adobe) — pick a base character, download as `.fbx`, convert to `.glb` (Blender does this in 30s), then download additional animations as separate `.fbx` from the same character to keep skeletons compatible. Drop in `library/mixamo/`.
