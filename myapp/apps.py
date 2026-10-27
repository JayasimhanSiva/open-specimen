import os
import sys
import threading
import time

from django.apps import AppConfig


class MyappConfig(AppConfig):
    name = 'myapp'

    def ready(self):
        # Load the embedding model in the background so the first visitor's answer is as fast as every
        # other one: under `runserver` (RUN_MAIN marks the serving process, not the file watcher) and
        # under gunicorn. Gunicorn may import the app in its master process and then fork the worker;
        # a thread started before the fork doesn't exist in the worker, so the model is loaded in the
        # worker only, after the fork.
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") == "true":
            self._start_warm()
        elif os.path.basename(sys.argv[0]).startswith("gunicorn"):
            state = {"forked": False, "started": False}

            def in_child():
                from .views import matcher
                matcher.reset_after_fork()
                state["started"] = True
                self._start_warm()

            def in_parent():
                state["forked"] = True  # this is the master: it serves no requests, so don't load here

            os.register_at_fork(after_in_child=in_child, after_in_parent=in_parent)

            def start_if_worker():
                time.sleep(3)  # app imported in the worker itself (no fork follows): load here
                if not state["forked"] and not state["started"]:
                    self._start_warm()

            threading.Thread(target=start_if_worker, name="warm-check", daemon=True).start()

    @staticmethod
    def _start_warm():
        from .views import warm_matcher
        threading.Thread(target=warm_matcher, name="warm-model", daemon=True).start()
