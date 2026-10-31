# audio.md — захват звука с ПК, анализатор и вывод на клавиатуру

## 1. Цель
Добавить аудио-реактивные эффекты: захват системного звука с ПК (loopback
дефолтного вывода, WASAPI), анализ (спектр / волна / уровень), рендер
анализатора в окне приложения и стрим цветов на клавиатуру в реальном времени.

## 2. Контекст существующей архитектуры (см. также meters.md)
- `AmbilightWorker` (app.py:478) — образец фонового `QThread` с сигналом
  `gridReady(list)`; GUI не блокируется.
- `_effect_tick` (app.py:1555) — единая точка отправки кадра
  `keyboard.set_led_colors(colors)` и обновления превью.
- `_compute_effect` (app.py:1596) — ветвление по `self.active_effect`.
- `led_pos` / `led_to_name` (app.py:1135) — координаты LED на сетке 800×300.
- `_active_led_pos` (app.py:1373) — умеет исключать правую секцию.
- `EFFECTS` (app.py:223), `_on_effect_changed` (app.py:1477) — показ/скрытие
  блоков настроек под конкретный эффект (как `ambi_widget`, `game_widget`).
- `hsv_to_rgb` (app.py:403), `_preview_effect` (app.py:1585), `keycap_qss`
  (theme.py:210) — цвет/превью.
- Персист: `_load_settings` (981), `_save_settings` (1043),
  `_reset_settings` (1058), `_connect_setting_persist` (1033).
- Аудио-поток по смыслу повторяет пайплайн амбилайта (фоновый воркер →
  сигнал → `_compute_effect` → LED).

## 3. Библиотеки и зависимости
- **SoundCard** — захват loopback (чистый Python + CFFI, WASAPI).
- **numpy** — FFT / DSP.
- Установка: `pip install soundcard numpy`.
- Обе — опциональные, как `mss`: импорт в `try/except`; без них аудио-эффекты
  показывают статус «установите soundcard и numpy».
- Известный баг SoundCard на Windows: запись в 1 канал даёт мусор → всегда
  открываем стерео и микшируем в моно.

## 4. Поток данных
```
Default Output (WASAPI loopback)
  → soundcard Microphone.recorder().record(numframes=block)
     → AudioWorker(QThread): окно Ханна, DC-remove, микс в моно
        → numpy rfft → dB → лог/mel-полосы → attack/release
           → signal bandsReady(bands, wave, level)
              → MainWindow._on_audio(data)         [GUI-поток, хранит последнее]
                 ├─ SpectrumWidget.set_data(...)   [рендер в окне]
                 └─ _effect_tick → _compute_effect("...аудио...") → set_led_colors
```

## 5. Стадия 1 — Захват звука (`audio.py`)
Класс `AudioWorker(QThread)`:
- Параметры: `samplerate=48000`, `block=2048`, `device_name`, `bands`,
  `scale` ("log"/"mel"/"lin"), `fmin=30`, `fmax=16000`, `attack`, `release`,
  `gain_db`, `floor_db=-80`, `mode`, `mono=True`.
- `run()`:
  1. `spk = sc.default_speaker()` (или выбранное устройство);
     `mic = sc.get_microphone(spk.name, include_loopback=True)`.
  2. `with mic.recorder(samplerate=self.samplerate, blocksize=self.block*4)
     as rec:` цикл `data = rec.record(numframes=self.block)` (frames×channels).
  3. препроцесс: микс в моно, окно Ханна, вычитание DC.
  4. анализ (см. стадию 2) → `self.bandsReady.emit(...)`.
  5. `isInterruptionRequested()` — выход; при ошибке/смене устройства —
     переоткрытие с backoff.
- Список устройств: `sc.all_microphones(include_loopback=True)`; дефолт —
  loopback дефолтного speaker.

## 6. Стадия 2 — Анализатор
Чистые функции в `audio.py` (тестируемы без звука):
- `make_band_edges(sr, fft_size, n_bands, fmin, fmax, scale)` — границы
  FFT-бинов на каждую полосу (log / mel / linear).
- `spectrum_db(block, window, sr)` — `np.fft.rfft`, нормировка на усиление
  окна, перевод в dB.
- `band_levels(spec_db, edges)` — уровень полосы (max или mean).
- `EnvelopeTracker` — attack/release сглаживание по полосам (состояние).
- `normalize_db(x, floor_db, ceil_db)` → 0..1; `rms_level(block)` для VU.
- `waveform(block, ncols)` — прореженные сэмплы для осциллографа.

`SpectrumWidget(QWidget)` (в `widgets.py`):
- хранит последние `bands`, `wave`, `level`, `mode`;
- `set_data(...)` + `paintEvent` рисует бары / заливку / волну с градиентом
  по токенам темы; скруглённые столбцы;
