// =============================================================================
// Voxel Island — Reference example (what a good model output looks like)
// =============================================================================
// This is NOT required to be perfect — it shows the expected shape, groups,
// and use of the provided `random()`. The benchmark runtime provides THREE
// and `random()`; the model builds only geometry.

export function createScene({ THREE, random }) {
  const root = new THREE.Group();
  root.name = "VoxelIsland";

  const voxel = 2; // block size

  // ---------- Materials ----------
  const matGrass = new THREE.MeshLambertMaterial({ color: 0x567d46 });
  const matDirt = new THREE.MeshLambertMaterial({ color: 0x8b5a2b });
  const matStone = new THREE.MeshLambertMaterial({ color: 0x7f8c8d });
  const matWood = new THREE.MeshLambertMaterial({ color: 0x5d4037 });
  const matLeaf = new THREE.MeshLambertMaterial({ color: 0x2d5a27 });
  const matApple = new THREE.MeshLambertMaterial({ color: 0xc62828 });
  const matWater = new THREE.MeshLambertMaterial({ color: 0x1565c0, transparent: true, opacity: 0.85 });
  const matFlower = new THREE.MeshLambertMaterial({ color: 0xffeb3b });

  const box = (s) => new THREE.BoxGeometry(s, s, s);
  const add = (group, geo, mat, x, y, z, name) => {
    const m = new THREE.Mesh(geo, mat);
    m.position.set(x, y, z);
    m.name = name || "voxel";
    m.castShadow = true;
    m.receiveShadow = true;
    group.add(m);
    return m;
  };

  // ---------- Terrain ----------
  const terrain = new THREE.Group();
  terrain.name = "Terrain";
  const size = 22;
  const heightMap = [];
  for (let x = 0; x < size; x++) {
    heightMap[x] = [];
    for (let z = 0; z < size; z++) {
      const dx = x - size / 2;
      const dz = z - size / 2;
      const dist = Math.sqrt(dx * dx + dz * dz);
      const h = Math.max(1, Math.round(6 - dist / 2.2 + (random() - 0.5) * 2));
      heightMap[x][z] = h;
    }
  }
  for (let x = 0; x < size; x++) {
    for (let z = 0; z < size; z++) {
      const h = heightMap[x][z];
      const wx = (x - size / 2) * voxel;
      const wz = (z - size / 2) * voxel;
      // grass top
      add(terrain, box(voxel), matGrass, wx, h * voxel, wz, `grass_${x}_${z}`);
      // dirt & stone underneath, narrowing
      for (let y = h - 1; y >= Math.max(0, h - 4); y--) {
        const narrow = 1 + Math.max(0, (y - h + 4) / 4); // narrower at bottom
        if (random() < narrow * 0.85) {
          const mat = y > h - 2 ? matDirt : matStone;
          add(terrain, box(voxel * narrow), mat, wx, y * voxel, wz, `under_${x}_${y}_${z}`);
        }
      }
    }
  }
  root.add(terrain);

  // ---------- Trees ----------
  const trees = new THREE.Group();
  trees.name = "Trees";
  const treeCount = 4;
  for (let t = 0; t < treeCount; t++) {
    const tx = (random() - 0.5) * size * 0.8 * voxel;
    const tz = (random() - 0.5) * size * 0.8 * voxel;
    // find height at this x,z (approx)
    const ix = Math.floor((tx / voxel) + size / 2);
    const iz = Math.floor((tz / voxel) + size / 2);
    const th = (ix >= 0 && ix < size && iz >= 0 && iz < size)
      ? heightMap[ix][iz]
      : 4;
    const ty = th * voxel + voxel;
    // trunk
    for (let y = 0; y < 5; y++) {
      add(trees, box(voxel * 0.7), matWood, tx, ty + y * voxel, tz, `trunk_${t}_${y}`);
    }
    // canopy
    for (let dy = -2; dy <= 2; dy++) {
      for (let dx = -2; dx <= 2; dx++) {
        for (let dz = -2; dz <= 2; dz++) {
          if (Math.abs(dx) + Math.abs(dy) + Math.abs(dz) <= 3 && random() > 0.25) {
            add(trees, box(voxel * 0.9), matLeaf,
              tx + dx * voxel, ty + 5 * voxel + dy * voxel, tz + dz * voxel, `leaf_${t}_${dx}_${dy}_${dz}`);
          }
        }
      }
    }
    // apples
    for (let a = 0; a < 3; a++) {
      add(trees, box(voxel * 0.45), matApple,
        tx + (random() - 0.5) * voxel * 2,
        ty + 5 * voxel + (random() - 0.5) * voxel,
        tz + (random() - 0.5) * voxel * 2,
        `apple_${t}_${a}`);
    }
  }
  root.add(trees);

  // ---------- Waterfall ----------
  const waterfall = new THREE.Group();
  waterfall.name = "Waterfall";
  const wx0 = (size / 2 - 2) * voxel;
  const wz0 = (size / 2 - 2) * voxel;
  for (let y = 0; y < 8; y++) {
    add(waterfall, box(voxel), matWater, wx0, y * voxel, wz0, `water_${y}`);
  }
  root.add(waterfall);

  // ---------- Vegetation ----------
  const vegetation = new THREE.Group();
  vegetation.name = "Vegetation";
  for (let v = 0; v < 20; v++) {
    const vx = (random() - 0.5) * size * 0.9 * voxel;
    const vz = (random() - 0.5) * size * 0.9 * voxel;
    add(vegetation, box(voxel * 0.5), matFlower, vx, 1 * voxel, vz, `flower_${v}`);
  }
  root.add(vegetation);

  return root;
}
