import os
import sys
import threading

from django.apps import AppConfig


class MyappConfig(AppConfig):
    name = 'myapp'

    def ready(self):
        # Load the embedding model in the background so the first visitor's answer is
        # as fast as every other one: under `runserver` (RUN_MAIN marks the serving
        # process, not the file watcher) and under gunicorn in production.
        serving = ("runserver" in sys.argv and os.environ.get("RUN_MAIN") == "true") or \
            os.path.basename(sys.argv[0]).startswith("gunicorn")
        if serving:
            from .views import warm_matcher
            threading.Thread(target=warm_matcher, name="warm-model", daemon=True).start()
