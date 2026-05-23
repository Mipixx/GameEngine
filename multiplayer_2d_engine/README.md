# 2D Top-Down Multiplayer Game Engine

Полноценный движок для 2D top-down игр с поддержкой мультиплеера, редактором уровней и утилитой для запуска сервера.

## Структура проекта

```
multiplayer_2d_engine/
├── engine/                 # Игровой движок
│   ├── game_engine.py     # Основной движок
│   └── launch_game.py     # Утилита запуска игры
├── editor/                 # Редактор уровней
│   ├── level_editor.py    # Визуальный редактор
│   └── launch_editor.py   # Утилита запуска редактора
├── server/                 # Серверная часть
│   ├── game_server.py     # WebSocket сервер
│   └── launch_server.py   # Утилита запуска сервера
└── assets/                 # Ресурсы игры
```

## Требования

- Python 3.8+
- pygame
- websockets
- asyncio

## Установка зависимостей

```bash
pip install pygame websockets asyncio
```

## Компоненты

### 1. Игровой движок (Engine)

**Функции:**
- 2D рендеринг с камерой
- Поддержка мультиплеера через WebSocket
- Управление игроком (WASD/стрелки)
- Система игровых объектов
- Загрузка/сохранение уровней

**Запуск игры:**

```bash
# Одиночная игра
python engine/launch_game.py

# Мультиплеер (подключение к серверу)
python engine/launch_game.py --multiplayer --host localhost --port 8765 --name "Игрок"

# С загрузкой уровня
python engine/launch_game.py --load-level level.json

# Полный экран
python engine/launch_game.py --fullscreen
```

**Управление в игре:**
- `W/A/S/D` или `Стрелки` - Перемещение
- `ESC` - Выйти

### 2. Редактор уровней (Editor)

**Функции:**
- Визуальное создание и редактирование объектов
- Настройка свойств объектов
- Сохранение/загрузка уровней в JSON
- Экспорт данных уровня
- Масштабирование и навигация

**Запуск редактора:**

```bash
python editor/launch_editor.py

# С пользовательским разрешением
python editor/launch_editor.py --width 1920 --height 1080
```

**Управление в редакторе:**
- `Левая кнопка мыши` - Выбрать/Создать объект
- `Перетаскивание` - Переместить объект / Панорамирование камеры
- `W/A/S/D` или `Стрелки` - Панорамирование камеры
- `+/-` - Приблизить/Отдалить
- `G` - Включить/выключить сетку
- `Delete/Backspace` - Удалить выбранный объект
- `ESC` - Снять выделение

**Инструменты редактора:**
- **Select** - Выбор и перемещение объектов
- **Create** - Создание новых объектов
- **Rectangle** - Тип объекта: прямоугольник
- **Spawn Point** - Тип объекта: точка спавна
- **Save Level** - Сохранить уровень в level.json
- **Load Level** - Загрузить уровень из level.json
- **Toggle Grid** - Показать/скрыть сетку
- **Delete** - Удалить выбранный объект
- **Export to JSON** - Экспортировать данные уровня в консоль

### 3. Игровой сервер (Server)

**Функции:**
- WebSocket сервер для мультиплеера
- Поддержка множественных клиентов
- Синхронизация позиций игроков
- Трансляция состояния игры
- Обработка подключений/отключений

**Запуск сервера:**

```bash
# Сервер на порту по умолчанию (8765)
python server/launch_server.py

# На конкретном порту
python server/launch_server.py --port 9000

# Только локальные подключения
python server/launch_server.py --localhost

# Публичный сервер (доступен извне)
python server/launch_server.py --public

# С подробным выводом
python server/launch_server.py -v
```

## Пример использования

### Шаг 1: Запустить сервер

```bash
python server/launch_server.py --port 8765
```

### Шаг 2: Создать уровень в редакторе

```bash
python editor/launch_editor.py
```

- Создайте объекты на уровне
- Нажмите "Save Level" для сохранения

### Шаг 3: Запустить игру

В одном терминале (игрок 1):
```bash
python engine/launch_game.py --multiplayer --name "Player1" --load-level level.json
```

В другом терминале (игрок 2):
```bash
python engine/launch_game.py --multiplayer --name "Player2" --load-level level.json
```

## API Движка

### GameEngine

```python
from engine.game_engine import GameEngine

# Создание движка
engine = GameEngine(screen_width=1280, screen_height=720, title="My Game")

# Включить мультиплеер
engine.set_multiplayer(host="localhost", port=8765, player_name="Player")

# Загрузить уровень
engine.load_level(level_data)

# Запустить игру
engine.run()
```

### NetworkClient

```python
from engine.game_engine import NetworkClient

client = NetworkClient(host="localhost", port=8765)
await client.connect("PlayerName")
await client.send_move(x, y)
await client.disconnect()
```

## Формат уровня (JSON)

```json
{
  "world_width": 2000,
  "world_height": 2000,
  "objects": [
    {
      "id": "abc12345",
      "x": 100,
      "y": 100,
      "width": 100,
      "height": 100,
      "object_type": "rectangle",
      "properties": {
        "color": [100, 100, 100]
      }
    }
  ]
}
```

## Расширение

### Добавление новых типов объектов

В `game_engine.py` в методе `draw()`:

```python
if obj.object_type == "rectangle":
    # рисование прямоугольника
elif obj.object_type == "circle":
    # рисование круга
elif obj.object_type == "your_type":
    # ваше рисование
```

### Добавление новой логики игры

Создайте подкласс `GameEngine`:

```python
class MyGameEngine(GameEngine):
    def update(self, dt):
        super().update(dt)
        # ваша логика обновления
    
    def draw(self):
        super().draw()
        # ваше рисование
```

## Лицензия

MIT License
