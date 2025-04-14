import threading
from robot.output.logger import LOGGER
from robot.output.loggerapi import LoggerApi
from robot.output.librarylogger import LOGGING_THREADS
from functools import partial


class DumpOutputFile(LoggerApi):

    def __init__(self, is_logged_function):
        """
        A class responsible for handling the logging of messages in the case where
        output_file is set to None, which results in an exception being raised in the
        _log_message function from the robot.output.logger file.
        The class contains a single method to prevent the exception by handling the case where output_file is None.
        """
        self.is_logged_function = is_logged_function

    def is_logged(self, message):
        return self.is_logged_function(message)


class LoggingThreads:

    def __init__(self):
        """
        A class designed to enable the collection of logs from threads in Python.
        By default, Robot Framework does not support logging from threads, but this
        class provides a mechanism to capture and manage log messages originating
        from multiple threads.
        """
        self.hijacked_console_logger = None
        self.hijacked_syslog = None
        self.hijacked_output_file = None
        self.main_robot_threads = None
        self.loggers_manager = None
        self.threads = []

    def hijack_loggers(self):
        """
        A function that intercepts the current loggers from the LOGGER class to
        allow them to be restored later.
        """
        self.hijacked_console_logger = LOGGER._console_logger
        self.hijacked_syslog = LOGGER._syslog
        self.hijacked_output_file = LOGGER._output_file

    @staticmethod
    def unregister_loggers():
        """
        Unregisters the current loggers from the LOGGER class to prevent unnecessary
        log entries in log.html. This is necessary because functions decorated by
        start/end_body_item are called by threads, which can result in redundant or unwanted
        log entries being created.
        """
        is_logged_function = LOGGER._output_file.is_logged
        LOGGER._output_file = DumpOutputFile(is_logged_function)
        LOGGER.unregister_logger()
        LOGGER.unregister_console_logger()

    def register_loggers(self):
        LOGGER._console_logger = self.hijacked_console_logger
        LOGGER._syslog = self.hijacked_syslog
        LOGGER._output_file = self.hijacked_output_file

    def create_thread(self, thread_name, function, *args, **kwargs):
        """
        Adds the thread name to the LOGGING_THREADS in robot.output.librarylogger.
        Without this step, log messages would be ignored. By appending the thread name,
        the messages are properly passed through and managed accordingly.
        """
        thread = threading.Thread(name=thread_name, target=function, args=args, kwargs=kwargs)
        LOGGING_THREADS.append(thread_name)
        self.loggers_manager.thread_messages[thread_name] = []
        thread.start()
        self.threads.append(thread)

    def __enter__(self):
        self.hijack_loggers()
        self.unregister_loggers()
        self.main_robot_threads = list(LOGGING_THREADS)
        self.loggers_manager = LoggersManager(main_robot_threads=self.main_robot_threads,
                                              hijacked_console_logger=self.hijacked_console_logger,
                                              hijacked_syslog=self.hijacked_syslog,
                                              hijacked_outputfile=self.hijacked_output_file)
        LOGGER.register_logger(self.loggers_manager)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for thread in self.threads:
            thread.join()
        LOGGER.unregister_logger(self.loggers_manager)
        for thread_name in list(LOGGING_THREADS):
            LOGGING_THREADS.remove(thread_name) if thread_name not in self.main_robot_threads else None
        self.register_loggers()
        self.loggers_manager.log_all_threads_messages()
        self.loggers_manager.thread_messages = {}


