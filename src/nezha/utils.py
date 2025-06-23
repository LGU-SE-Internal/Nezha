import datetime
import inspect
import sys
from functools import wraps


def timeit(*, log_level: str = "DEBUG", log_args: bool | set[str] = True):
    def decorator(func):
        sig = inspect.signature(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = f"{func.__qualname__:<20}"

            sys.stdout.flush()

            start = datetime.datetime.now()
            result = func(*args, **kwargs)
            end = datetime.datetime.now()

            duration = end - start
            duration_message = f"duration={duration.total_seconds():.6f}s"
            print(f"exit  {func_name} {duration_message}")
            sys.stdout.flush()

            return result

        return wrapper

    return decorator
