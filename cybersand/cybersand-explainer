ELI11:

Cybervox is a pixel-physics engine designed to make falling-sand worlds feel alive without needing to simulate every part of the world at full speed.

Each cell follows compact material rules. Sand falls and settles, water conserves and redistributes its mass, smoke rises through denser materials, and other materials can burn, react, grow, dissolve, or change state. The complexity comes from combining many simple local rules rather than relying on one enormous physics calculation.

The engine is organised into regions that can sleep when stable. A buried block of unmoving stone does not consume the same processing time as an active cloud of smoke or a collapsing pile of sand. When something changes nearby, the affected region and its neighbours are woken automatically.

The simulation runs in a native high-performance backend, while Godot handles the game, controls, presentation, and general scene logic. Communication happens through carefully controlled snapshots and commands, so rendering cannot accidentally corrupt the simulation.

Rigid bodies use a separate physics system, but their occupied area is projected into the pixel world as a solid collision mask. This lets sand, smoke, liquids, characters, and moving objects interact without forcing everything into one expensive system.

The result is a reusable foundation for games and interactive worlds where material behaviour, destruction, chemistry, and visual effects all emerge from the same coherent world model.

ELIPHD-physicist:
  
Cybervox is a hybrid cellular-physics engine intended for large, reactive 2D worlds in which material behaviour is represented primarily through local cell rules rather than continuous fields or object-per-particle dynamics.

The authoritative world is maintained by a native simulation core with sparse chunk storage. Material identity is compact, while mutable state is attached only where required: liquid mass, burn or growth progress, heading, payload, temperature, and similar quantities can be represented through small state fields or optional per-chunk arrays. This avoids imposing the memory cost of every possible physical quantity on every cell.

Material behaviour is expressed through bounded RuleKernel families and immutable material descriptors. Descriptors define density, directional exchange permissions, lateral-flow mode, viscosity-like mobility, state requirements, palette behaviour, and maximum write radius. The current rule system supports density exchange, conserved water transfer, ignition, extinguishing, corrosion, phase changes, growth, agents, cloning, projectiles, and compact reaction logic. It is deliberately not a hierarchy of material objects: kernels are data-oriented, deterministic, and unable to allocate, spawn threads, call Godot, or access unbounded neighbourhoods during the hot path.

The architecture separates local cellular evolution from larger structural events. Ordinary kernels are restricted to small neighbourhoods, currently no more than radius two. Explosions and other potentially wider edits are handled at serialized coordinator boundaries, where their ordering, wake propagation, conservation effects, and dirty-state consequences can be controlled deterministically. This prevents one exceptional reaction from invalidating the assumptions used for parallel local updates.

Parallelism is achieved through four parity-coloured in-place phases over 64×64 scheduling cores, with a barrier between phases. Worker write domains are expanded by the declared rule radius, and same-phase domains are geometrically proven non-overlapping. Scan direction and phase rotation are deterministic, so worker count and completion timing do not alter tested state hashes. A persistent worker pool avoids thread creation overhead.

The engine distinguishes authoritative state change from scheduling eligibility and presentation change. Stable interiors can sleep, while boundary activity and wake observations preserve propagation into dormant regions. Dirty rectangles identify what must be republished; active blocks identify what deserves simulation time. Interest regions further bound the actively simulated world without destroying authoritative state outside them.

Rigid-body coupling is intentionally asymmetric but extensible. Rapier2D remains authoritative for external body transforms, while the cellular core receives a copied, rasterised occupancy mask and returns bounded impact, pressure, displacement, and correction observations. Thus cells perceive moving rigid bodies as obstacles without making live physics objects worker-owned data.

Rendering consumes immutable dirty snapshots rather than the mutable simulation. The GPU can derive bounded material-condition appearance, variation, emission, and glow from compact presentation data. This leaves temperature, pressure, composition, conduction, plasma-like fields, and richer chemistry available as additional fields without requiring a second world model or coupling visual effects directly into authoritative rule execution. The result is a deterministic, bounded approximation framework: sufficiently local and structured for parallel performance, but with explicit seams for future multi-field reactive physics.
