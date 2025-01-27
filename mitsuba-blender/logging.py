import time
from contextlib import contextmanager

def info(msg):
    '''
    Log a INFO level message.
    '''
    import mitsuba as mi
    mi.Log(mi.LogLevel.Info, msg)

def debug(msg):
    '''
    Log a DEBUG level message.
    '''
    import mitsuba as mi
    mi.Log(mi.LogLevel.Debug, msg)

def warn(msg):
    '''
    Log a WARN level message.
    '''
    import mitsuba as mi
    mi.Log(mi.LogLevel.Warn, msg)

def error(msg):
    '''
    Log a ERROR level message.
    '''
    import mitsuba as mi
    mi.Log(mi.LogLevel.Error, msg)

def register():
    if False: # TODO somehow this is causing a crash in Blender
        import mitsuba as mi

        logger = mi.Thread.thread().logger()

        # Remove all current Mitsuba appenders
        while logger.appender_count() > 0:
            logger.remove_appender(logger.appender(0))

        # Add an appender that uses our logging infrastructure
        class MyAppender(mi.Appender):
            def append(self, level, text):
                {
                    mi.LogLevel.Info: info,
                    mi.LogLevel.Debug: debug,
                    mi.LogLevel.Warn: warn,
                    mi.LogLevel.Error: error,
                }[level](text)

        logger.add_appender(MyAppender())

def unregister():
    pass


@contextmanager
def time_operation(label):
    '''
    Context manager to time some Mitsuba / Dr.Jit operations.

    Make sure so use `dr.schedule(var)` to trigger the computation of a specific
    variable in the next kernel launch, and therefore include it in the timing.
    '''
    import drjit as dr
    print(f'{label} ...')
    start = time.time()
    yield
    dr.eval()
    dr.sync_thread()
    print(f'{label} → done in {(time.time() - start)} sec')
