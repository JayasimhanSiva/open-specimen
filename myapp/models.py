import logging
import queue
import threading
from urllib.parse import urlencode

from django.db import models
from django.urls import reverse


class Typeface(models.Model):
    class Classification(models.TextChoices):
        SANS = "sans", "Sans"
        SERIF = "serif", "Serif"
        DISPLAY = "display", "Display"
        MONO = "mono", "Mono"

    name = models.CharField(max_length=60, help_text="Exact Google Fonts family name")
    slug = models.SlugField(unique=True)
    designer = models.CharField(max_length=120)
    year = models.PositiveSmallIntegerField()
    classification = models.CharField(max_length=10, choices=Classification.choices)
    axes = models.JSONField(default=list, blank=True,
                            help_text='e.g. [{"tag": "wght", "name": "Weight", "min": 100, "max": 900, "default": 400}]')
    gf_query = models.CharField("Google Fonts query", max_length=160,
                                help_text="e.g. Anybody:wdth,wght@50..150,100..900")
    sample = models.CharField(max_length=160, help_text="Specimen line")
    description = models.TextField()
    uses = models.TextField(blank=True, help_text="Comma-separated jobs it suits; the font matcher reads these")
    mood = models.CharField(max_length=160, blank=True, help_text="Comma-separated words for how it feels")
    gf_path = models.CharField("google/fonts path", max_length=80, blank=True,
                               help_text="Folder in github.com/google/fonts, e.g. ofl/anybody")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("myapp:typeface", args=[self.slug])

    @property
    def google_url(self):
        return "https://fonts.google.com/specimen/" + self.name.replace(" ", "+")

    @property
    def axes_ui(self):
        """Axes with a slider step: fine steps for 0–1 switches like MONO, whole numbers otherwise."""
        return [{**a, "step": 0.01 if a["max"] - a["min"] <= 1 else 1} for a in self.axes]

    @property
    def axis_tags(self):
        return " ".join(a["tag"] for a in self.axes) or "Static"

    @property
    def hover_variation(self):
        """Variation settings at the far end of every axis, used for hover states."""
        return ", ".join(f'"{a["tag"]}" {a["max"]}' for a in self.axes if a["tag"] in ("wght", "wdth"))


class Match(models.Model):
    """One font-matcher request and what it returned."""
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="matches")
    query = models.CharField(max_length=200)
    typeface = models.ForeignKey(Typeface, on_delete=models.CASCADE, related_name="matches")
    settings = models.JSONField(default=dict)
    size = models.PositiveSmallIntegerField(default=72)
    reason = models.CharField(max_length=300)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name_plural = "matches"

    def __str__(self):
        return f"{self.query} → {self.typeface}"

    @property
    def tester_url(self):
        """The typeface page with the tester preloaded with this match."""
        params = {**{k: v for k, v in self.settings.items()}, "size": self.size, "text": self.query}
        return f"{self.typeface.get_absolute_url()}?{urlencode(params)}"

    @property
    def variation_css(self):
        return ", ".join(f'"{k}" {v}' for k, v in self.settings.items()) or "normal"

    @property
    def settings_label(self):
        return " · ".join(f"{k} {v}" for k, v in self.settings.items()) or "Static"


class Faq(models.Model):
    """A frequently asked question. The assistant answers from these."""
    question = models.CharField(max_length=200)
    answer = models.TextField()
    category = models.CharField(max_length=40)
    phrasings = models.TextField(blank=True, help_text="Other ways people ask this, one per line. The assistant matches these too.")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question

    def get_absolute_url(self):
        return f"{reverse('myapp:faq')}#faq-{self.pk}"

    @property
    def phrasing_list(self):
        return [p.strip() for p in self.phrasings.splitlines() if p.strip()]


class ErrorCode(models.Model):
    """An error the site can return, explained in plain words."""
    code = models.CharField(max_length=12, unique=True, help_text="HTTP status like 404, or a site code like OS-422")
    title = models.CharField(max_length=80)
    meaning = models.TextField(help_text="What happened")
    fix = models.TextField(help_text="What the visitor can do about it")
    when = models.CharField(max_length=200, help_text="Where this site returns it")
    site_specific = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "code"]

    def __str__(self):
        return f"{self.code} {self.title}"

    def get_absolute_url(self):
        return f"{reverse('myapp:errors')}#code-{self.code}"


class SupportTicket(models.Model):
    """Opened by the assistant when it can't answer a question."""
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ANSWERED = "answered", "Answered"
        CLOSED = "closed", "Closed"

    user = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets")
    name = models.CharField(max_length=80, blank=True)
    email = models.EmailField()
    question = models.TextField()
    session_id = models.CharField(max_length=64, blank=True, help_text="Links to the chat log in MongoDB")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.reference} — {self.question[:60]}"

    @property
    def reference(self):
        return f"T-{self.pk:05d}" if self.pk else "T-new"


