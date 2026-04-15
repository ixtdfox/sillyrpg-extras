from __future__ import annotations

import bpy

from ..common.utils import quantize_025
from ..domain.walls import WallRun as PerimeterRun
from ..domain.walls import WallSegment


# Добавляет один boundary interval в группу для последующего merge.
# Как это работает:
# входной отрезок сразу снапится к сетке 0.25 и кладётся в список по ключу
# линии. Дальше эти интервалы будут слиты в непрерывные wall runs.
def add_grouped_edge(
    grouped_edges: dict[tuple, list[tuple[float, float]]],
    key: tuple,
    start: float,
    end: float,
) -> None:
    # Все интервалы сразу снапим к сетке 0.25, чтобы дальше merge и split
    # работали в одной и той же координатной системе без плавающих хвостов.
    grouped_edges.setdefault(key, []).append((quantize_025(start), quantize_025(end)))


# Сливает соседние интервалы одной линии в непрерывные wall runs.
# Как это работает:
# spans сортируются по координате старта и затем последовательно склеиваются,
# если следующий начинается ровно там, где закончился предыдущий. На выходе
# получается набор непрерывных отрезков без промежуточных дублей.
def merge_spans(*, run_factory, run_args: tuple, spans: list[tuple[float, float]]) -> list:
    merged: list = []
    current_start = None
    current_end = None

    for span_start, span_end in sorted(spans):
        if current_start is None:
            current_start = span_start
            current_end = span_end
            continue
        # Сливаем только вплотную примыкающие spans. Если между ними есть даже
        # маленький зазор, это уже два разных run-а, и их нельзя превращать в
        # одну стену, иначе геометрия перепрыгнет через пустое место.
        if abs(span_start - current_end) < 1e-6:
            current_end = span_end
            continue
        merged.append(run_factory(*run_args, current_start, current_end))
        current_start = span_start
        current_end = span_end

    if current_start is not None and current_end is not None:
        merged.append(run_factory(*run_args, current_start, current_end))
    return merged


# Режет отрезок на модульные куски длиной не больше `module_width`.
# Как это работает:
# курсор последовательно двигается от `start` к `end`, каждый раз отрезая
# следующий кусок длиной до `module_width`. Все координаты при этом держатся
# в сетке 0.25, чтобы последующие wall segments были детерминированными.
def split_interval(start: float, end: float, module_width: float) -> list[tuple[float, float]]:
    segments: list[tuple[float, float]] = []
    cursor = quantize_025(start)
    end = quantize_025(end)
    while cursor < end - 1e-6:
        # Держим каждый модуль в той же сетке 0.25, что и вся остальная
        # генерация стен. Благодаря этому wall meshes и metadata остаются
        # предсказуемыми независимо от длины исходного run-а.
        next_cursor = min(end, quantize_025(cursor + module_width))
        if next_cursor <= cursor:
            next_cursor = end
        segments.append((cursor, next_cursor))
        cursor = next_cursor
    return segments


# Переводит абстрактный сегмент в размеры box-геометрии и мировой центр.
# Как это работает:
# функция берёт внутреннюю линию стены, применяет corner caps и trims на
# концах, затем вычисляет размер box-а и смещает его центр наружу на
# половину толщины относительно boundary line.
def segment_geometry(segment: WallSegment) -> tuple[float, float, float, tuple[float, float, float]]:
    if segment.orientation == "x":
        # start/end описывают внутреннюю линию стены вдоль оси X. Cap-ы
        # удлиняют сегмент на концах, а trim-ы наоборот подрезают его там,
        # где соседняя ортогональная стена уже занимает этот угловой квадрант.
        start = quantize_025(segment.start - segment.cap_start + segment.trim_start)
        end = quantize_025(segment.end + segment.cap_end - segment.trim_end)
        center_x = round((start + end) * 0.5, 6)
        center_y = round(
            # Для внешних и внутренних стен line всегда трактуется как
            # внутренняя грань стены. Поэтому центр меша смещается наружу
            # относительно этой грани ровно на половину толщины.
            segment.line + (segment.thickness * 0.5 if segment.side == "north" else -segment.thickness * 0.5),
            6,
        )
        return (
            quantize_025(end - start),
            quantize_025(segment.thickness),
            quantize_025(segment.height),
            (center_x, center_y, round(segment.base_z + segment.height * 0.5, 6)),
        )

    # Для вертикальной стены всё то же самое, только длина откладывается уже
    # по оси Y, а смещение толщины идёт по X.
    start = quantize_025(segment.start - segment.cap_start + segment.trim_start)
    end = quantize_025(segment.end + segment.cap_end - segment.trim_end)
    center_y = round((start + end) * 0.5, 6)
    center_x = round(
        segment.line + (segment.thickness * 0.5 if segment.side == "east" else -segment.thickness * 0.5),
        6,
    )
    return (
        quantize_025(segment.thickness),
        quantize_025(end - start),
        quantize_025(segment.height),
        (center_x, center_y, round(segment.base_z + segment.height * 0.5, 6)),
    )


# Строит прямоугольный параллелепипед с центром в начале координат.
# Как это работает:
# функция вычисляет половины размеров по трём осям, создаёт восемь вершин
# симметрично вокруг нуля и собирает из них шесть quad-граней box mesh-а.
def build_box_mesh(mesh: bpy.types.Mesh, *, size_x: float, size_y: float, size_z: float) -> None:
    # Геометрия стены во всём аддоне сведена к одному простому box mesh.
    # Вся "умная" логика живёт не в топологии, а в вычислении размеров и
    # мирового центра конкретного сегмента.
    hx = size_x * 0.5
    hy = size_y * 0.5
    hz = size_z * 0.5
    verts = [
        (-hx, -hy, -hz),
        (hx, -hy, -hz),
        (hx, hy, -hz),
        (-hx, hy, -hz),
        (-hx, -hy, hz),
        (hx, -hy, hz),
        (hx, hy, hz),
        (-hx, hy, hz),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
