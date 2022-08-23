
def test_mitsuba_has_correct_variant():
    import mitsuba
    assert mitsuba.variant() == 'scalar_rgb'
