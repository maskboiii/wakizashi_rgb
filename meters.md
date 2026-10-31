# meters.md — захват окна MiniMeters для эффекта «Амбилайт»

## 1. Существующая архитектура

Приложение — PyQt6-хост для подсветки TKL-клавиатуры SinoWealth
(Wakizashi V2 / AULA F87 Pro). Один гарнитурный комплект:

| Файл        | Роль |
|-------------|------|
| `app.py`    | GUI + хост эффектов + амбилайт (весь UI и логика анимаций) |
| `kb.py`     | Низкоуровневый HID-контроль (протокол SinoWealth) |
| `widgets.py`| Кастомные «стеклянные» виджеты (aurora, панели, статус-бар) |
| `theme.py`  | Токены тем (DARK/LIGHT) и QSS-хелперы |
| `cli.py`    | Консольная утилита (detect / color / off) |
| `_scan.py`  | Дамп HID-устройств |

### 1.1 kb.py — устройство
- VID `0x258A`, набор PID (`0x010C` и др.), Feature Report ID `0x06`.
- `Keyboard` открывает lighting-collection (usage_page `0xFF00`) и держит
  firmware в «direct RGB» режиме (`enable_direct_mode`).
- Режим волатильный → нужен keepalive (`KEEPALIVE_S = 0.1`).
- Методы: `set_solid_color`, `set_led_colors(colors)` (полный кадр per-LED),
  `set_per_key(color_map)`, `set_off`, `resolve_index`.
- Раскладка `_F87_KEYS` (87 слотов), `by_name` → индекс LED (`LAYOUTS["F87"]`).

### 1.2 widgets.py
- `AuroraBackground` — фон с градиентом/свечением, кэш в `QPixmap`.
- `KeyboardCanvas` — «стеклянная» подложка под клавиши.
- `GlassPanel` — переиспользуемая стеклянная панель.
- `StatusBar` — статус-полоса с индикатором подключения.

### 1.3 theme.py
- Токены `DARK` / `LIGHT`; `build_qss`, `keycap_base_qss`, `keycap_qss`,
  `swatch_qss`, `draw_glass`, `qcolor`.

### 1.4 app.py — структура
Константы и данные:
- Геометрия окна: `WINDOW_W=800`, `KEYBOARD_H=300`, `TABS_H`, `STATUS_H`, `X_OFFSET`.
- `KEY_MAP` (app.py:76) — координаты и имена клавиш (row, name, x, y, w, h, seq).
- `PALETTE` (178), `UI_ALIASES` (185), `RIGHT_SECTION_KEYS` (189),
  `VK_TO_NAME` (197), `EFFECTS` (223), `GAME_PRESETS` (229).

Хелперы цвета:
- `resolve_led_index` (391) — UI-имя → индекс LED.
- `hsv_to_rgb` (403).
- Амбилайт-математика: `AMBI_SAMPLES` (429), `_SRGB_TO_LINEAR` (433),
  `_linear_to_srgb` (440), `boost_saturation` (449), `apply_brightness` (461),
  `grade_zone` (471).

Классы:
- `AmbilightWorker(QThread)` (478) — захват монитора вне GUI-потока.
  - `run` (495): цикл по `mss`-региону, эмитит `gridReady(list)`.
  - `_sample` (527): режет кадр на `cols×rows` зон.
  - `_zone_color` (543): усреднение в линейном свете + опция «игнор чёрных».
  - Атрибуты: `cols`, `rows`, `hz`, `drop_dark`, `monitor` ({left,top,width,height}).
- `KeyButton(QPushButton)` (572) — добавляет `rightClicked`.
- `MainWindow(QMainWindow)` (585).

MainWindow — ключевые методы:
- UI: `_build_ui` (646), `_build_paint_tab` (682), `_build_effects_tab` (740).
- Настройки: `_build_settings_dialog` (916), `_load_settings` (981),
  `_save_settings` (1043), `_reset_settings` (1058), `_connect_setting_persist`.
- Клавиши/устройство: `_build_keys` (1135), `_connect_device` (1159), `_send` (1316).
- Эффекты: `_on_effect_changed` (1477), `_start_effect` (1492), `_stop_effect` (1517),
  `_toggle_preview` (1530), `_effect_tick` (1555), `_compute_effect` (1596).
- Keepalive/трей: `_keepalive` (1782), `_setup_tray` (1807), `eventFilter` (1834),
  `closeEvent` (1860).

### 1.5 Пайплайн «Амбилайт» (существующий)
1. Настройки в `_build_effects_tab` (783–873): монитор, режим сетки
   («Сетка»/«Колонки»), `cols` (1–16), `rows` (1–6), Гц (5–60), сглаживание,
   насыщенность, яркость, «игнор чёрных полос».
2. `_effective_ambi_grid` (1367) → `(_ambi_cols, _ambi_rows)`.
3. `_rebuild_led_zones` (1385) — по позициям LED (`led_pos`) считает bounding-box
   и присваивает каждому LED зону `cy*cols+cx`; `_active_led_pos` (1373) умеет
   исключать правую секцию.
4. `_current_monitor` (1408) — сопоставляет Qt-экран с mss-монитором
   (с учётом `devicePixelRatio`), отдаёт `{left,top,width,height}`.
