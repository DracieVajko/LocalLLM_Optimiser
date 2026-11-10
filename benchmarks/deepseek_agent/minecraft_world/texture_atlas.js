/* Predefined 16x16 pixel-art texture atlas for the minecraft_world benchmark.
 *
 * Usage inside a single-file HTML page (after Three.js is loaded):
 *
 *   const textures = createVoxelAtlas(THREE);
 *   const geo = textures.blockGeometry(
 *     textures.tile.grassTop,
 *     textures.tile.grassSide,
 *     textures.tile.dirt
 *   );
 *   const mesh = new THREE.InstancedMesh(geo, textures.materials.opaque, count);
 *
 * `textures.atlas` is a THREE.CanvasTexture using NearestFilter, so the pixel
 * art stays crisp. The atlas is generated at runtime: no image files, no
 * external assets, still one self-contained HTML file.
 */
function createVoxelAtlas(THREE) {
  const TILE = 16;
  const COLS = 4;
  const ROWS = 4;

  const canvas = document.createElement("canvas");
  canvas.width = TILE * COLS;
  canvas.height = TILE * ROWS;
  const ctx = canvas.getContext("2d");

  function noise(x, y, seed) {
    const n = Math.sin(x * 127.1 + y * 311.7 + seed * 74.7) * 43758.5453;
    return n - Math.floor(n);
  }

  function px(col, row, x, y, color) {
    ctx.fillStyle = color;
    ctx.fillRect(col * TILE + x, row * TILE + y, 1, 1);
  }

  function fill(col, row, colors, seed) {
    for (let y = 0; y < TILE; y += 1) {
      for (let x = 0; x < TILE; x += 1) {
        px(col, row, x, y, colors[Math.floor(noise(x, y, seed) * colors.length)]);
      }
    }
  }

  // Row 0: grass top, grass side, dirt, stone.
  fill(0, 0, ["#4caf50", "#57b85a", "#3f8f43", "#66c26a"], 1);
  for (let y = 0; y < TILE; y += 1) {
    for (let x = 0; x < TILE; x += 1) {
      const edge = 4 + Math.floor(noise(x, y, 2) * 2);
      const color = y < edge
        ? ["#4caf50", "#3f8f43", "#57b85a"][Math.floor(noise(x, y, 3) * 3)]
        : ["#8d5a3b", "#7a4a2f", "#9b6644"][Math.floor(noise(x, y, 4) * 3)];
      px(1, 0, x, y, color);
    }
  }
  fill(2, 0, ["#8d5a3b", "#7a4a2f", "#9b6644", "#6b3f28"], 5);
  fill(3, 0, ["#8b939b", "#7d858d", "#9aa2aa", "#6f777f"], 6);

  // Row 1: wood side, wood top, leaves, water.
  for (let y = 0; y < TILE; y += 1) {
    for (let x = 0; x < TILE; x += 1) {
      const stripe = x % 4 === 0 || (x % 7 === 0 && y % 3 === 0);
      px(0, 1, x, y, stripe ? "#5a341c" : "#7a4a2a");
    }
  }
  for (let y = 0; y < TILE; y += 1) {
    for (let x = 0; x < TILE; x += 1) {
      const d = Math.abs(x - 8) + Math.abs(y - 8);
      px(1, 1, x, y, d % 5 === 0 ? "#5a341c" : "#8a5731");
    }
  }
  fill(2, 1, ["#2f8f3a", "#257a30", "#3aa347", "#1f6b28"], 7);
  fill(3, 1, ["#2f7fd4", "#3a8fe0", "#266bb8", "#55a6ef"], 8);

  // Row 2: chest, planks, roof, path.
  fill(0, 2, ["#b5722f", "#9d5f24", "#c98443"], 9);
  for (let y = 0; y < TILE; y += 1) {
    for (let x = 0; x < TILE; x += 1) {
      px(1, 2, x, y, y % 5 === 0 ? "#8a5731" : "#b98a52");
    }
  }
  fill(2, 2, ["#a33a2f", "#8f2f26", "#bb4a3d", "#7c241c"], 10);
  fill(3, 2, ["#b9a98f", "#a8977d", "#c7b79c", "#94846c"], 11);

  const atlas = new THREE.CanvasTexture(canvas);
  atlas.magFilter = THREE.NearestFilter;
  atlas.minFilter = THREE.NearestFilter;
  atlas.encoding = THREE.sRGBEncoding;
  atlas.needsUpdate = true;

  const tile = {
    grassTop: [0, 0], grassSide: [1, 0], dirt: [2, 0], stone: [3, 0],
    woodSide: [0, 1], woodTop: [1, 1], leaves: [2, 1], water: [3, 1],
    chest: [0, 2], planks: [1, 2], roof: [2, 2], path: [3, 2]
  };

  // Remap the six box faces into the selected atlas tiles.
  function blockGeometry(top, side, bottom) {
    const geo = new THREE.BoxGeometry(1, 1, 1);
    const uv = geo.attributes.uv;
    const faces = [side, side, top, bottom, side, side];
    const du = 1 / COLS;
    const dv = 1 / ROWS;
    for (let f = 0; f < 6; f += 1) {
      const t = faces[f];
      const u0 = t[0] * du;
      const v0 = 1 - (t[1] + 1) * dv;
      for (let i = 0; i < 4; i += 1) {
        const index = f * 4 + i;
        uv.setXY(index, u0 + uv.getX(index) * du, v0 + uv.getY(index) * dv);
      }
    }
    uv.needsUpdate = true;
    return geo;
  }

  const opaque = new THREE.MeshLambertMaterial({ map: atlas });
  const water = new THREE.MeshLambertMaterial({
    map: atlas,
    transparent: true,
    opacity: 0.82
  });

  return {
    atlas,
    tile,
    blockGeometry,
    materials: { opaque, water }
  };
}
