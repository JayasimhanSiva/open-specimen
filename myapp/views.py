import hashlib
import json
import logging
import re
import threading
import time
import uuid
from collections import deque
from datetime import timedelta
from urllib.parse import quote, urlsplit

import requests
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required, login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponseServerError, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ErrorCode, Faq, Match, Submission, SupportTicket, Typeface, documents

log = logging.getLogger(__name__)

GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789&?"  # 64 = an 8 × 8 grid
WATERFALL = [96, 64, 40, 24, 16]
EXAMPLES = [
    "Menu for a relaxed wine bar",
    "Loud poster for a summer music festival",
    "Theme for a code editor",
    "Wedding invitation, elegant and light",
    "Long essays on a calm reading blog",
]


def fonts_url(faces):
    families = "&".join("family=" + quote(f.gf_query, safe=":,@.;") for f in faces)
    return f"https://fonts.googleapis.com/css2?{families}&display=swap"


class AccessibleErrorsMixin:
    """Point screen readers at each field's error message."""

    def mark_errors(self):
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs.update({
                    "aria-invalid": "true",
                    "aria-describedby": f"id_{name}_error",
                })


# ------------------------------------------------------------------ font matcher
#
# A small sentence-embedding model (bge-small, ~70 MB, ONNX on the CPU) turns the
# visitor's description and each typeface's "uses" and "mood" phrases into vectors.
# The closest typeface wins; the same vectors set each variable axis by comparing
# the description with two opposite anchor phrases (e.g. "bold" vs "light").
# Free, offline after the first download, and a few milliseconds per request.

# Each axis: (phrase for the axis maximum, phrase for the axis minimum,
#             words that jump to the maximum, words that jump to the minimum)
AXIS_ANCHORS = {
    "wght": ("bold, heavy, loud, strong, powerful, chunky, impactful",
             "light, thin, delicate, quiet, subtle, airy, fine",
             {"bold", "heavy", "black", "thick", "chunky", "loud", "heavier", "bolder"},
             {"light", "thin", "hairline", "delicate", "fine", "lighter", "thinner"}),
    "wdth": ("wide, expanded, broad, spacious, stretched, extended",
             "narrow, condensed, compact, tall, tight, slim",
             {"wide", "wider", "expanded", "extended", "broad", "stretched"},
             {"narrow", "narrower", "condensed", "compressed", "tall", "skinny", "slim"}),
    "opsz": ("huge headline, poster, billboard, title, display type, signage",
             "small text, body copy, captions, footnotes, menu items, labels",
             {"headline", "poster", "billboard", "title", "display"},
             {"caption", "captions", "footnote", "footnotes", "small", "body"}),
    "CASL": ("casual, handwritten, playful, informal, brush lettering, relaxed, fun",
             "formal, technical, precise, strict, serious, corporate",
             {"casual", "handwritten", "brush", "playful", "informal", "comic"},
             {"formal", "strict", "corporate"}),
    "MONO": ("code, programming, terminal, monospace, data table, developer tool",
             "prose, reading, natural writing, story, friendly text",
             {"code", "coding", "programming", "terminal", "monospace", "developer"},
             {"prose", "story", "proportional"}),
    # Slant is set by explicit words only; the embedding gap for it is mostly noise.
    "slnt": (None, None, {"upright", "straight"}, {"italic", "slanted", "slant", "leaning", "oblique"}),
}
# Display size in the result preview, from "small text" (low) to "huge poster" (high)
SIZE_ANCHORS = ("huge headline, poster, billboard, big title", "small text, body copy, captions, paragraphs")
# Briefs that say nothing about any axis. Their average gap is each axis's bias,
# subtracted before scoring so that a neutral brief keeps the typeface's defaults.
NEUTRAL_BRIEFS = ["a typeface", "hello", "some text", "a design project", "words on a page", "something nice"]
DEAD_ZONE = 0.035    # gaps smaller than this (after bias) are treated as "no preference"
GAIN = 7.0           # remaining gap → axis travel; ~0.18 reaches the end of an axis
LOW_CONFIDENCE = 0.67  # best "uses" similarity below this means the brief is too vague to place

ADJUSTMENT_WORDS = {
    "wght": ("heavier", "lighter"),
    "wdth": ("wider", "narrower"),
    "opsz": ("tuned for large sizes", "tuned for small sizes"),
    "CASL": ("in its casual style", "in its strict style"),
    "MONO": ("monospaced", "proportional"),
    "slnt": ("upright", "slanted"),
}


