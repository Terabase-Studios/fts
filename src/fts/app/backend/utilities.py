import inspect

async def await_me_maybe(callback):
    result = callback()
    if inspect.isawaitable(result):
        return await result
    return result