class LoggersManager(LoggerApi):
    thread_messages = {}

    def __init__(self, main_robot_threads, hijacked_console_logger, hijacked_syslog, hijacked_outputfile):
        self.main_robot_threads = main_robot_threads
        hijacked_loggers = [hijacked_outputfile, hijacked_syslog, hijacked_console_logger]
        self.hijacked_loggers = [logger for logger in hijacked_loggers if logger]

    def check_if_main_robot_thread(self):
        return threading.current_thread().name in self.main_robot_threads

    @staticmethod
    def add_logger_func_to_thread_message(logger_func):
        try:
            LoggersManager.thread_messages[threading.current_thread().name].append(logger_func)
        except KeyError:
            LoggersManager.thread_messages[threading.current_thread().name] = [logger_func]

    @staticmethod
    def log_all_threads_messages():
        for thread_messages in LoggersManager.thread_messages.values():
            for logger_func in thread_messages:
                logger_func()

    def manage_loggers(self, logger_function_name, *logger_args, **logger_kwargs):
        """
        Manages loggers for messages based on their originating thread. If the message
        comes from one of the main Robot Framework threads, it is logged immediately.
        If the message comes from a non-main thread, it is stored for later logging.
        """
        if self.check_if_main_robot_thread():
            for logger in self.hijacked_loggers:
                getattr(logger, logger_function_name)(*logger_args, **logger_kwargs)
        else:
            self.add_logger_func_to_thread_message(
                partial(getattr(LOGGER, logger_function_name), *logger_args, **logger_kwargs))

    def start_library_keyword(self, data, implementation, result):
        self.manage_loggers("start_library_keyword", data, implementation, result)

    def end_library_keyword(self, data, implementation, result):
        self.manage_loggers("end_library_keyword", data, implementation, result)

    def log_message(self, message):
        self.manage_loggers("log_message", message)

    def message(self, message):
        self.manage_loggers("message", message)

    def start_keyword(self, data, result):
        self.manage_loggers("start_keyword", data, result)

    def end_keyword(self, data, result):
        self.manage_loggers("end_keyword", data, result)

    def start_user_keyword(self, data, implementation, result):
        self.manage_loggers("start_user_keyword", data, result)

    def end_user_keyword(self, data, implementation, result):
        self.manage_loggers("end_user_keyword", data, result)

    def start_invalid_keyword(self, data, implementation, result):
        self.manage_loggers("start_invalid_keyword", data, result)

    def end_invalid_keyword(self, data, implementation, result):
        self.manage_loggers("end_invalid_keyword", data, result)

    def start_for(self, data, result):
        self.manage_loggers("start_for", data, result)

    def end_for(self, data, result):
        self.manage_loggers("end_for", data, result)

    def start_for_iteration(self, data, result):
        self.manage_loggers("start_for_iteration", data, result)

    def end_for_iteration(self, data, result):
        self.manage_loggers("end_for_iteration", data, result)

    def start_while(self, data, result):
        self.manage_loggers("start_while", data, result)

    def end_while(self, data, result):
        self.manage_loggers("end_while", data, result)

    def start_while_iteration(self, data, result):
        self.manage_loggers("start_while_iteration", data, result)

    def end_while_iteration(self, data, result):
        self.manage_loggers("end_while_iteration", data, result)

    def start_group(self, data, result):
        self.manage_loggers("start_group", data, result)

    def end_group(self, data, result):
        self.manage_loggers("end_group", data, result)

    def start_if(self, data, result):
        self.manage_loggers("start_if", data, result)

    def end_if(self, data, result):
        self.manage_loggers("end_if", data, result)

    def start_if_branch(self, data, result):
        self.manage_loggers("start_if_branch", data, result)

    def end_if_branch(self, data, result):
        self.manage_loggers("end_if_branch", data, result)

    def start_try(self, data, result):
        self.manage_loggers("start_try", data, result)

    def end_try(self, data, result):
        self.manage_loggers("end_try", data, result)

    def start_try_branch(self, data, result):
        self.manage_loggers("start_try_branch", data, result)

    def end_try_branch(self, data, result):
        self.manage_loggers("end_try_branch", data, result)

    def start_var(self, data, result):
        self.manage_loggers("start_var", data, result)

    def end_var(self, data, result):
        self.manage_loggers("end_var", data, result)

    def start_break(self, data, result):
        self.manage_loggers("start_break", data, result)

    def end_break(self, data, result):
        self.manage_loggers("end_break", data, result)

    def start_continue(self, data, result):
        self.manage_loggers("start_continue", data, result)

    def end_continue(self, data, result):
        self.manage_loggers("end_continue", data, result)

    def start_return(self, data, result):
        self.manage_loggers("start_return", data, result)

    def end_return(self, data, result):
        self.manage_loggers("end_return", data, result)

    def start_error(self, data, result):
        self.manage_loggers("start_error", data, result)

    def end_error(self, data, result):
        self.manage_loggers("end_error", data, result)
