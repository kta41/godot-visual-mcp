# Catálogo de Plantillas ComfyUI para Videojuegos 2D (Godot 4)

Este directorio contiene **28 plantillas de workflows en formato API de ComfyUI** listas para generar assets de videojuegos 2D e integrarlos directamente en proyectos Godot 4 (`res://`) a través de `generate_asset`.

Todas las plantillas están sincronizadas en:
- `workflows/*.json` (catálogo editable y de referencia en la raíz del repositorio).
- `src/godot_visual_mcp/resources/workflows/*.json` (recursos empaquetados servidos por el MCP en `godot://catalog/workflows` y `list_workflows`).

---

## Arquitectura del Grafo y Soporte LoRA

Cada plantilla incluye un grafo completo de ComfyUI utilizando exclusivamente nodos core estándar:
- **Nodo `1` (`CheckpointLoaderSimple`)**: Carga el modelo base (`${ckpt_name}`).
- **Nodo `2` (`LoraLoader`)**: Carga un modelo LoRA primario (`${lora_name}`, `${lora_strength_model}`, `${lora_strength_clip}`).
  - **Activación / Bypass automático**: Si no se especifica `lora_name` (ni variable de entorno `COMFYUI_DEFAULT_LORA`) en una plantilla estándar, `prepare_workflow()` reconecta automáticamente el modelo y el CLIP desde el nodo `1` y omite el nodo `LoraLoader` para no requerir archivos LoRA adicionales. Si pasas `lora_name="mi_lora.safetensors"`, el nodo `LoraLoader` permanece activo en cualquiera de las 28 plantillas.
- **Nodo `2b` (`LoraLoader` secundario en `lora_dual_style_character`)**: Permite apilar un segundo LoRA (p. ej. LoRA de estilo pixel-art + LoRA de personaje/paleta).
- **Nodo `3` (`CLIPTextEncode`)**: Prompt positivo especializado por tipo de asset 2D + `${prompt}`.
- **Nodo `4` (`EmptyLatentImage`)**: Dimensiones de generación (`${width}`, `${height}`, `${batch}`).
- **Nodo `5` (`CLIPTextEncode`)**: Prompt negativo curado contra artefactos 3D/mixels/fondos sucios + `${negative_prompt}`.
- **Nodo `6` (`KSampler`)**: Muestreador configurable (`${seed}`, `${steps}`, `${cfg}`, `${sampler_name}`, `${scheduler}`, `${denoise}`).
- **Nodo `7` (`VAEDecode`)** y **Nodo `8` (`SaveImage`)**.

---

## Tabla de las 28 Plantillas 2D

