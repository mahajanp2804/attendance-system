"""
Background worker for model inference.
YOLO, MTCNN and FaceNet calls are slow and blocking, so they run here instead of
on the event loop — otherwise every other API request waits for each frame.
One thread only: the YOLO predictor isn't thread-safe, and running models one at
a time avoids CPU contention when several scanners are open.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ml-worker")


async def run_ml(fn, *args):
    """Run a blocking model call on the inference thread and await its result."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, fn, *args)
