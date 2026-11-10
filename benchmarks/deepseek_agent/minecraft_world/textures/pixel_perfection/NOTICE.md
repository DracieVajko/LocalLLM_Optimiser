# Pixel Perfection textures — notice and license

The files in `source/` and the generated `atlas.png` are derived from
**Pixel Perfection** by Hugh "XSSheep" Rutland, obtained from the Minetest
texture-pack port:

- Source: https://github.com/minetest-texture-packs/Pixel-Perfection
- Author: Hugh "XSSheep" Rutland (Minetest port by the minetest-texture-packs contributors)
- License: **Creative Commons Attribution-ShareAlike 4.0 International**
  (CC BY-SA 4.0) — full text in `LICENSE-CC-BY-SA-4.0.txt`
- License URL: https://creativecommons.org/licenses/by-sa/4.0/

## Changes

- Selected 19 basic block textures (grass top/side, dirt, stone, gravel,
  tree side/top, leaves, water, sand, chest front/side/top, planks, brick,
  furnace front/side/top, glass).
- Cropped the animated water strip to its first 16x16 frame.
- Scaled the 14x14 chest tiles to 16x16.
- Packed the tiles into a 5x4 atlas (`atlas.png`, 80x64) and embedded the
  atlas as a base64 data URI in `../index.html`.

## License scope

The source textures, the atlas and the embedded texture data are licensed
under **CC BY-SA 4.0**. If you extract or modify them, you must keep the
attribution and share the resulting texture work under CC BY-SA 4.0.

The HTML/JavaScript code around the textures remains under the repository's
MIT license. The two licenses apply to their respective parts.

Attribution to use: **"Pixel Perfection by XSSheep, CC BY-SA 4.0"**.
