# Blender + LLM Integrácia — Návod

## Prehľad

Existujú **dva prístupy** na generovanie 3D scén pomocou LLM:

### Prístup 1: Generate .py (automatizovaný, pre benchmarky)

LLM vygeneruje Python skript (`build_scene.py`), ktorý sa spustí v Blenderi cez CLI.

**Ako to funguje:**
1. Model vygeneruje `build_scene.py` (Blender Python API)
2. Sandbox runner spustí: `blender --background --python build_scene.py`
3. Blender vytvorí `scene.blend`
4. Runner skontroluje: binary, mesh count, camera, light, height variety

**Výhody:** Automatické, headless, reproducibilné, skórovateľné
**Nevýhody:** Modely robia API chyby (pre-5.x idiomy, syntax errors)

**Overený príklad (DeepSeek reference, skóruje 1.0):**
- Skript: [build_scene.py](benchmarks/deepseek_agent/blender_city/build_scene.py)
- Výsledok: [scene.blend](benchmarks/deepseek_agent/blender_city/scene.blend) (233 KB, 138 budov, 4 landmarky, rieka, park, kamera, svetlo)
- Spustenie: `blender.exe --background --python build_scene.py` → exit 0

**Blender 5.3 API poznámky (pre modely):**
- `scene.collection` je read-only → použi `bpy.data.collections.new('Name')` + `children.link()`
- Kamera: `bpy.ops.object.camera_add(location=(x,y,z))` (NIE `bpy.ops.camera_add`)
- Svetlo: `bpy.ops.object.light_add(type='SUN', location=(x,y,z))`
- Mesh: `bpy.ops.mesh.primitive_cube_add(size=1, location=(x,y,z))`
- Uloženie: `bpy.ops.wm.save_as_mainfile(filepath='scene.blend')`

**Časté chyby modelov:**
| Chyba | Príčina | Riešenie |
|---|---|---|
| `AttributeError: scene.collection.name is read-only` | Pre-5.x idiom | Použi `collections.new()` + `children.link()` |
| `TypeError: 'module' object is not callable` | `bpy.ops.camera_add()` namiesto `bpy.ops.object.camera_add()` | Plná cesta k operátoru |
| `SyntaxError: unmatched ')'` | Syntaktická chyba v generovanom kóde | Skontroluj v Python IDE pred spustením |
| `RuntimeError: Collection already in Scene Collection` | Duplicitný link | Kontroluj pred linknutím |
| `scene.blend not created` | Skript neskončil `save_as_mainfile` | Skontroluj blender.log |

### Prístup 2: BlenderMCP addon (interaktívny, pre používateľa)

LLM ovláda Blender priamo cez MCP (Model Context Protocol) — namiesto generovania .py súborov posielá príkazy (create_cube, add_light, atď.) a Blender ich vykonáva okamžite.

**Inštalácia (automatická):**
```powershell
# Stiahni a nainštaluj addon
git clone https://github.com/ahujasid/blender-mcp.git "$env:TEMP\blender-mcp"
Copy-Item "$env:TEMP\blender-mcp\addon.py" "$env:APPDATA\Blender Foundation\Blender\5.3\scripts\addons\blender_mcp.py"
```

**Inštalácia (manuálna):**
1. Stiahni `addon.py` z https://github.com/ahujasid/blender-mcp
2. Blender → Edit → Preferences → Add-ons → Install → vyber `addon.py`
3. Zapni addon (zaškrtni checkbox)
4. Server sa auto-spustí na port 9876

**Použitie s LLM:**
1. Otvor Blender (GUI) — addon sa auto-spustí
2. V Claude/Cursor pridaj MCP server: `uvx blender-mcp` alebo `mcp-for-blender`
3. LLM môže priamo ovládať Blender (create_cube, add_light, render, atď.)

**Obmedzenie**: Addon nefunguje v `--background` mode (vyžaduje GUI). Pre automatizované benchmarky zostáva `.py` prístup.

### Porovnanie prístupov

| Vlastnosť | Generate .py | BlenderMCP addon |
|---|---|---|
| Automatizované (CI/benchmark) | ✅ | ❌ (vyžaduje GUI) |
| Interaktívne (user) | ❌ | ✅ |
| Syntax errors | ❌ (modely robia chyby) | ✅ (LLM posielá validné príkazy) |
| Vizuálna kontrola | ❌ | ✅ (real-time preview) |
| Skórovateľné | ✅ | ❌ (harder to automate) |
| Rýchlosť | Pomalé (generovanie + spustenie) | Rýchle (priame príkazy) |

### Odporúčanie
- **Pre benchmarky**: použi `.py` prístup (už implementovaný v sandbox runneri)
- **Pre interaktívne použitie**: použi BlenderMCP addon (nainštalovaný)
- **Pre hybrid**: LLM generuje .py, runner ho spustí, ak crashne, pošle chybu na opravu (repair loop)