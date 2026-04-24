import threading
import time
from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn

# To allow `librarylogger` to pass messages down to LOGGER, 
# we spoof the current thread name to 'MainThread' inside the thread 
# or append it to LOGGING_THREADS.
import robot.output.librarylogger
from robot.output.librarylogger import LOGGING_THREADS

def thread_task(name):
    # Spoof thread to be recognized by RF logger
    curr = threading.current_thread()
    # Add to LOGGING_THREADS so librarylogger.write calls LOGGER
    if curr.name not in LOGGING_THREADS:
        LOGGING_THREADS.append(curr.name)
        
    logger.info(f"Thread {name} starting")
    time.sleep(0.1)
    
    # Try calling a BuiltIn keyword inside thread (this is a common user requested scenario)
    # BuiltIn requires execution context properly set up
    logger.info(f"Thread {name} running keyword...")
    try:
        BuiltIn().run_keyword("Log", f"Message from {name} run_keyword")
    except Exception as e:
        logger.error(f"Thread {name} failed: {e}")
        
    logger.info(f"Thread {name} finishing")

def start_threads():
    threads = []
    for i in range(2):
        t = threading.Thread(target=thread_task, args=(f"T{i}",), name=f"RobotFrameworkTimeoutThread_{i}")
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
