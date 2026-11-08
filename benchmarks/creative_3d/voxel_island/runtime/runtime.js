// =============================================================================
// Voxel Island — Creative 3D Benchmark Runtime (runtime.js)
// =============================================================================
// The model generates ONE file: scene.js
// It must export exactly one function:
//   export function createScene({ THREE, random }) { ... return new THREE.Group(); }
//
// The runtime:
//   1. Loads Three.js + OrbitControls from vendor/
//   2. Provides THREE and a deterministic seeded `random()`
//   3. Imports ./scene.js and calls createScene()
//   4. Adds the returned Group to the scene, renders with orbit controls
//   5. Reports errors cleanly to the HUD
//
// The model MUST NOT generate HTML, CSS, camera, lights, or renderer code.
// Those belong to this runtime. The model generates only procedural 3D geometry.
// =============================================================================

// If you run this directly without a bundler, ensure:
//   vendor/three.module.js        (Three.js ES module)
//   vendor/jsm/controls/OrbitControls.js