5. `_ensure_ambi_worker` (1436) — создаёт/стартует `AmbilightWorker`,
   `_sync_ambi_worker` (1427) прокидывает cols/rows/hz/drop_dark.
6. `_on_ambi_grid` (1457) кладёт захват в `self._ambi_grid`.
7. `_compute_effect` → ветка `"Амбилайт"` (1638): сглаживание зон,
   `grade_zone`, раскладка зон на LED через `self.led_zone`.
8. Fallback: `_legacy_ambi` (1462) через `QScreen.grabWindow`, если `mss` нет.
9. `_effect_tick` (1555) шлёт кадр на клавиатуру (`set_led_colors`) и в превью.

Нюанс: `AmbilightWorker.monitor` — это просто mss-регион, а `mss.grab()`
принимает **произвольный** прямоугольник (не только монитор). Это и есть
точка расширения под захват окна.

### 1.6 Миниметры (внешний контекст)
MiniMeters (direct.audio) — standalone аудиометеринг: модули VU, Waveform,
Spectrogram, Spectrum, Stereometer, Loudness, Oscilloscope; Horizontal-бар,
Stick Mode, pop-out модулей в отдельные окна.
**Публичного API/OSC для чтения данных наружу нет** (на GitHub только
`MiniMetersServer` — плагин, отдающий звук *в* MiniMeters). Поэтому
единственный надёжный путь — **захват окна** MiniMeters и подача его пикселей
в существующий амбилайт.

## 2. Решение (согласовано с пользователем)
- Объект захвата: **выбор окна из списка** видимых окон (авто-подсветка
  MiniMeters по заголовку).
- Встраивание: **переключатель источника в существующем эффекте «Амбилайт»**
  (не новый эффект).
- Раскладка: **общая сетка cols×rows** (маппинг сохраняется как есть).

## 3. План реализации (только app.py, новых pip-зависимостей нет)

### 3.1 Win32-хелперы (ctypes, рядом с AmbilightWorker)
- `list_visible_windows()` → `[(hwnd, title, (left,top,w,h))]` через `EnumWindows`,
  `GetWindowTextW`, `GetWindowRect`, `IsWindowVisible`, `IsIconic`; пропуск
  пустых/свёрнутых/нулевой площади.
- `window_rect(hwnd)` — повторное чтение `GetWindowRect` для трекинга.

### 3.2 UI (в блоке «Амбилайт», после комбо «Монитор», ~app.py:800)
- `ambi_source_combo` = `["Весь монитор", "Окно"]`.
- `ambi_window_combo` (список окон) + кнопка «⟳ Обновить».
- Показ/скрытие комбо окна по источнику.
- `_refresh_windows()` — заполняет список, авто-выбор записи с `minimeters`
  в заголовке (без регистра), иначе первая.

### 3.3 Выбор региона
- `_capture_region()`:
  - «Монитор» → `_current_monitor()` (без изменений).
  - «Окно» → `{"left","top","width","height"}` выбранного hwnd.

### 3.4 Интеграция с worker
- `_ensure_ambi_worker` (1436): вместо `_current_monitor()` брать
  `_capture_region()`.
- Кэш прямоугольника окна, обновление раз в ~0.5 с (переиспользуя по-тиковый
  вызов из `_effect_tick`, без нового таймера).
- Окно не найдено/свёрнуто → `worker.monitor = None`, статус
  «окно MiniMeters не найдено», кадр чёрный (без отката на весь экран).
- `_sync_ambi_worker` (1427): при смене источника регион пересчитывается.

### 3.5 Персист настроек
- `_save_settings` (1043): `ambi/source` (индекс), `ambi/window` (заголовок,
  т.к. hwnd между запусками нестабилен).
- `_load_settings` (981): восстановить + `_refresh_windows()`.
- `_reset_settings` (1058): источник → 0.
- Оба виджета — в цикл `_connect_setting_persist` (868).
- Смена источника/окна → `_rebuild_led_zones` + `_sync_ambi_worker`.

### 3.6 Сетка
Без изменений. Для бара MiniMeters пользователь ставит `rows=1`; можно
одноразово предложить `rows=1`, если окно очень широкое (aspect > ~6:1),
но не навязывать.

## 4. Краевые случаи / риски
- **DPI:** Qt6 — per-monitor aware, `GetWindowRect` обычно уже в физических
  пикселях (как mss). Проверить при масштабе ≠100%; при расхождении — применить
  коэффициент как в `_current_monitor`.
- **Прозрачный фон MiniMeters:** `mss` снимает скомпонованный кадр — в цвет
  попадут обои/окна за модулем.
- **Stick Mode:** окно обычное, захват работает; трекинг подхватит
  перемещение/ресайз.
- **Мультимонитор:** координаты Win32 и mss совместимы (начало — левый-верхний
  угол основного монитора).
- **Заголовок окна:** pop-out модули могут иметь иной заголовок → выбран список
  окон, а не хардкод по имени.

## 5. Verification
- `python app.py` → «Амбилайт», источник «Окно», выбрать MiniMeters →
  клавиатура реагирует на метры.
- Свернуть/закрыть MiniMeters → чёрный кадр + статус; вернуть → работает.
- Масштаб 100% и 125/150% — сверить область захвата.
- `python -c "import app"` — базовая проверка импорта.
