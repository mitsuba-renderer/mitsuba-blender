from contextlib import contextmanager


class ConversionError(Exception):
    '''Raised when a converter cannot represent the given content.'''


@contextmanager
def saved_file_resolver():
    '''Restore the state of Mitsuba's session-global file resolver on exit.'''
    import mitsuba as mi
    fr = mi.file_resolver()
    paths = list(fr)
    try:
        yield fr
    finally:
        fr.clear()
        for path in paths:
            fr.append(path)
