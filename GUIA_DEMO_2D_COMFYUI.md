# Guía Práctica: Preparando una Demo 2D en Godot 4 con ComfyUI y `godot-visual-mcp`

Este documento muestra un **caso de uso completo de principio a fin** para construir la base visual y escénica de una demo jugable de un **Action-RPG 2D estilo 16-bits** (un caballero explorando una cripta, enfrentándose a un nigromante esqueleto y recogiendo botín, con HUD de diálogo e iluminación dinámica 2D) combinando ComfyUI y las herramientas de `godot-visual-mcp`.

---

## 0. Preparación previa (Variables de entorno del servidor MCP)

Antes de iniciar el flujo con el agente MCP, configura la ruta de tu proyecto de Godot 4 y tu instancia de ComfyUI:

```bash
export GODOT_PROJECT_ROOT="/ruta/a/mi_juego_godot"
export COMFYUI_ENDPOINT="http://127.0.0.1:8188"
export COMFYUI_DEFAULT_CHECKPOINT="sd15_game_assets.safetensors"
export COMFYUI_DEFAULT_LORA="pixel_art_16bit.safetensors"
```

---

## Paso 1: Explorar el proyecto y consultar el catálogo de plantillas 2D

Pídele al agente:
> *"Revisa el proyecto Godot y dime qué workflows 2D tenemos disponibles para personajes, mapas, efectos y UI."*

El agente invocará:
1. `inspect_project()` → Verifica que `project.godot` existe y detecta el binario instalado de Godot 4.
2. `list_workflows()` → Devuelve las **28 plantillas 2D** junto con la resolución de generación recomendada (`recommended_generation_size`), el tamaño final en el motor (`recommended_target_size`), sugerencias de post-procesado (`remove_background`, `crop`) y el nodo de Godot 4 de destino (`Sprite2D`, `AnimatedSprite2D`, `TileMapLayer`, `Parallax2D`, `NinePatchRect`, `GPUParticles2D`, `CanvasTexture`).

---

## Paso 2: Generar al Héroe y al Enemigo (LoRA + Downscale Pixel-Perfect + Paleta)

Los modelos de difusión en ComfyUI rinden mejor generando a `512×512`, pero en un juego 2D necesitas que el asset final tenga su resolución real de juego (`64×64` o `96×96`) sin bordes borrosos. Con `generate_asset` todo ocurre en **una sola operación atómica**:

### A. El Héroe (usando Dual-LoRA: estilo pixel-art + paleta de fantasía oscura)
Plantilla: `workflows/lora_dual_style_character.json`

```json
{
  "tool": "generate_asset",
  "arguments": {
    "prompt": "armored paladin knight with glowing blue broadsword",
    "workflow": "lora_dual_style_character",
    "output": "res://assets/characters/hero_idle.png",
    "width": 512,
    "height": 512,
    "lora_name": "pixel_art_16bit.safetensors",
    "lora_strength_model": 0.9,
    "secondary_lora_name": "dark_fantasy_palette.safetensors",
    "secondary_lora_strength_model": 0.7,
    "remove_background": true,
    "crop": true,
    "target_width": 64,
    "target_height": 64,
    "pixel_perfect": true,
    "seed": 1001
  }
}
```

### B. El Enemigo / Jefe (con cuantización a paleta `pico8`)
Plantilla: `workflows/enemy_monster.json`

```json
{
  "tool": "generate_asset",
  "arguments": {
    "prompt": "undead skeleton necromancer with green fire staff",
    "workflow": "enemy_monster",
    "output": "res://assets/enemies/skeleton_mage.png",
    "width": 512,
    "height": 512,
    "remove_background": true,
    "crop": true,
    "target_width": 96,
    "target_height": 96,
    "pixel_perfect": true,
    "palette": "pico8",
    "seed": 2002
  }
}
```

---

## Paso 3: Generar una variante "Fase 2 / Dañado" del jefe (`Img2Img`)

Para cuando al jefe le quede poca vida, usamos `workflows/sprite_variation_img2img.json` (`LoadImage` + `ImageScale` + `VAEEncode`) con `denoise: 0.45` sobre el sprite base. Esto mantiene **la misma silueta y caja de colisión (`CollisionShape2D`)**, cambiando únicamente los detalles de daño y color:

```json
{
  "tool": "generate_asset",
  "arguments": {
    "prompt": "cracked bones, shattered armor, enraged red flame aura",
    "workflow": "sprite_variation_img2img",
    "input_image": "skeleton_mage.png",
    "denoise": 0.45,
    "output": "res://assets/enemies/skeleton_mage_enraged.png",
    "width": 512,
    "height": 512,
    "remove_background": true,
    "crop": true,
    "target_width": 96,
    "target_height": 96
  }
}
```