# ------------------------------------------------------------------ MongoDB
#
# Chat logs and feedback live in MongoDB (one document per message / per rating).
# The connection is opened lazily with a short timeout so a slow or missing
# database never blocks a page; failures are reported on /health/.

class DocumentStore:
    def __init__(self):
        self._client = None
        self._error = ""
        self.memory = {"chat_logs": [], "feedback": []}  # used when MongoDB isn't configured
        self._queue = queue.Queue(maxsize=2000)
        self._writer = None
        self._writer_lock = threading.Lock()

    @property
    def configured(self):
        from django.conf import settings
        return bool(settings.MONGODB_URI)

    def _db(self):
        from django.conf import settings
        if not self.configured:
            return None
        if self._client is None:
            if settings.MONGODB_URI.startswith("mongomock://"):  # tests
                import mongomock
                self._client = mongomock.MongoClient()
            else:
                from pymongo import MongoClient
                self._client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
                                           connectTimeoutMS=settings.MONGODB_TIMEOUT_MS, appname="open-specimen")
        return self._client[settings.MONGODB_DB]

    def insert(self, collection, doc):
        """Store a document and return its id. Never raises, and in production never makes the visitor
        wait: the id is made here and the write happens on a background thread."""
        from bson import ObjectId
        from django.conf import settings
        doc = {**doc, "_id": ObjectId()}
        db = self._db()
        if db is None:
            self.memory[collection].append(doc)
            del self.memory[collection][:-500]
        elif settings.MONGODB_ASYNC:
            self._start_writer()
            try:
                self._queue.put_nowait((collection, doc))
            except queue.Full:
                logging.getLogger("myapp").warning("MongoDB write queue full; dropped a %s document", collection)
        else:
            self._write(db, collection, doc)
        return str(doc["_id"])

    def _write(self, db, collection, doc):
        try:
            db[collection].insert_one(doc)
            self._error = ""
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"[:200]
            logging.getLogger("myapp").warning("MongoDB insert into %s failed: %s", collection, self._error)

    def _start_writer(self):
        if self._writer and self._writer.is_alive():
            return
        with self._writer_lock:
            if self._writer and self._writer.is_alive():
                return

            def run():
                while True:
                    collection, doc = self._queue.get()
                    db = self._db()
                    if db is not None:
                        self._write(db, collection, doc)

            self._writer = threading.Thread(target=run, name="mongo-writer", daemon=True)
            self._writer.start()

    def find(self, collection, query=None, limit=20):
        """Newest documents first; an empty list (not an error page) when MongoDB is unreachable."""
        db = self._db()
        if db is None:
            docs = [d for d in self.memory[collection] if all(d.get(k) == v for k, v in (query or {}).items())]
            return list(reversed(docs))[:limit]
        try:
            return list(db[collection].find(query or {}).sort("created", -1).limit(limit))
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"[:200]
            logging.getLogger("myapp").warning("MongoDB read from %s failed: %s", collection, self._error)
            return []

    def _ping_now(self):
        import time
        db = self._db()
        if db is None:
            return "not configured", "MONGODB_URI is not set; chat logs are kept in memory only."
        started = time.perf_counter()
        try:
            db.command("ping")
            counts = f"{db.chat_logs.estimated_document_count()} chat messages, {db.feedback.estimated_document_count()} ratings"
            return "ok", f"{counts} · {round((time.perf_counter() - started) * 1000)} ms"
        except Exception as exc:
            return "down", f"{type(exc).__name__}: {str(exc)[:160]}"

    def ping(self):
        """(status, detail) for the health page. In production the check runs in the background and
        the page shows the latest result, so a slow database never makes the health check slow."""
        import time
        from django.conf import settings
        if not settings.MONGODB_ASYNC or not self.configured:
            return self._ping_now()
        last = getattr(self, "_last_ping", None)
        if last is None or time.monotonic() - last[0] > 30:
            if not getattr(self, "_pinging", False):
                self._pinging = True

                def run():
                    try:
                        self._last_ping = (time.monotonic(), self._ping_now())
                    finally:
                        self._pinging = False

                threading.Thread(target=run, name="mongo-ping", daemon=True).start()
        if last is None:
            return "checking", "Connecting to MongoDB; reload in a few seconds."
        return last[1]


documents = DocumentStore()


class Submission(models.Model):
    typeface = models.CharField("typeface name", max_length=80)
    designer = models.CharField(max_length=120)
    url = models.URLField("link to the font files")
    email = models.EmailField("your email")
    ofl = models.BooleanField("it's licensed under the SIL Open Font License")
    note = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.typeface} — {self.designer}"
