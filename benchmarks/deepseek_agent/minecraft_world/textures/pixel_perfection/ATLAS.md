# Atlas layout (Pixel Perfection)

`atlas.png` is 80x64 pixels: **5 columns x 4 rows** of 16x16 tiles.
`atlas.base64.txt` is the base64 encoding embedded in `../index.html`.

| Row | Column 0 | Column 1 | Column 2 | Column 3 | Column 4 |
|---|---|---|---|---|---|
| 0 | grass top | grass side | dirt | stone | gravel |
| 1 | tree side | tree top | leaves | water (frame 1) | sand |
| 2 | chest front | chest side | chest top | planks | brick |
| 3 | furnace front | furnace side | furnace top | glass | stone (spare) |

Source files (in `source/`):

- `default_grass.png`, `default_grass_side.png`, `default_dirt.png`,
  `default_stone.png`, `default_gravel.png`
- `default_tree.png`, `default_tree_top.png`, `default_leaves.png`,
  `default_water_source_animated.png`, `default_sand.png`
- `default_chest_front.png`, `default_chest_side.png`, `default_chest_top.png`,
  `default_wood.png`, `default_brick.png`
- `default_furnace_front.png`, `default_furnace_side.png`,
  `default_furnace_top.png`, `default_glass.png`

The texture files are CC BY-SA 4.0; see `NOTICE.md` and
`LICENSE-CC-BY-SA-4.0.txt`.