def _words(text):
    return set(re.findall(r"[a-z]+", text.lower()))


def _phrases(text):
    return [p.strip() for p in text.split(",") if p.strip()]


class FontMatcher:
    def __init__(self):
        self._model = None
        self._failed = False
        self._lock = threading.Lock()
        self._vectors = {}
        self._bias = {}

    @property
    def engine(self):
        return "keywords" if self._failed else "embedding"

    def _load(self):
        if self._model is not None or self._failed:
            return
        with self._lock:
            if self._model is not None or self._failed:
                return
            try:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(settings.MATCHER_MODEL, cache_dir=settings.MATCHER_CACHE_DIR,
                                            providers=["CPUExecutionProvider"])
            except Exception:  # missing package, no network for the first download, corrupt cache…
                log.exception("Font matcher model unavailable; falling back to keyword matching")
                self._failed = True

    def _embed(self, texts):
        """Unit vectors for texts, cached; phrases from the index are embedded once."""
        import numpy as np
        missing = [t for t in dict.fromkeys(texts) if t not in self._vectors]
        if missing:
            for t, v in zip(missing, self._model.embed(missing)):
                v = np.asarray(v, dtype="float32")
                self._vectors[t] = v / (np.linalg.norm(v) or 1.0)
        return [self._vectors[t] for t in texts]

    def warm(self, faces=()):
        self._load()
        if self._model is None:
            return
        texts = [a for anchors in AXIS_ANCHORS.values() for a in anchors[:2] if a] + list(SIZE_ANCHORS)
        for f in faces:
            texts += [self._profile(f)] + _phrases(f.uses) + _phrases(f.mood)
        self._embed(texts)
        self._calibrate()

    def _calibrate(self):
        if self._bias:
            return
        neutral = self._embed(NEUTRAL_BRIEFS)
        pairs = {tag: anchors[:2] for tag, anchors in AXIS_ANCHORS.items() if anchors[0]}
        pairs["size"] = SIZE_ANCHORS
        for key, (high, low) in pairs.items():
            gaps = [hi - lo for hi, lo in (self._similarity(v, [high, low]) for v in neutral)]
            self._bias[key] = sum(gaps) / len(gaps)

    @staticmethod
    def _profile(face):
        return f"{face.name} typeface for {face.uses}. It feels {face.mood}."

    # -- scoring

    def _similarity(self, q, texts):
        vecs = self._embed(texts)
        return [float(q @ v) for v in vecs]

    def _lean(self, key, q, words, high, low, high_words, low_words):
        """-1 … 1: how far the description leans towards the axis maximum."""
        if words & high_words:
            return 0.9
        if words & low_words:
            return -0.9
        if q is None or high is None:
            return 0.0
        hi, lo = self._similarity(q, [high, low])
        gap = hi - lo - self._bias.get(key, 0.0)
        if abs(gap) < DEAD_ZONE:
            return 0.0
        gap -= DEAD_ZONE if gap > 0 else -DEAD_ZONE
        return max(-1.0, min(1.0, gap * GAIN))

    def match(self, query, faces):
        started = time.perf_counter()
        self._load()
        words = _words(query)
        q = None
        if self._model is not None:
            self._calibrate()
            q = self._embed([query])[0]

        ranked = []
        for f in faces:
            uses, mood = _phrases(f.uses), _phrases(f.mood)
            if q is not None:
                use_sims = self._similarity(q, uses)
                mood_sims = self._similarity(q, mood)
                score = 0.5 * self._similarity(q, [self._profile(f)])[0] + 0.35 * max(use_sims) + 0.15 * max(mood_sims)
            else:  # keyword fallback: shared words with the phrases
                use_sims = [len(words & _words(u)) for u in uses]
                mood_sims = [len(words & _words(m)) for m in mood]
                score = sum(use_sims) * 2 + sum(mood_sims)
            best = max(range(len(uses)), key=use_sims.__getitem__)
            top_moods = [m for _, m in sorted(zip(mood_sims, mood), reverse=True)[:2]]
            ranked.append((score, f, uses[best], use_sims[best], top_moods))
        ranked.sort(key=lambda r: r[0], reverse=True)
        score, face, best_use, best_use_sim, top_moods = ranked[0]

        settings_, adjustments = {}, []
        for axis in face.axes_ui:
            tag = axis["tag"]
            if tag not in AXIS_ANCHORS:
                continue
            lean = self._lean(tag, q, words, *AXIS_ANCHORS[tag])
            lo, hi, default = axis["min"], axis["max"], axis["default"]
            value = default + lean * ((hi - default) if lean > 0 else (default - lo))
            value = round(value, 2) if axis["step"] < 1 else int(round(value))
            settings_[tag] = value
            if abs(lean) >= 0.3 and value != default:
                adjustments.append(ADJUSTMENT_WORDS[tag][0 if lean > 0 else 1])

        size_lean = self._lean("size", q, words, *SIZE_ANCHORS, {"poster", "billboard", "headline", "logo", "banner"},
                               {"paragraph", "paragraphs", "body", "caption", "essay", "essays"})
        size = int(round(88 + size_lean * (52 if size_lean > 0 else 40)))  # 48 … 140 px

        said_something = any(words & (a[2] | a[3]) for a in AXIS_ANCHORS.values())
        confident = q is None or best_use_sim >= LOW_CONFIDENCE or said_something
        reason = f"Made for {best_use}, and it feels {' and '.join(top_moods)}."
        if adjustments:
            reason += f" Set {', '.join(adjustments[:-1]) + ' and ' if len(adjustments) > 1 else ''}{adjustments[-1]} to match your words."
        if not confident:
            reason = "That's a broad brief, so here's a versatile pick. " + reason

        return {
            "face": face,
            "settings": settings_,
            "size": size,
            "reason": reason,
            "runner_up": ranked[1][1] if len(ranked) > 1 else None,
            "ms": round((time.perf_counter() - started) * 1000, 1),
            "engine": self.engine,
        }


