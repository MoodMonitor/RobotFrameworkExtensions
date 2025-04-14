import threading
from logging_threads import LoggingThreads
from robot.libraries.BuiltIn import BuiltIn


def test_function():
    BuiltIn().log("Run test function")

def example_thread():
    BuiltIn().log("{} Thread run".format(threading.current_thread().name))
    BuiltIn().run_keyword("test_function")

def example_threads_basic():
    BuiltIn().log("Start example_threads_basic")
    thread1 = threading.Thread(target=example_thread, name="BasicThread1")
    thread2 = threading.Thread(target=example_thread, name="BasicThread2")
    thread3 = threading.Thread(target=example_thread, name="BasicThread3")
    thread1.start(), thread2.start(), thread3.start()
    thread1.join(), thread2.join(), thread3.join()
    BuiltIn().log("End example_threads_basic")

def example_threads_extended():
    BuiltIn().log("Start example_threads_extended")
    with LoggingThreads() as threads:
        threads.create_thread(thread_name="ExtendedThread1", function=example_thread)
        threads.create_thread(thread_name="ExtendedThread2", function=example_thread)
        threads.create_thread(thread_name="ExtendedThread3", function=example_thread)
    BuiltIn().log("End example_threads_extended")