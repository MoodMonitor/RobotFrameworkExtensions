import threading
import sys
from robot.output import LOGGER
import robot.output.librarylogger as librarylogger
from robot.running.model import Keyword
from robot.model import Message

class AllThreadsList:
    def __contains__(self, item):
        return True

class ThreadInterceptorLibrary:
    def __init__(self):
        self.main_thread = None
        self.active = False
        self.buffers = {}
        self.lock = threading.Lock()
        self._original_methods = {}
        
    def start_thread_interception(self):
        if self.active: return
        self.main_thread = threading.current_thread()
        self.buffers.clear()
        self.active = True
        
        self.orig_logging_threads = librarylogger.LOGGING_THREADS
        librarylogger.LOGGING_THREADS = AllThreadsList()
        
        methods_to_patch = [
            'start_keyword', 'end_keyword', 'start_for', 'end_for', 
            'start_for_iteration', 'end_for_iteration',
            'start_if', 'end_if', 'start_if_branch', 'end_if_branch', 
            'start_try', 'end_try', 'start_try_branch', 'end_try_branch',
            'start_while', 'end_while', 'start_while_iteration', 'end_while_iteration',
            'start_break', 'end_break',
            'start_continue', 'end_continue', 'start_return', 'end_return',
            'start_error', 'end_error', 'start_var', 'end_var',
            'start_library_keyword', 'end_library_keyword',
            'start_user_keyword', 'end_user_keyword',
            'start_invalid_keyword', 'end_invalid_keyword',
            'start_group', 'end_group',
            'log_message', 'message', 'trace', 'debug', 'info', 'warn', 'error', 'fail',
            'start_body_item', 'end_body_item'
        ]
        
        # In RF, decorators like @start_body_item intercept method calls.
        # But we patch the exposed methods on LOGGER instance.
        for name in methods_to_patch:
            if hasattr(LOGGER, name):
                orig = getattr(LOGGER, name)
                # If we've already patched, don't patch again (just in case)
                if not getattr(orig, '__is_thread_interceptor__', False):
                    self._original_methods[name] = orig
                    wrapper = self._make_wrapper(name, orig)
                    setattr(LOGGER, name, wrapper)

    def _make_wrapper(self, name, orig):
        def wrapper(*args, **kwargs):
            current = threading.current_thread()
            if self.active and current != self.main_thread:
                with self.lock:
                    if current not in self.buffers:
                        self.buffers[current] = []
                    
                    import sys
                    print(f"INTERCEPTED {name} IN {current.name}", file=sys.stderr)
                    # Hack: copy message objects if it's logging methods because RF might mutate it?
                    # Generally RF messages are instantiated with timestamp so it's captured now.
                    self.buffers[current].append((name, args, kwargs))
            else:
                return orig(*args, **kwargs)
        wrapper.__is_thread_interceptor__ = True
        return wrapper

    def stop_and_replay_thread_logs(self):
        if not self.active: return
        self.active = False
        
        librarylogger.LOGGING_THREADS = self.orig_logging_threads
        
        # Restore original methods
        for name, orig in self._original_methods.items():
            setattr(LOGGER, name, orig)
        
        
        # Replay
        from robot.running.model import Keyword as RKeyword
        from robot.result.model import Keyword as SKeyword
        
        for thread, calls in self.buffers.items():
            # Create a virtual keyword for this thread grouping
            kw_data = RKeyword(name=f"Thread: {thread.name}", type="KEYWORD")
            kw_result = SKeyword(name=f"Thread: {thread.name}", type="KEYWORD")
            
            LOGGER.start_keyword(kw_data, kw_result)
            for name, args, kwargs in calls:
                orig_method = self._original_methods.get(name) or getattr(LOGGER, name)
                orig_method(*args, **kwargs)
            LOGGER.end_keyword(kw_data, kw_result)
            
        self.buffers.clear()
        self._original_methods.clear()