---

## Paso 4: Generar el Entorno, Tiles e Iluminación Dinámica 2D

1. **Fondo Parallax (`workflows/parallax_layer.json` para `Parallax2D`):**
   ```json
   {
     "tool": "generate_asset",
     "arguments": {
       "prompt": "gothic underground cathedral arches and distant stone pillars",
       "workflow": "parallax_layer",
       "output": "res://assets/environment/crypt_bg.png",
       "width": 1024,
       "height": 512,
       "remove_background": true,
       "crop": false,
       "target_width": 640,
       "target_height": 320
     }
   }
   ```

2. **Terreno y Plataformas (`workflows/tileset_platformer.json` y `workflows/tileset_autotile_3x3.json` para `TileMapLayer`):**
   ```json
   {
     "tool": "generate_asset",
     "arguments": {
       "prompt": "mossy dungeon cobblestone platform block",
       "workflow": "tileset_platformer",
       "output": "res://assets/tiles/crypt_floor_tile.png",
       "width": 512,
       "height": 512,
       "remove_background": true,
       "crop": false,
       "target_width": 64,
       "target_height": 64
     }
   }
   ```

3. **Mapa de Normales 2D (`workflows/normal_map_2d.json` para `CanvasTexture` + `PointLight2D`):**
   ```json
   {
     "tool": "generate_asset",
     "arguments": {
       "prompt": "carved dungeon stone wall bricks relief",
       "workflow": "normal_map_2d",
       "output": "res://assets/environment/stone_wall_normal.png",
       "width": 512,
       "height": 512,
       "remove_background": false,
       "crop": false,
       "target_width": 64,
       "target_height": 64
     }
   }
   ```

---

## Paso 5: Generar UI, Retratos, Botín y Máscaras de Partículas

1. **Marco de Diálogo 9-Slice (`workflows/ui_ninepatch_panel.json` para `NinePatchRect`):**
   ```json
   {
     "tool": "generate_asset",
     "arguments": {
       "prompt": "dark iron and gold RPG dialogue frame",
       "workflow": "ui_ninepatch_panel",
       "output": "res://assets/ui/dialogue_box.png",
       "width": 512,
       "height": 512,
       "remove_background": true,
       "crop": true,
       "target_width": 128,
       "target_height": 128
     }
   }
   ```

2. **Retrato del Héroe (`workflows/character_portrait.json` para `TextureRect`):**
   Genera `res://assets/ui/hero_portrait.png` (`128×128`) para mostrar junto al texto del diálogo.

3. **Ítem de Inventario (`workflows/item_loot.json`) y Partículas (`workflows/particle_mask_alpha.json` para `GPUParticles2D`):**
   - `res://assets/items/health_potion.png` (`32×32`) aislado y recortado.
   - `res://assets/vfx/spark_mask.png` (`64×64`) en blanco sobre negro para tintar con `color_ramp` en `GPUParticles2D`.

---

## Paso 6: Ensamblar la Escena `.tscn` y Verificar Importación Headless en Godot 4

Con todos los assets validados en `res://`, el agente construye la escena y verifica que Godot 4 la importe sin errores:

1. **Crear la escena base (`create_scene`):**
   ```json
   {
     "tool": "create_scene",
     "arguments": {
       "output": "res://scenes/CryptDemo.tscn",
       "root_type": "Node2D",
       "root_name": "CryptDemo"
     }
   }
   ```

2. **Poblar la escena con los sprites generados (`add_sprite_to_scene`):**
   - `add_sprite_to_scene(scene="res://scenes/CryptDemo.tscn", texture="res://assets/environment/crypt_bg.png", node_name="Background", overwrite=true)`
   - `add_sprite_to_scene(scene="res://scenes/CryptDemo.tscn", texture="res://assets/characters/hero_idle.png", node_name="Player", overwrite=true)`
   - `add_sprite_to_scene(scene="res://scenes/CryptDemo.tscn", texture="res://assets/enemies/skeleton_mage.png", node_name="Boss", overwrite=true)`

3. **Validar referencias y ejecutar Godot en modo Headless (`validate_scene` + `verify_import`):**
   - `validate_scene(path="res://scenes/CryptDemo.tscn")` → Comprueba que la sintaxis `.tscn` y todas las rutas `res://` sean válidas.
   - `verify_import()` → Lanza Godot 4 en modo `--headless`, genera los archivos `.import` oficiales del motor y confirma que todas las texturas y escenas están listas para abrirse directamente en el editor.
