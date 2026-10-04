"""Explicit operator-selected map drafts; never applied on connection."""
from copy import deepcopy
import math


def competition_field(values):
    """Measured 3.40 x 2.40 m field, dimensions along paint centre lines.

    Inner clear dimensions: field 3.35 x 2.35, circle .85, goal area 1.145 x .24.
    Add .05 m paint width to get centre-line dimensions. Goal height/colour
    stay unchanged; goal width is still the drawing's unverified 1 m.
    """
    result = deepcopy({k: v for k, v in values.items() if k.startswith('field.')})
    geometry = result['field.geometry']
    geometry.update(length=3.4, width=2.4, circle_diameter=.9, circle_measured=True,
                    paint_width=.05,
                    carpet_length=max(4., geometry['carpet_length']),
                    carpet_width=max(3., geometry['carpet_width']))
    for i, x in enumerate((-1.7, 1.7)):
        result[f'field.goal.{i}'].update(x=x, y=0., width=1., measured=False)
    for key, mark in result.items():
        if key.startswith('field.mark.'):
            mark['enabled'] = False
    marks = []
    def add(kind, x, y, size, angle=0.):
        marks.append(dict(enabled=True, kind=kind, x=x, y=y, size=size, size2=size,
                          angle=angle, width=min(geometry['paint_width'], size)))
    for x in (-.75, .75):
        for y in (-.65, 0., .65):
            add('disk', x, y, .05)
    for y in (-.76, 0., .76):
        add('line', 0., y, .155)  # Along X, across the halfway line.
    # Measured goal areas: 29 cm deep and 119.5 cm wide along paint centres.
    for sign in (-1, 1):
        add('line', sign*1.41, 0., 1.195, math.pi/2)
        for y in (-.5975, .5975):
            add('line', sign*1.555, y, .29)
    for i, mark in enumerate(marks):
        result[f'field.mark.{i:02d}'] = mark
    return result