matcher = FontMatcher()


def warm_matcher():
    """Load the model and embed the index in the background so the first match is instant."""
    try:
        matcher.warm(list(Typeface.objects.all()))
        assistant.warm()
    except Exception:
        log.exception("Model warm-up failed")


class MatchForm(forms.Form):
    q = forms.CharField(min_length=3, max_length=200, strip=True, error_messages={
        "required": "Describe what you're setting first.",
        "min_length": "Add a few more words, like what it's for and how it should feel.",
        "max_length": "Keep it under 200 characters.",
    })


MATCHES_PER_MINUTE = 30


def match_payload(m, result):
    face = m.typeface
    return {
        "id": m.pk,
        "query": m.query,
        "face": {"name": face.name, "slug": face.slug, "url": face.get_absolute_url(), "family": face.name,
                 "designer": face.designer, "classification": face.get_classification_display()},
        "settings": m.settings,
        "settings_label": m.settings_label,
        "size": m.size,
        "reason": m.reason,
        "tester_url": m.tester_url,
        "runner_up": ({"name": result["runner_up"].name, "url": result["runner_up"].get_absolute_url()}
                      if result and result.get("runner_up") else None),
        "ms": result["ms"] if result else None,
        "engine": result["engine"] if result else None,
    }


@require_POST
def match(request):
    wants_json = request.headers.get("Accept", "").startswith("application/json")
    if not request.user.is_authenticated:
        if wants_json:
            return api_error(401, "Log in to use the font matcher.")
        return redirect_to_login(reverse("myapp:home") + "#match")

    form = MatchForm(request.POST)
    if not form.is_valid():
        error = form.errors["q"][0]
        if wants_json:  # the site's own error code: brief too short to match
            return JsonResponse({"error": error, "code": "OS-422"}, status=422)
        messages.error(request, error)
        return redirect("myapp:home")

    recent = request.user.matches.filter(created__gte=timezone.now() - timedelta(minutes=1)).count()
    if recent >= MATCHES_PER_MINUTE:
        error = "That's a lot of matches in a minute. Try again shortly."
        if wants_json:
            return api_error(429, error)
        messages.error(request, error)
        return redirect("myapp:home")

    query = form.cleaned_data["q"]
    result = matcher.match(query, list(Typeface.objects.all()))
    m = Match.objects.create(user=request.user, query=query, typeface=result["face"],
                             settings=result["settings"], size=result["size"], reason=result["reason"])
    if wants_json:
        return JsonResponse(match_payload(m, result))
    return redirect(f"{reverse('myapp:home')}?m={m.pk}#match")


# ------------------------------------------------------------------ request logging and limits

request_log = logging.getLogger("myapp.requests")


