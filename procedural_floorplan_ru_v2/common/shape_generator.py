from __future__ import annotations

import math
import random
from dataclasses import dataclass


ShapeTile = tuple[int, int]


@dataclass(frozen=True)
class Footprint:
    """Хранит итоговый контур здания как дискретный набор тайлов сетки."""

    shape_key: str
    tiles: frozenset[ShapeTile]

    @property
    def tile_count(self) -> int:
        """Возвращает число тайлов, из которых собран footprint."""
        return len(self.tiles)

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Возвращает ограничивающий прямоугольник по минимальным и максимальным координатам."""
        xs = [x for x, _ in self.tiles]
        ys = [y for _, y in self.tiles]
        return min(xs), min(ys), max(xs), max(ys)


def _rect(x0: int, y0: int, width: int, depth: int) -> set[ShapeTile]:
    """Строит прямоугольную область тайлов.

    Как это работает:
    функция перебирает все координаты в диапазонах по X и Y и собирает
    декартово произведение этих диапазонов в множество тайлов. На выходе
    получается заполненный прямоугольник, который затем используется как
    базовый строительный блок для более сложных фигур.
    """
    return {(x, y) for x in range(x0, x0 + width) for y in range(y0, y0 + depth)}


def _shape_min_dims(shape_key: str, min_side_tiles: int) -> tuple[int, int]:
    """Возвращает минимальные габариты footprint для выбранной формы."""
    mins = {
        "rectangle": (min_side_tiles * 2, min_side_tiles * 2),
        "l_shape": (min_side_tiles * 2 + 1, min_side_tiles * 2 + 1),
        "u_shape": (min_side_tiles * 3 + 1, min_side_tiles * 2 + 1),
        "h_shape": (min_side_tiles * 3 + 1, min_side_tiles * 2 + 2),
        "t_shape": (min_side_tiles * 2 + 1, min_side_tiles * 2 + 1),
        "courdoner": (min_side_tiles * 3 + 1, min_side_tiles * 2 + 1),
        "offset": (min_side_tiles * 2 + 1, min_side_tiles * 2 + 1),
    }
    return mins.get(shape_key, mins["rectangle"])


def _derive_base_dims(
    room_count: int,
    house_scale: float,
    min_side_tiles: int,
    shape_key: str,
) -> tuple[int, int]:
    """Оценивает базовые размеры здания по количеству комнат и масштабу.

    Как это работает:
    сначала входные значения нормализуются до безопасного минимума, чтобы
    генератор не получил нулевые или слишком маленькие размеры. Затем из
    числа комнат вычисляется примерная площадь, после чего ширина берётся
    как корень из площади с поправкой на более вытянутую форму, а глубина
    добирается делением площади на найденную ширину.
    """
    rooms = max(1, int(room_count))
    scale = max(0.5, house_scale)
    min_width, min_depth = _shape_min_dims(shape_key, min_side_tiles)

    # Чем выше минимальная сторона комнаты, тем сильнее должен расти общий
    # размер дома, иначе сложные формы схлопываются в fallback и room splits
    # теряют пространство для вариаций.
    base_room_area = max(4.0, float(min_side_tiles * min_side_tiles))
    area_hint = max(min_width * min_depth, int(round(rooms * base_room_area * 1.35 * scale)))
    width = max(min_width, int(round(math.sqrt(area_hint) * 1.35)))
    depth = max(min_depth, int(round(area_hint / width)))

    while width * depth < area_hint:
        if width <= depth:
            width += 1
        else:
            depth += 1
    return width, depth


def _min_side_tiles(min_room_side_m: float) -> int:
    """Переводит ограничение минимальной стороны комнаты в дискретные тайлы 1x1."""
    return max(1, int(math.ceil(min_room_side_m)))


def _rectangle(width: int, depth: int) -> set[ShapeTile]:
    """Возвращает простой прямоугольный footprint без вырезов и смещений."""
    return _rect(0, 0, width, depth)


def _l_shape(width: int, depth: int, min_side_tiles: int) -> set[ShapeTile]:
    """Строит L-образный footprint через вырез угла у полного прямоугольника.

    Как это работает:
    сначала создаётся полный прямоугольник здания, затем из его правого
    верхнего угла вычитается внутренний прямоугольный блок. Размер выреза
    вычисляется как доля от исходной ширины и глубины, но с нижней границей,
    чтобы форма не схлопнулась на маленьких размерах.
    """
    if width < min_side_tiles * 2 or depth < min_side_tiles * 2:
        return _rectangle(width, depth)
    cut_w = min(width - min_side_tiles, max(min_side_tiles, width // 3))
    cut_d = min(depth - min_side_tiles, max(min_side_tiles, depth // 3))
    return _rect(0, 0, width, depth) - _rect(width - cut_w, depth - cut_d, cut_w, cut_d)


def _u_shape(width: int, depth: int, min_side_tiles: int) -> set[ShapeTile]:
    """Строит U-образную форму с центральной выемкой.

    Как это работает:
    берётся полный прямоугольник, после чего из его нижней части вырезается
    центральный прямоугольный проём. Боковые части остаются как «крылья»,
    а задняя часть сохраняет связность всей фигуры.
    """
    if width < min_side_tiles * 3 or depth < min_side_tiles * 2:
        return _rectangle(width, depth)
    wing = max(min_side_tiles, width // 4)
    recess_depth = min(depth - min_side_tiles, max(min_side_tiles, depth // 2))
    inner_width = width - wing * 2
    if inner_width < min_side_tiles:
        return _rectangle(width, depth)
    tiles = _rect(0, 0, width, depth)
    tiles -= _rect(wing, 0, inner_width, recess_depth)
    return tiles


def _h_shape(width: int, depth: int, min_side_tiles: int) -> set[ShapeTile]:
    """Строит H-образную форму из двух вертикальных блоков и поперечной перемычки.

    Как это работает:
    фигура не вычитается из большого прямоугольника, а собирается объединением
    трёх независимых прямоугольников: левой стойки, правой стойки и средней
    горизонтальной перемычки. Такой способ гарантирует предсказуемую форму
    даже при сравнительно небольших размерах здания.
    """
    if width < min_side_tiles * 3 or depth < (min_side_tiles * 2 + 1):
        return _rectangle(width, depth)
    bar = max(min_side_tiles, width // 4)
    if width - bar * 2 < min_side_tiles:
        return _rectangle(width, depth)
    bridge_depth = max(min_side_tiles, depth // 3)
    bridge_y = max(1, (depth - bridge_depth) // 2)
    tiles = set()
    tiles |= _rect(0, 0, bar, depth)
    tiles |= _rect(width - bar, 0, bar, depth)
    tiles |= _rect(0, bridge_y, width, bridge_depth)
    return tiles


def _t_shape(width: int, depth: int, min_side_tiles: int) -> set[ShapeTile]:
    """Строит T-образную форму из верхней перекладины и центральной ножки.

    Как это работает:
    сначала формируется широкая верхняя часть, занимающая весь размер по X,
    затем под ней добавляется узкая центральная секция. Координата стержня
    вычисляется так, чтобы он оказался по центру и визуально образовал букву T.
    """
    if width < (min_side_tiles * 2 + 1) or depth < min_side_tiles * 2:
        return _rectangle(width, depth)
    top_depth = max(min_side_tiles, depth // 3)
    stem_width = max(min_side_tiles, width // 3)
    stem_x = (width - stem_width) // 2
    tiles = set()
    tiles |= _rect(0, depth - top_depth, width, top_depth)
    tiles |= _rect(stem_x, 0, stem_width, depth - top_depth)
    return tiles


def _courdoner(width: int, depth: int) -> set[ShapeTile]:
    """Строит форму курдонёра с внутренним парадным двором.

    Как это работает:
    фигура собирается из двух боковых крыльев и заднего объёма, который
    замыкает композицию с трёх сторон. Передняя центральная часть остаётся
    пустой и формирует двор. Если при маленьких размерах внутренний проём
    не помещается, функция перестраховывается и возвращает полный прямоугольник.
    """
    wing = max(2, width // 5)
    recess_depth = max(2, int(round(depth * 0.45)))
    inner_width = max(2, width - wing * 2)
    rear_depth = max(2, depth - recess_depth)
    tiles = set()
    tiles |= _rect(0, 0, wing, depth)
    tiles |= _rect(width - wing, 0, wing, depth)
    tiles |= _rect(0, recess_depth, width, rear_depth)
    if inner_width <= 0:
        tiles |= _rect(0, 0, width, depth)
    return tiles


def _offset(width: int, depth: int) -> set[ShapeTile]:
    """Строит составную форму из двух прямоугольников со сдвигом.

    Как это работает:
    нижний объём создаётся как базовый прямоугольник, а верхний накладывается
    на него с горизонтальным смещением. Перекрытие по одной полосе тайлов
    сохраняет связность footprint и создаёт силуэт с «уступом».
    """
    lower_depth = max(2, depth // 2 + 1)
    upper_depth = max(2, depth - lower_depth + 1)
    shift = max(1, width // 4)
    upper_width = max(3, width - shift)
    tiles = set()
    tiles |= _rect(0, 0, width, lower_depth)
    tiles |= _rect(shift, lower_depth - 1, upper_width, upper_depth)
    return tiles


def generate_footprint(
    shape_key: str,
    room_count: int,
    min_room_side_m: float,
    house_scale: float,
    seed: int,
) -> Footprint:
    """Генерирует footprint по ключу формы и параметрам здания.

    Как это работает:
    функция сначала инициализирует генератор случайных чисел тем же seed,
    чтобы последовательность вычислений была воспроизводимой. Затем она
    получает базовые размеры, выбирает конкретный алгоритм генерации по
    `shape_key`, строит множество тайлов и упаковывает его в неизменяемый
    объект `Footprint`. Если ключ формы неизвестен, используется прямоугольник
    как безопасный вариант по умолчанию.
    """
    random.seed(seed)
    min_side_tiles = _min_side_tiles(min_room_side_m)
    width, depth = _derive_base_dims(room_count, house_scale, min_side_tiles, shape_key)
    generators = {
        "rectangle": lambda w, d: _rectangle(w, d),
        "l_shape": lambda w, d: _l_shape(w, d, min_side_tiles),
        "u_shape": lambda w, d: _u_shape(w, d, min_side_tiles),
        "h_shape": lambda w, d: _h_shape(w, d, min_side_tiles),
        "t_shape": lambda w, d: _t_shape(w, d, min_side_tiles),
        "courdoner": _courdoner,
        "offset": _offset,
    }
    generator = generators.get(shape_key, _rectangle)
    tiles = generator(width, depth)
    return Footprint(shape_key=shape_key, tiles=frozenset(sorted(tiles)))