| Categoría | Plantilla (`workflow`) | Nodo Godot Destino | Gen. Recomendada | Tamaño Target 2D | `remove_background` | `crop` | Descripción |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Personajes** | `character` | `Sprite2D` | 512×512 | 64×64 | Sí | Sí | Héroe o NPC de cuerpo completo con silueta legible |
| | `character_portrait` | `TextureRect` | 512×512 | 128×128 | Sí | No | Retrato / busto expresivo para diálogos RPG / Visual Novel |
| | `character_turnaround` | `Sprite2D` | 768×512 | 384×256 | Sí | Sí | Hoja multi-vista (frente, perfil, espalda) alineada |
| | `enemy_monster` | `Sprite2D` | 512×512 | 96×96 | Sí | Sí | Criaturas, enemigos y jefes 2D de alto contraste |
| **Sprites y VFX** | `sprite` | `Sprite2D` | 512×512 | 64×64 | Sí | Sí | Sprite 2D / pixel-art general de entidad u objeto centrado |
| | `spritesheet_strip` | `AnimatedSprite2D` | 1024×256 | 256×64 | Sí | No | Tira horizontal de frames de animación para `SpriteFrames` |
| | `vfx_effect` | `AnimatedSprite2D` | 512×512 | 128×128 | Sí | Sí | Explosiones, tajos, fuego e impactos mágicos |
| | `projectile_hazard` | `Area2D` | 512×512 | 32×32 | Sí | Sí | Proyectiles, balas, flechas, láseres y trampas |
| | `particle_mask_alpha` | `GPUParticles2D` | 512×512 | 64×64 | No | No | Máscara blanca sobre fondo negro para sistemas de partículas |
| **Entornos y Tiles** | `background` | `Sprite2D` | 1024×576 | 640×360 | No | No | Escenario 2D completo con profundidad atmosférica |
| | `parallax_layer` | `Parallax2D` | 1024×512 | 640×320 | Sí | No | Capa horizontal separable por plano para scroll lateral |
| | `tileset_topdown` | `TileMapLayer` | 512×512 | 128×128 | No | No | Tiles ortogonales vista cenital 90° (RPG / roguelike) |
| | `tileset_platformer` | `TileMapLayer` | 512×512 | 64×64 | Sí | No | Bloques de terreno y plataformas en vista lateral |
| | `tileset_autotile_3x3` | `TileMapLayer` | 512×512 | 96×96 | Sí | No | Parche 3×3 (esquinas, bordes, centro) para terrenos `TileSet` |
| | `isometric_tile_prop` | `TileMapLayer` | 512×512 | 128×128 | Sí | Sí | Bloques y estructuras en proyección isométrica 2:1 |
| | `environment_prop` | `Sprite2D` | 512×512 | 64×64 | Sí | Sí | Props aislados (árboles, cofres, rocas, farolas, ruinas) |
| **UI, Ítems y Menús** | `icon` | `TextureRect` | 512×512 | 64×64 | No | No | Iconos de habilidades, estados (buff/debuff) y logros |
| | `item_loot` | `TextureRect` | 512×512 | 64×64 | Sí | Sí | Objetos de inventario (armas, pociones, llaves, reliquias) |
| | `ui_ninepatch_panel` | `NinePatchRect` | 512×512 | 128×128 | Sí | Sí | Marcos HUD 9-slice con esquinas simétricas y centro uniforme |
| | `game_logo_title` | `TextureRect` | 768×512 | 384×256 | Sí | Sí | Emblema / crest principal para pantalla de título |
| **Materiales y Luces** | `seamless_texture` | `Polygon2D` | 512×512 | 256×256 | No | No | Textura repetible sin costuras (agua, lava, piedra, hierba) |
| | `normal_map_2d` | `CanvasTexture` | 512×512 | 64×64 | No | No | Mapa de normales tangent-space para `PointLight2D` |
| | `shader_noise_mask` | `ShaderMaterial` | 512×512 | 256×256 | No | No | Mapa en escala de grises para disolución/UV en `.gdshader` |
| **LoRA / Control** | `lora_pixel_art` | `Sprite2D` | 512×512 | 64×64 | Sí | Sí | Flujo con LoRA preconfigurado para pixel-art 16-bit estricto |
| | `lora_hand_drawn_2d` | `Sprite2D` | 512×512 | 256×256 | Sí | Sí | Flujo con LoRA para arte 2D ilustrado / cel-shaded |
| | `lora_dual_style_character`| `Sprite2D` | 512×512 | 128×128 | Sí | Sí | Dual-LoRA en cadena (estilo artístico + personaje/paleta) |
| | `sprite_variation_img2img`| `Sprite2D` | 512×512 | 64×64 | Sí | Sí | Img2Img (`LoadImage` + `VAEEncode`) para variantes y daño |
| | `controlnet_pose_guide` | `Sprite2D` | 512×512 | 64×64 | Sí | Sí | ControlNet para fijar pose o silueta de colisión exacta |

---

## Pipeline Pixel-Art en un Solo Paso (`target_width`, `target_height`, `palette`)

Los modelos de difusión generan mejor en `512×512` o `1024×1024`, pero en Godot 2D necesitas el sprite final en su resolución real de juego (`32×32`, `64×64`, `128×128`) y con una paleta controlada:

```json
{
  "prompt": "medieval iron broadsword with glowing rune",
  "workflow": "lora_pixel_art",
  "output": "res://assets/items/rune_sword.png",
  "width": 512,
  "height": 512,
  "lora_name": "pixel_art_v2.safetensors",
  "lora_strength_model": 0.9,
  "remove_background": true,
  "crop": true,
  "target_width": 64,
  "target_height": 64,
  "pixel_perfect": true,
  "palette": "pico8"
}
```

## Variables de Entorno Soportadas

- `COMFYUI_ENDPOINT`: URL del servidor ComfyUI (por defecto `http://127.0.0.1:8188`).
- `COMFYUI_ALLOWED_ENDPOINTS`: Lista separada por comas de endpoints adicionales permitidos.
- `COMFYUI_DEFAULT_CHECKPOINT`: Checkpoint por defecto si no se pasa `ckpt_name` (por defecto `v1-5-pruned-emaonly.safetensors`).
- `COMFYUI_DEFAULT_LORA`: Modelo LoRA primario por defecto si no se pasa `lora_name`.
- `COMFYUI_SECONDARY_LORA`: Modelo LoRA secundario por defecto para `lora_dual_style_character`.
- `COMFYUI_DEFAULT_CONTROLNET`: Modelo ControlNet por defecto para `controlnet_pose_guide`.