- перерисовка с ограничением ~30–60 fps.

## 7. Стадия 3 — Рендер на клавиатуру
Новые пункты в `EFFECTS` (app.py:223): **«Спектр»**, **«Спектр 2D»**,
**«Осциллограф»**, **«Аудио-пульс»**. Общая ветка в `_compute_effect`
(app.py:1596), вход — последние данные воркера.

Маппинг частоты на LED: по `led_pos` x-координата нормализуется
`min_x..max_x → [0,1]`, затем в индекс полосы (лог-шкала на выбор). Реверс —
существующий чекбокс; исключение правой секции — через `_active_led_pos`.

- **Спектр (заливка в стиле MiniMeters):** частота по x, амплитуда по y;
  нижние ряды загораются первыми, столбец заполняется до уровня полосы.
  Чем громче — тем ярче (`value = level**0.75`). Цвет — градиент MiniMeters
  (тёмно-фиолетовый → маджента → красно-оранжевый) по высоте относительно
  уровня; у кромки волны — светлый контур (белый), как линия спектра.
- **Спектр 2D:** x = частота, y = уровень; LED горит, если
  `1 - y_norm <= level(band(x))`; яркость = уровень, цвет — выбранная схема.
- **Осциллограф:** сэмпл волны привязан к x LED; амплитуда → яркость,
  знак → оттенок; цвет = `effect_color` / радужный.
- **Аудио-пульс:** общий уровень (RMS/басы) → яркость всей клавиатуры
  (аналог «Дыхания», управляемый `level`); цвет = `effect_color` / радужный.

Отправка без изменений: `_effect_tick` → `set_led_colors` + превью.

## 8. UI (таб «Эффекты»)
Новый `self.audio_widget` (по образцу `ambi_widget`), видим для аудио-эффектов:
- Живой `SpectrumWidget` (высота ~70 px) вверху блока.
- Строка 1: `Устройство:` combo (loopback-устройства) + кнопка `⟳`.
- Строка 2: `Полос:` spin (4–64), `Шкала:` combo (Лог/Mel/Линейная),
  `Гейн (дБ):` slider, `Пол (дБ):` spin.
- Строка 3: `Атака:` slider, `Спад:` slider, `Цвет:` combo
  (MiniMeters / Радужный / Статичный).
- Строка 4: чекбоксы `«Исключать правую секцию»`, `«Моно»` (реверс — общий).
- `_on_effect_changed`: `audio_widget.setVisible(text in AUDIO_EFFECTS)`;
  запуск/останов `AudioWorker` через `_ensure_audio_worker()` /
  `_stop_audio_worker()`.

## 9. Настройки / персист
- Ключи `audio/*`: device, bands, scale, gain, floor, attack, release, color,
  exclude_right, mono.
- Правки в `_load_settings` / `_save_settings` / `_reset_settings` +
  добавление виджетов в `_connect_setting_persist`.

## 10. Упаковка
- Новый `requirements.txt`: `soundcard`, `numpy`.
- `WakizashiRGB.spec`: `collect_all('soundcard')` и `collect_all('numpy')` в
  `try/except` (как сделано для `mss`). SoundCard — CFFI, dlopen системных
  библиотек, доп. DLL не требуется.

## 11. Краевые случаи / риски
- ASIO / exclusive mode / DRM-звук → loopback может отдавать тишину
  (то же ограничение, что у MiniMeters).
- Задержка: сумма буфера записи и тика (~33 мс); блок 1024–2048.
- Смена дефолтного устройства вывода → переоткрытие потока.
- Нет loopback/устройства → статус-сообщение, пустой (чёрный) кадр.
- CPU: FFT в отдельном потоке, numpy отпускает GIL.
- 1-канальный поток → принудительно стерео.

## 12. Verification
- `python -c "import soundcard, numpy"`.
- Тестовый тон на выводе → уровни растут в `SpectrumWidget`.
- Проверка каждого режима на клавиатуре (бары / 2D / осциллограф / пульс).
- Смена устройства вывода → переоткрытие без перезапуска.
- Тишина → все LED тёмные.

## 13. Порядок реализации
1. [x] `audio.py`: захват + DSP-функции; консольный smoke-тест.
2. [x] `AudioWorker(QThread)` + сигнал; интеграция в `MainWindow`.
3. [x] `SpectrumWidget` в `widgets.py`.
4. [x] Эффекты в `_compute_effect` + `EFFECTS` + UI-блок настроек.
5. [x] Персист настроек.
6. [x] Упаковка (`WakizashiRGB.spec`, `requirements.txt`).
7. [x] Прогон проверок из раздела 12.
