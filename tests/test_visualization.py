"""
@file    tests/test_visualization.py
@brief   The figures, and the colour measurement that keeps them legible.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-07

@details
Two jobs.

First, verify the MEASUREMENT before trusting anything it says. palette_check
implements CIEDE2000 from the standard, and a wrong implementation would
happily bless an illegible palette. The Sharma, Wu & Dalal (2005) test data
is the published answer key, so the checker is checked against it before the
palettes are checked against the checker.

Second, hold the palettes to their floors. Defect D-02 was a palette that
called itself validated while failing on four counts, and it survived twelve
build steps because no test could contradict a docstring. These tests can.

@note These do not assert what a figure LOOKS like — pixels are not a thing
    to unit-test. They assert the properties a figure needs in order to be
    readable at all, plus that every file a caller asked for got written.
"""

import os

import pytest

import visualization
from visualization import LIGHT, DARK, THEMES, use_theme
from tests.palette_check import (check_theme, ciede2000, contrast_ratio,
                                 separation, simulate,
                                 CONTRAST_FLOOR, DELTA_FLOOR, VISIONS)


# --- the measurement itself --------------------------------------------------

# Sharma, Wu & Dalal (2005), "The CIEDE2000 Color-Difference Formula", Table 1.
# Every pair the standard publishes an answer for that exercises a different
# branch: the hue-angle wrap, the neutral-axis case, the blue-region rotation.
SHARMA = [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
    ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
    ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0009), 7.1792),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
]


@pytest.mark.parametrize("lab1,lab2,expected", SHARMA)
def test_ciede2000_matches_published_test_data(lab1, lab2, expected):
    """The distance metric agrees with the standard's own answer key."""
    assert ciede2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)


def test_ciede2000_is_zero_for_identical_colours():
    assert ciede2000((50.0, 10.0, -20.0), (50.0, 10.0, -20.0)) == pytest.approx(0.0)


def test_contrast_ratio_extremes():
    """Black on white is the 21:1 ceiling; a colour against itself is 1:1."""
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=1e-3)
    assert contrast_ratio("#3a7bd5", "#3a7bd5") == pytest.approx(1.0)


def test_contrast_ratio_is_symmetric():
    assert contrast_ratio("#1963a4", "#fcfcfb") == contrast_ratio("#fcfcfb", "#1963a4")


# --- the palettes ------------------------------------------------------------

@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=["light", "dark"])
def test_theme_meets_its_floors(theme):
    """No mark invisible against its ground, no pair confusable on one axis.

    This is the test defect D-02 did not have. The failure message lists
    every violation with its measured number, so a future palette edit says
    what it broke instead of just going red.
    """
    problems = check_theme(theme)
    assert not problems, "palette violations:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=["light", "dark"])
def test_critical_is_never_a_series_colour(theme):
    """The reserved status colour must not double as a category.

    A palette search once returned a CRITICAL identical to a series slot
    because nothing forbade it. Identity by hex is the cheap guard; the
    CIEDE2000 floor in check_theme is the real one.
    """
    assert theme.critical not in theme.series


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=["light", "dark"])
def test_three_categorical_slots(theme):
    """Three, not four — no figure identifies more than three series by colour."""
    assert len(theme.series) == 3


def test_the_floors_are_the_documented_standards():
    """Pin the floors themselves.

    A palette can also be "fixed" by quietly lowering the bar it is measured
    against, which would leave every other test in this file green. These are
    WCAG 2.2 SC 1.4.11 for contrast, and a CIEDE2000 separation comfortably
    above the ~2.3 just-noticeable difference for large fields.
    """
    assert CONTRAST_FLOOR == 3.0
    assert DELTA_FLOOR == 18.0


def test_the_two_themes_are_actually_different():
    assert LIGHT.surface != DARK.surface
    assert LIGHT.series != DARK.series


def test_dark_surface_is_darker_than_light_surface():
    """Guards against the two theme definitions being swapped in an edit."""
    white = "#ffffff"
    assert contrast_ratio(DARK.surface, white) > contrast_ratio(LIGHT.surface, white)


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=["light", "dark"])
def test_body_text_is_readable(theme):
    """Ink against surface must clear the 4.5:1 body-text floor, not just 3:1."""
    assert contrast_ratio(theme.ink, theme.surface) >= 4.5


def test_separation_takes_the_worst_vision_type():
    """separation() is a minimum over vision types, never an average.

    An average would let a pair that vanishes under deuteranopia pass on the
    strength of looking fine to everyone else, which is precisely the failure
    D-02 shipped with.
    """
    a, b = LIGHT.series[0], LIGHT.series[1]
    per_vision = [ciede2000(simulate(a, v), simulate(b, v)) for v in VISIONS]
    assert separation(a, b) == pytest.approx(min(per_vision))
    assert min(per_vision) < sum(per_vision) / len(per_vision)


# --- theme switching ---------------------------------------------------------

def test_use_theme_restores_afterwards():
    before = visualization.THEME
    with use_theme(DARK):
        assert visualization.THEME is DARK
    assert visualization.THEME is before


def test_use_theme_restores_on_exception():
    """A figure that raises must not leave the module in the wrong theme."""
    before = visualization.THEME
    with pytest.raises(ValueError):
        with use_theme(DARK):
            raise ValueError("boom")
    assert visualization.THEME is before


def test_use_theme_nests():
    with use_theme(DARK):
        with use_theme(LIGHT):
            assert visualization.THEME is LIGHT
        assert visualization.THEME is DARK


def test_themes_registry_matches_names():
    assert THEMES["light"] is LIGHT and THEMES["dark"] is DARK
    for name, theme in THEMES.items():
        assert theme.name == name


def test_theme_is_immutable():
    """Frozen, because a figure that mutates the theme corrupts later figures."""
    with pytest.raises(Exception):
        LIGHT.surface = "#ff0000"


# --- rendering ---------------------------------------------------------------

def test_make_all_writes_both_themes(nominal_history, tmp_path):
    """Four figures in two themes; light keeps the bare name for old links."""
    paths = visualization.make_all(nominal_history, str(tmp_path))
    assert len(paths) == 8
    for path in paths:
        assert os.path.getsize(path) > 0, f"{path} is empty"
    names = {os.path.basename(p) for p in paths}
    assert "two_signals.png" in names
    assert "two_signals_dark.png" in names


def test_make_all_can_render_one_theme(nominal_history, tmp_path):
    paths = visualization.make_all(nominal_history, str(tmp_path), themes=(LIGHT,))
    assert len(paths) == 4
    assert all(not p.endswith("_dark.png") for p in paths)


def test_rendering_leaves_the_theme_unchanged(nominal_history, tmp_path):
    before = visualization.THEME
    visualization.make_all(nominal_history, str(tmp_path))
    assert visualization.THEME is before