class RequestStats:
    """Counts since the process started, shown on /health/."""

    def __init__(self):
        self.started = time.time()
        self.lock = threading.Lock()
        self.total = 0
        self.by_class = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
        self.recent_ms = deque(maxlen=200)

    def add(self, status, ms):
        with self.lock:
            self.total += 1
            key = f"{status // 100}xx"
            if key in self.by_class:
                self.by_class[key] += 1
            self.recent_ms.append(ms)

    @property
    def avg_ms(self):
        return round(sum(self.recent_ms) / len(self.recent_ms), 1) if self.recent_ms else 0.0


stats = RequestStats()


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def ip_tag(request):
    """A short one-way tag for the visitor's IP, so logs can group requests without storing the address."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:{client_ip(request)}".encode()).hexdigest()[:12]


class RequestLogMiddleware:
    """Logs one line per request (id, method, path, status, time, user) and tags the response with X-Request-ID."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = self.get_response(request)
        ms = round((time.perf_counter() - started) * 1000, 1)
        user = getattr(request, "user", None)
        username = user.get_username() if user is not None and user.is_authenticated else "-"
        request_log.info("%s %s %s %s %sms user=%s ip=%s", request.request_id, request.method,
                         request.get_full_path()[:200], response.status_code, ms, username, ip_tag(request))
        stats.add(response.status_code, ms)
        response["X-Request-ID"] = request.request_id
        return response


def rate_limited(request, scope, limit, seconds):
    """True once a visitor has made more than `limit` requests in this scope within the window."""
    key = f"rl:{scope}:{ip_tag(request)}"
    cache.add(key, 0, seconds)
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, seconds)
        count = 1
    return count > limit


ERROR_CODE_HINTS = {400: "400", 401: "401", 403: "403", 404: "404", 405: "405", 429: "429", 500: "500", 503: "503"}


def api_error(status, message, **extra):
    return JsonResponse({"error": message, "code": ERROR_CODE_HINTS.get(status, str(status)), **extra}, status=status)


def same_origin(request):
    """Browsers always send Origin on POST; refuse cross-site calls to the JSON endpoints."""
    origin = request.headers.get("Origin")
    return not origin or urlsplit(origin).netloc == request.get_host()


