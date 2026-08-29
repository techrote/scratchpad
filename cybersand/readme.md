
1. Move with `A`/`D` and hold Space for jetpack thrust.
2. Pan with the arrow keys and press `F` to toggle follow/free camera mode.
3. Paint with the left mouse button and erase with the right mouse button.
4. Select prototype paint-tool slots with `1`–`6` (currently Sand, Water, Wall,
   Smoke, Paste, and Slush respectively), or use `Q`/`E` (Page Up/Page Down
   remain aliases) to cycle all 79 paintable materials. Use `Shift+Q`/`Shift+E`
   to jump between core/reactive, medieval, industrial, and luminous groups.
5. Press `C` to toggle coherent/calm emission. Normal emission preserves the
   fast spray/splash behavior. Coherent Water delays lateral spread for 12
   simulation ticks, then resumes ordinary flow so later edge falls still spray.
6. Press `T` to toggle the current Water surface-adhesion comparison. The native
   solver retains a small supported film by default; disabling it removes that
   threshold without changing gravity or density.
7. Press `V` to cycle the rendered logical viewport through 320×180, 480×270,
   640×360, and 960×540. Press `B` independently to cycle simulation margins
   through 0×0, 32×36, 128×128, and 256×256 pixels. The 1920×1080 game window
   aspect-fits the selected logical view; painting uses the same fitted rectangle.
8. Press `L` to compare the selected interest window with whole-world
    simulation, `K` to toggle temporal snapshot smoothing, `H` to cycle render
    publication through 30/45/60 Hz, `F3` to hide/show debug statistics, `G` to
    disable/enable material glow, `P` to pause, and `R` to reset.

Three red rectangles fall from above the character spawn after start/reset. They
use ordinary Godot `RigidBody2D` nodes backed by the vendored Rapier2D v0.35.2
PhysicsServer. The sandbox disables automatic space stepping, applies the newest
cellular response, advances Rapier once, batch-reads active transforms, flushes
once, and copies body state to the cellular worker. Wall pixels are merged into
static Rapier rectangles, so hard contact is solved once; fluid/particle samples
still provide bounded two-way forces. The worker receives no live Node or RID.

Paint slots and material IDs are separate namespaces. The current UI mapping is
`1→Sand (ID 2)`, `2→Water (ID 3)`, `3→Wall (ID 1)`, `4→Smoke (ID 4)`,
`5→Paste (ID 20)`, and `6→Slush (ID 21)`. Changing a key/slot mapping does not
change simulation identity. Painting is retained as a test/gameplay emitter;
equipment, enemies, and fixed or dynamic spawners can enqueue the same generic
material-emission command without using a paint slot.

The complete manual material list, interaction expectations, and controls are
in `docs/MATERIAL_LAB.md`. The construction IDs, visual grammar, performance
cost, and scene recipes are indexed in
`docs/systems/themed-construction-materials.md`.
