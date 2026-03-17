import shutil
import time

def delete_with_retry(path, max_attempts=5, delay=0.1):
    for attempt in range(max_attempts):
        try:
            shutil.rmtree(path)
            return True
        except Exception:
            if attempt == max_attempts - 1:
                raise
            time.sleep(delay * (2 ** attempt))
    return False