def read_json(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ------------------------------------------------------------------ assistant
#
# Answers from the FAQ and error-code tables in the SQL database, using the same
# local embedding model as the font matcher. When nothing is close enough it
# says so and offers to open a support ticket. Every exchange is logged to MongoDB.

GREETING_RE = re.compile(r"^\W*(hi|hello|hey|hiya|yo|good (morning|afternoon|evening))\b[\W\w]{0,20}$", re.I)
THANKS_RE = re.compile(r"^\W*(thanks|thank you|thx|cheers|ty|great|perfect|ok(ay)?)\b[\w\s!.]{0,30}$", re.I)
ABOUT_RE = re.compile(r"\b(what can you do|who are you|what are you|help me|how can you help)\b", re.I)
CODE_RE = re.compile(r"(?<![\w-])(os[\s-]?\d{3}|[1-5]\d\d)(?![\w-])", re.I)
CODE_CONTEXT_RE = re.compile(r"\b(error|code|status|http|mean|means|meaning|got|getting|get|see|seeing|shows?)\b", re.I)

ANSWER_AT = 0.80     # similarity for a confident answer
MAYBE_AT = 0.745     # between this and ANSWER_AT: answer, but say it's a best guess
MESSAGE_LIMIT = 500


class Assistant:
    def _docs(self):
        faqs = list(Faq.objects.all())
        codes = list(ErrorCode.objects.all())
        # (kind, object, texts to compare with): the question, its other phrasings, and question + answer
        docs = [("faq", f, [f.question, *f.phrasing_list, f"{f.question} {f.answer}"]) for f in faqs]
        docs += [("error", c, [f"What does error {c.code} {c.title.lower()} mean?",
                               f"Error {c.code} {c.title}. {c.meaning}"]) for c in codes]
        return docs

    def warm(self):
        matcher._load()
        if matcher._model is not None:
            matcher._embed([t for d in self._docs() for t in d[2]])

    @staticmethod
    def _explain(code, prefix=""):
        text = f"{prefix}{code.code} · {code.title}. {code.meaning} What to do: {code.fix}"
        return {"kind": "error_code", "text": text, "source": {"title": f"Error {code.code}", "url": code.get_absolute_url()},
                "matched": code.code}

    def reply(self, message):
        text = message.strip()
        if GREETING_RE.match(text) and len(text) < 30:
            return {"kind": "greeting", "text": "Hi! Ask me about the typefaces, licensing, your account, or any "
                    "error code you've seen on this site."}
        if THANKS_RE.match(text) and len(text) < 40:
            return {"kind": "thanks", "text": "Glad that helped. Anything else?"}
        if ABOUT_RE.search(text):
            return {"kind": "about", "text": "I answer questions from the FAQ and explain the error codes this site "
                    "can show, like 404 or 429. If I can't answer, I'll open a support ticket so a person replies "
                    "by email.", "related": [f.question for f in Faq.objects.all()[:3]]}

        # 1. An error code, when the message is about one ("what does 429 mean", "error OS-422", "403?")
        code_match = CODE_RE.search(text)
        if code_match and (CODE_CONTEXT_RE.search(text) or len(text.split()) <= 3):
            raw = code_match.group(1).upper().replace(" ", "-")
            key = f"OS-{raw[-3:]}" if raw.startswith("OS") else raw
            code = ErrorCode.objects.filter(code=key).first()
            if code:
                return self._explain(code)
            known = ", ".join(ErrorCode.objects.values_list("code", flat=True))
            return {"kind": "unknown_code", "text": f"This site doesn't return error {key}. The codes it can show "
                    f"are {known}. Tell me which one you saw and I'll explain it.",
                    "source": {"title": "All error codes", "url": reverse("myapp:errors")}}

        # 2. The closest FAQ or error explanation
        docs = self._docs()
        matcher._load()
        if matcher._model is not None:
            q = matcher._embed([text])[0]
            scored = [(max(matcher._similarity(q, texts)), kind, obj) for kind, obj, texts in docs]
        else:  # keyword fallback when the model can't load
            words = _words(text) - STOPWORDS
            scored = [(max(len(words & (_words(t) - STOPWORDS)) / (len(words) or 1) for t in texts) * 0.9, kind, obj)
                      for kind, obj, texts in docs]
        scored.sort(key=lambda s: s[0], reverse=True)
        score, kind, obj = scored[0]
        related = [o.question for _, k, o in scored[1:6] if k == "faq" and o is not obj][:2]

        if score >= MAYBE_AT:
            prefix = "" if score >= ANSWER_AT else "I think you're asking about this: "
            if kind == "error":
                answer = self._explain(obj, prefix)
            else:
                answer = {"kind": "faq", "text": prefix + obj.answer, "matched": obj.question,
                          "source": {"title": obj.question, "url": obj.get_absolute_url()}}
            return {**answer, "score": round(score, 3), "related": related}

        return {"kind": "no_answer", "score": round(score, 3), "offer_ticket": True,
                "text": "I couldn't find that in the FAQ. I can open a support ticket so a person replies to you "
                        "by email.", "related": [o.question for _, k, o in scored[:3] if k == "faq"][:2]}


STOPWORDS = {"a", "an", "the", "is", "are", "do", "does", "i", "my", "me", "can", "how", "what", "to", "of", "for",
             "in", "on", "it", "this", "you", "your", "and", "or", "be", "with", "there", "any", "why", "when"}
assistant = Assistant()


class ChatForm(forms.Form):
    message = forms.CharField(max_length=MESSAGE_LIMIT, strip=True)
    session = forms.RegexField(regex=r"^[A-Za-z0-9_-]{8,64}$", required=False)
    page = forms.CharField(max_length=200, required=False)


@csrf_exempt  # JSON API used from every page, including error pages; protected by same_origin + rate limits
@require_POST
def chat(request):
    if not same_origin(request):
        return api_error(403, "Cross-site requests aren't allowed.")
    data = read_json(request)
    if data is None:
        return api_error(400, "Send the message as JSON, like {\"message\": \"Are the fonts free?\"}.")
    form = ChatForm(data)
    if not form.is_valid():
        if "message" in form.errors:
            limit = "Keep messages under 500 characters." if data.get("message") else "Type a question first."
            return api_error(400, limit)
        return api_error(400, "That chat session id isn't valid. Reload the page.")
    if rate_limited(request, "chat", limit=20, seconds=60):
        return api_error(429, "That's a lot of messages in a minute. Wait a moment and try again.")

    started = time.perf_counter()
    message = form.cleaned_data["message"]
    answer = assistant.reply(message)
    ms = round((time.perf_counter() - started) * 1000, 1)
    user = request.user if request.user.is_authenticated else None
    log_id = documents.insert("chat_logs", {
        "session": form.cleaned_data["session"] or None,
        "user": user.get_username() if user else None,
        "message": message,
        "reply": answer["text"],
        "kind": answer["kind"],
        "matched": answer.get("matched"),
        "score": answer.get("score"),
        "ms": ms,
        "page": form.cleaned_data["page"] or None,
        "ip": ip_tag(request),
        "request_id": getattr(request, "request_id", ""),
        "created": timezone.now(),
    })
    return JsonResponse({**answer, "id": log_id, "ms": ms,
                         "email": user.email if user else ""})


class FeedbackForm(forms.Form):
    id = forms.RegexField(regex=r"^[a-f0-9]{24}$")
    helpful = forms.BooleanField(required=False)
    comment = forms.CharField(max_length=300, required=False, strip=True)


@csrf_exempt
@require_POST
def chat_feedback(request):
    if not same_origin(request):
        return api_error(403, "Cross-site requests aren't allowed.")
    data = read_json(request)
    form = FeedbackForm(data) if data is not None else None
    if form is None or not form.is_valid() or not isinstance(data.get("helpful"), bool):
        return api_error(400, "Feedback needs the message id and helpful: true or false.")
    if rate_limited(request, "feedback", limit=30, seconds=60):
        return api_error(429, "Too much feedback at once. Try again in a minute.")
    documents.insert("feedback", {
        "log_id": form.cleaned_data["id"],
        "helpful": data["helpful"],
        "comment": form.cleaned_data["comment"] or None,
        "user": request.user.get_username() if request.user.is_authenticated else None,
        "ip": ip_tag(request),
        "created": timezone.now(),
    })
    return JsonResponse({"ok": True, "text": "Thanks for the feedback."})


class TicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ["name", "email", "question", "session_id"]

    def clean_question(self):
        q = self.cleaned_data["question"].strip()
        if len(q) < 5:
            raise forms.ValidationError("Describe the problem in a few words.")
        return q[:2000]


@csrf_exempt
@require_POST
def ticket(request):
    if not same_origin(request):
        return api_error(403, "Cross-site requests aren't allowed.")
    data = read_json(request)
    if data is None:
        return api_error(400, "Send the ticket as JSON.")
    form = TicketForm({k: data.get(k, "") for k in ("name", "email", "question", "session_id")})
    if not form.is_valid():
        field, errors = next(iter(form.errors.items()))
        message = "Enter a valid email address so we can reply." if field == "email" else errors[0]
        return api_error(400, message, field=field)
    if rate_limited(request, "ticket", limit=5, seconds=3600):
        return api_error(429, "You've opened several tickets already. We'll reply to those first.")
    t = form.save(commit=False)
    if request.user.is_authenticated:
        t.user = request.user
    t.save()
    documents.insert("chat_logs", {
        "session": t.session_id or None, "user": t.user.get_username() if t.user else None,
        "message": None, "reply": f"Ticket {t.reference} opened", "kind": "ticket", "matched": t.reference,
        "ip": ip_tag(request), "request_id": getattr(request, "request_id", ""), "created": timezone.now(),
    })
    log.info("Support ticket %s opened", t.reference)
    return JsonResponse({"id": t.pk, "reference": t.reference,
                         "text": f"Ticket {t.reference} is open. We'll reply to {t.email}."}, status=201)


# ------------------------------------------------------------------ third-party API: GitHub
#
# Typeface pages show when the font last changed in the google/fonts repository.
# Every call has a hard time limit; on failure the last good answer is reused,
# and if there is none the page says the history is unavailable.

GITHUB_FRESH = 6 * 3600      # seconds before asking GitHub again
GITHUB_STALE = 7 * 24 * 3600  # how long a last-known answer may stand in when GitHub fails


def _github_headers():
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "open-specimen",
               "X-GitHub-Api-Version": "2022-11-28"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers


def font_history(face):
    if not face.gf_path:
        return {"status": "unavailable", "text": "No Google Fonts history for this typeface."}
    fresh_key, stale_key = f"gh:{face.slug}", f"gh-stale:{face.slug}"
    if cached := cache.get(fresh_key):
        return {**cached, "source": "cache"}
    started = time.perf_counter()
    try:
        r = requests.get("https://api.github.com/repos/google/fonts/commits", headers=_github_headers(),
                         params={"path": face.gf_path, "per_page": 1}, timeout=settings.GITHUB_TIMEOUT)
        r.raise_for_status()
        commits = r.json()
        if not commits:
            result = {"status": "ok", "text": "No changes recorded in Google Fonts yet.", "date": None}
        else:
            c = commits[0]
            result = {"status": "ok", "date": c["commit"]["committer"]["date"][:10],
                      "message": c["commit"]["message"].splitlines()[0][:120], "url": c["html_url"]}
        result["ms"] = round((time.perf_counter() - started) * 1000)
        cache.set(fresh_key, result, GITHUB_FRESH)
        cache.set(stale_key, result, GITHUB_STALE)
        return {**result, "source": "live"}
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log.warning("GitHub history for %s failed: %s", face.slug, exc)
        if stale := cache.get(stale_key):
            return {**stale, "source": "stale"}
        return {"status": "unavailable", "source": "fallback",
                "text": "GitHub didn't answer in time, so the update history is unavailable right now."}


def typeface_history(request, slug):
    face = get_object_or_404(Typeface, slug=slug)
    return JsonResponse(font_history(face))


def github_status():
    """(status, detail) for the health page, cached for a minute. /rate_limit doesn't count against the limit."""
    if cached := cache.get("gh:status"):
        return cached
    result = _github_status()
    cache.set("gh:status", result, 60)
    return result


def _github_status():
    started = time.perf_counter()
    try:
        r = requests.get("https://api.github.com/rate_limit", headers=_github_headers(), timeout=settings.GITHUB_TIMEOUT)
        r.raise_for_status()
        core = r.json()["resources"]["core"]
        return "ok", f"{core['remaining']}/{core['limit']} requests left this hour · {round((time.perf_counter() - started) * 1000)} ms"
    except (requests.RequestException, ValueError, KeyError) as exc:
        return "down", f"{type(exc).__name__}; typeface pages fall back to cached history"


# ------------------------------------------------------------------ health

def run_checks():
    checks = []
    started = time.perf_counter()
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        detail = (f"{connection.vendor} · {Faq.objects.count()} FAQs, {ErrorCode.objects.count()} error codes, "
                  f"{SupportTicket.objects.count()} tickets · {round((time.perf_counter() - started) * 1000)} ms")
        checks.append(("SQL database", "ok", detail))
    except Exception as exc:
        checks.append(("SQL database", "down", f"{type(exc).__name__}: {str(exc)[:160]}"))
    checks.append(("MongoDB (chat logs)", *documents.ping()))
    if matcher._model is not None:
        checks.append(("AI model", "ok", f"{settings.MATCHER_MODEL} loaded · {len(matcher._vectors)} phrases cached"))
    elif matcher._failed:
        checks.append(("AI model", "degraded", "Model failed to load; the assistant is using keyword matching"))
    else:
        checks.append(("AI model", "loading", "Loads in the background after a restart"))
    checks.append(("GitHub API", *github_status()))
    sql_ok = checks[0][1] == "ok"
    overall = "ok" if all(c[1] in ("ok", "not configured", "loading") for c in checks) else ("degraded" if sql_ok else "down")
    return overall, checks


@login_not_required
def health(request):
    overall, checks = run_checks()
    status = 200 if overall != "down" else 503
    uptime = int(time.time() - stats.started)
    payload = {
        "status": overall,
        "checks": [{"name": n, "status": s, "detail": d} for n, s, d in checks],
        "version": settings.APP_VERSION,
        "uptime_seconds": uptime,
        "requests": {"total": stats.total, **stats.by_class, "avg_ms_last_200": stats.avg_ms},
        "time": timezone.now().isoformat(timespec="seconds"),
    }
    if request.path.endswith(".json"):
        return JsonResponse(payload, status=status)
    return render(request, "myapp/health.html", {**payload, "uptime": timedelta(seconds=uptime), "now": timezone.now()},
                  status=status)


# ------------------------------------------------------------------ error pages

def _error_page(request, status, title, lead, ask):
    code = ErrorCode.objects.filter(code=str(status)).first() if status != 500 else None
    return render(request, "myapp/error.html", {"status": status, "title": title, "lead": lead, "ask": ask,
                                                "code": code}, status=status)


def bad_request(request, exception=None):
    return _error_page(request, 400, "That request didn't make sense to us.",
                       "Something in it was malformed. Reload the page and try again.", "What does error 400 mean?")


def permission_denied(request, exception=None):
    return _error_page(request, 403, "You can't do that here.",
                       "You don't have permission for this page or action.", "What does error 403 mean?")


def csrf_failure(request, reason=""):
    return _error_page(request, 403, "This form expired.",
                       "Its security token is out of date. Reload the page and send it again.",
                       "What does error 403 mean?")


def page_not_found(request, exception=None):
    return _error_page(request, 404, "There's no page at this address.",
                       "The typeface may have been removed from the index, or the link has a typo.",
                       "What does error 404 mean?")


def server_error(request):
    # Kept independent of the database and context processors, which may be what failed.
    return HttpResponseServerError(loader.get_template("500.html").render({"request_id": getattr(request, "request_id", "")}))


# ------------------------------------------------------------------ accounts

class SignupForm(AccessibleErrorsMixin, UserCreationForm):
    first_name = forms.CharField(label="Name", max_length=150)
    email = forms.EmailField(label="Email")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["first_name", "email", "username"]
        help_texts = {"username": "Letters, digits and @ . + - _ only. You'll log in with this."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.pop("autofocus", None)  # start at the first field instead
        self.fields["first_name"].widget.attrs.update(autocomplete="name", autofocus=True)
        self.fields["email"].widget.attrs.update(autocomplete="email")
        self.fields["username"].widget.attrs.update(autocomplete="username", autocapitalize="none")
        for name in ("password1", "password2"):
            self.fields[name].widget.attrs.update(autocomplete="new-password")
        self.fields["password1"].help_text = "At least 8 characters, not too common, not all numbers."
        self.fields["password2"].label = "Confirm password"
        self.fields["password2"].help_text = ""
        self.mark_errors()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Log in instead.")
        return email


class LoginForm(AccessibleErrorsMixin, AuthenticationForm):
    error_messages = {
        "invalid_login": "That username and password don't match. Check both and try again.",
        "inactive": "This account is switched off.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(autocapitalize="none")
        self.mark_errors()


@login_not_required
def signup(request):
    if request.user.is_authenticated:
        return redirect("myapp:home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Account created. Log in with your username, {user.username}.")
        request.session["new_username"] = user.username
        return redirect("myapp:login")
    return render(request, "myapp/signup.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "myapp/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_initial(self):
        return {"username": self.request.session.pop("new_username", "")}


# ------------------------------------------------------------------ pages

class SubmissionForm(AccessibleErrorsMixin, forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["typeface", "designer", "url", "email", "ofl", "note"]
        widgets = {
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mark_errors()

    def clean_ofl(self):
        if not self.cleaned_data["ofl"]:
            raise forms.ValidationError("We only list typefaces under the Open Font License.")
        return True


def home(request):
    faces = Typeface.objects.all()
    active = request.GET.get("class", "")
    shown = faces.filter(classification=active) if active in Typeface.Classification.values else faces
    if shown is faces:
        active = ""
    recent, current = [], None
    if request.user.is_authenticated:
        recent = request.user.matches.select_related("typeface")[:5]
        if request.GET.get("m", "").isdigit():  # result of a match sent without JavaScript
            current = request.user.matches.select_related("typeface").filter(pk=request.GET["m"]).first()
    return render(request, "myapp/home.html", {
        "faces": shown,
        "total": faces.count(),
        "classes": Typeface.Classification.choices,
        "active": active,
        "fonts_url": fonts_url(faces),
        "examples": EXAMPLES,
        "recent": recent,
        "current": current,
    })


def typeface(request, slug):
    face = get_object_or_404(Typeface, slug=slug)
    faces = list(Typeface.objects.all())
    i = faces.index(face)
    nxt = faces[(i + 1) % len(faces)]
    return render(request, "myapp/typeface.html", {
        "face": face,
        "next": nxt,
        "glyphs": GLYPHS,
        "waterfall": WATERFALL,
        "fonts_url": fonts_url([face, nxt]),
    })


@login_required
def submit(request):
    form = SubmissionForm(request.POST or None, initial={"email": request.user.email})
    if request.method == "POST" and form.is_valid():
        s = form.save()
        messages.success(request, f"Thanks — we'll review {s.typeface} and reply to {s.email}.")
        return redirect("myapp:submit")
    return render(request, "myapp/submit.html", {"form": form})


def faq(request):
    faqs = Faq.objects.all()
    categories = {}
    for f in faqs:
        categories.setdefault(f.category, []).append(f)
    return render(request, "myapp/faq.html", {"categories": categories, "count": len(faqs)})


def errors(request):
    return render(request, "myapp/errors.html", {"codes": ErrorCode.objects.all()})
