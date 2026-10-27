import io
import os
import re
import secrets
from importlib import import_module
from unittest import mock

import requests
from PIL import Image

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings
from playwright.sync_api import expect, sync_playwright

from . import views
from .models import ErrorCode, Faq, Match, Submission, SupportTicket, Typeface, documents

# Playwright's sync API runs an event loop; Django's ORM guard would otherwise refuse.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

SEEDS = [import_module(f"myapp.migrations.{name}").seed for name in (
    "0002_seed_typefaces", "0004_seed_matcher_profiles", "0006_seed_help", "0008_seed_faq_phrasings")]


def seed(apps, schema_editor):
    for s in SEEDS:
        s(apps, schema_editor)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def fake_github(url, **kwargs):
    """Stands in for api.github.com so tests never depend on the network."""
    if url.endswith("/rate_limit"):
        return FakeResponse({"resources": {"core": {"remaining": 59, "limit": 60}}})
    return FakeResponse([{"html_url": "https://github.com/google/fonts/commit/abc",
                          "commit": {"message": "Update family\n\nlong body", "committer": {"date": "2026-05-04T10:00:00Z"}}}])


@override_settings(MONGODB_URI="mongomock://localhost")
class BrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        # Live-server tests flush the database between tests; reseed the index, FAQs and error codes.
        seed(django_apps, None)
        cache.clear()  # rate limits and GitHub answers
        documents._client = None  # a fresh in-memory MongoDB (mongomock) per test
        self.github = mock.patch("myapp.views.requests.get", side_effect=fake_github)
        self.github_get = self.github.start()
        self.addCleanup(self.github.stop)
        # Tests run as a logged-in user unless they say otherwise.
        self.user = User.objects.create_user("tester", "tester@example.test", secrets.token_urlsafe(16),
                                             first_name="Test")
        self.ctx = self.new_context()
        self.page = self.ctx.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        self.expected_errors = 0  # the 404 test expects the browser's own "failed to load" line

    def tearDown(self):
        self.ctx.close()
        self.assertEqual(len(self.errors), self.expected_errors, f"Errors in the browser console: {self.errors}")

    def new_context(self, logged_in=True, **kwargs):
        kwargs.setdefault("viewport", {"width": 1440, "height": 900})
        ctx = self.browser.new_context(**kwargs)
        if logged_in:
            client = Client()
            client.force_login(self.user)
            ctx.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value,
                              "url": self.live_server_url}])
        return ctx

    def url(self, path):
        return f"{self.live_server_url}{path}"

    def test_hero_word_fills_the_grid_without_overflow(self):
        self.page.goto(self.url("/"))
        word = self.page.locator(".hero__word")
        expect(word).to_have_class("hero__word is-fit")
        # The outer letters reach into the page margin by their side bearings only, never off-screen.
        right, viewport = word.evaluate(
            "el => [Math.max(...[...el.children].map(s => s.getBoundingClientRect().right)), innerWidth]")
        self.assertLess(right, viewport)

    def test_hero_letters_follow_the_cursor(self):
        self.page.goto(self.url("/"))
        expect(self.page.locator(".hero__word")).to_have_class("hero__word is-fit")
        box = self.page.locator(".hero__word").bounding_box()
        self.page.mouse.move(box["x"] + 5, box["y"] + box["height"] / 2)
        self.page.wait_for_timeout(1500)
        first, last = self.page.locator(".hero__word span").evaluate_all(
            "els => [els[0], els.at(-1)].map(e => e.getBoundingClientRect().width)")
        self.assertGreater(first, last)

    def test_index_lists_every_typeface_in_its_own_face(self):
        self.page.goto(self.url("/"))
        rows = self.page.locator(".rows .row")
        expect(rows).to_have_count(Typeface.objects.count())
        family = rows.first.locator(".row__name").evaluate("el => getComputedStyle(el).fontFamily")
        self.assertIn("Anybody", family)

    def test_filter_by_classification(self):
        self.page.goto(self.url("/"))
        self.page.get_by_role("link", name="Serif", exact=True).click()
        expect(self.page.locator(".rows .row")).to_have_count(Typeface.objects.filter(classification="serif").count())

    def test_tester_sliders_change_the_sample(self):
        self.page.goto(self.url("/type/anybody/"))
        self.page.locator('[data-axis="wdth"]').fill("150")
        self.page.locator("[data-size]").fill("120")
        sample = self.page.locator(".tester__text")
        expect(sample).to_have_css("font-size", "120px")
        self.assertIn('"wdth" 150', sample.evaluate("el => getComputedStyle(el).fontVariationSettings"))
        self.page.get_by_role("button", name="Reset").click()
        expect(sample).to_have_css("font-size", "72px")

    def test_glyph_inspector(self):
        self.page.goto(self.url("/type/literata/"))
        self.page.locator('[data-glyph="&"]').hover()
        expect(self.page.locator("[data-glyph-view]")).to_have_text("&")
        expect(self.page.locator("[data-glyph-code]")).to_have_text("U+0026")

    def test_next_link_cycles_through_the_index(self):
        last = Typeface.objects.last()
        self.page.goto(self.url(last.get_absolute_url()))
        self.page.locator("a.next").click()
        expect(self.page.locator("h1")).to_have_text(Typeface.objects.first().name)

    def test_submit_requires_ofl(self):
        self.page.goto(self.url("/submit/"))
        self.page.get_by_label("Typeface name").fill("Fraktur Neue")
        self.page.get_by_label("Designer").fill("A. Designer")
        self.page.get_by_label("Link to the font files").fill("https://example.test/fonts")
        self.page.get_by_label("Your email").fill("a@example.test")
        self.page.get_by_role("button", name="Send submission").click()
        expect(self.page.locator(".field__error")).to_contain_text("Open Font License")
        self.assertFalse(Submission.objects.exists())

        self.page.get_by_label("It's licensed under the SIL Open Font License").check()
        self.page.get_by_role("button", name="Send submission").click()
        expect(self.page.locator(".notice")).to_contain_text("Fraktur Neue")
        self.assertEqual(Submission.objects.get().email, "a@example.test")

    def test_grid_overlay_toggles_with_g(self):
        self.page.goto(self.url("/"))
        self.page.keyboard.press("g")
        expect(self.page.locator("html")).to_have_class(re.compile(r"\bshow-grid\b"))
        expect(self.page.locator(".grid-toggle")).to_have_attribute("aria-pressed", "true")

    def test_no_horizontal_scroll_at_any_size(self):
        for width in (375, 768, 1024, 1440, 1920):
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in ["/", "/type/recursive/", "/type/big-shoulders-display/", "/submit/"]:
                self.page.goto(self.url(path))
                over = self.page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
                self.assertFalse(over, f"{path} scrolls sideways at {width}px")

    def test_nothing_crosses_the_right_edge(self):
        # body hides horizontal overflow, so check every element's box directly
        find = """() => {
          const vw = document.documentElement.clientWidth;
          return [...document.querySelectorAll('body *')]
            .filter(el => !el.closest('.overlay'))
            .filter(el => { const r = el.getBoundingClientRect(); return r.width && r.right > vw + 0.5; })
            .map(el => el.className || el.tagName).slice(0, 5);
        }"""
        for width in (375, 800, 1100, 1280, 1440, 1920):
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in ["/", "/type/bricolage-grotesque/", "/type/big-shoulders-display/", "/submit/"]:
                self.page.goto(self.url(path))
                self.page.evaluate("document.fonts.ready")
                self.assertEqual(self.page.evaluate(find), [], f"{path} at {width}px")

    def test_unknown_typeface_shows_our_404(self):
        self.expected_errors = 1
        self.assertEqual(self.page.goto(self.url("/type/comic-sans/")).status, 404)
        expect(self.page.locator("h1")).to_have_text("There's no page at this address.")
        self.page.get_by_role("link", name="Back to the index").click()
        expect(self.page.locator(".rows .row")).to_have_count(Typeface.objects.count())

    def test_hero_ink_meets_both_margins(self):
        # The letters' ink (not their boxes) should touch the grid edges as the wave moves.
        self.page.goto(self.url("/"))
        word = self.page.locator(".hero__word")
        expect(word).to_have_class("hero__word is-fit")
        box = word.bounding_box()
        for frac in (0.0, 0.5, 1.0):
            self.page.mouse.move(box["x"] + box["width"] * frac, box["y"] + box["height"] / 2)
            self.page.wait_for_timeout(1500)
            im = Image.open(io.BytesIO(word.screenshot())).convert("L")
            px, (w, h) = im.load(), im.size
            ink = [x for x in range(w) if any(px[x, y] < 100 for y in range(0, h, 2))]
            self.assertLessEqual(ink[0], 6, f"left gap at {frac}")
            self.assertLessEqual(w - 1 - ink[-1], 6, f"right gap at {frac}")

    def test_hero_moves_on_its_own(self):
        self.page.goto(self.url("/"))
        expect(self.page.locator(".hero__word")).to_have_class("hero__word is-fit")
        read = lambda: self.page.locator("[data-readout]").text_content()  # noqa: E731
        before = read()
        self.page.wait_for_timeout(800)
        self.assertNotEqual(read(), before)

    def test_hero_follows_cursor_with_reduced_motion(self):
        # Windows "Animation effects: off" sets prefers-reduced-motion.
        ctx = self.new_context(reduced_motion="reduce")
        page = ctx.new_page()
        page.goto(self.url("/"))
        word = page.locator(".hero__word")
        expect(word).to_have_class("hero__word is-fit")
        widths = lambda: page.locator(".hero__word span").evaluate_all(  # noqa: E731
            "els => [els[0], els.at(-1)].map(e => e.getBoundingClientRect().width)")
        box = word.bounding_box()
        page.mouse.move(box["x"] + 5, box["y"] + box["height"] / 2)
        page.wait_for_timeout(1500)
        first, last = widths()
        self.assertGreater(first, last * 2)
        page.mouse.move(box["x"] + box["width"] - 5, box["y"] + box["height"] / 2, steps=5)
        page.wait_for_timeout(1500)
        first, last = widths()
        self.assertGreater(last, first * 2)
        # no self-running wave: nothing changes while the pointer rests
        settled = page.locator("[data-readout]").text_content()
        page.wait_for_timeout(3500)
        self.assertEqual(page.locator("[data-readout]").text_content(), settled)
        ctx.close()

    def test_hero_is_visible_without_javascript(self):
        ctx = self.new_context(java_script_enabled=False)
        page = ctx.new_page()
        page.goto(self.url("/"))
        expect(page.locator(".hero__word")).to_be_visible()
        ctx.close()

    def test_slant_slider_moves_in_whole_degrees(self):
        self.page.goto(self.url("/type/recursive/"))
        expect(self.page.locator('[data-axis="slnt"]')).to_have_attribute("step", "1")
        expect(self.page.locator('[data-axis="MONO"]')).to_have_attribute("step", "0.01")

    def test_edited_text_flows_into_waterfall_and_reset_restores_it(self):
        self.page.goto(self.url("/type/newsreader/"))
        tester = self.page.locator(".tester__text")
        tester.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.type("Hamburgefonstiv")
        expect(self.page.locator(".waterfall__line").first).to_have_text("Hamburgefonstiv")
        self.page.locator('[data-axis="wght"]').fill("800")
        self.assertIn('"wght" 800', self.page.locator(".waterfall__line").first.evaluate(
            "el => getComputedStyle(el).fontVariationSettings"))
        self.page.get_by_role("button", name="Reset").click()
        sample = Typeface.objects.get(slug="newsreader").sample
        expect(tester).to_have_text(sample)
        expect(self.page.locator(".waterfall__line").first).to_have_text(sample)

    def test_form_errors_are_announced_and_focused(self):
        self.page.goto(self.url("/submit/"))
        self.page.get_by_role("button", name="Send submission").click()
        name = self.page.get_by_label("Typeface name")
        expect(name).to_be_focused()
        expect(name).to_have_attribute("aria-invalid", "true")
        expect(name).to_have_attribute("aria-describedby", "id_typeface_error")
        expect(self.page.locator("#id_typeface_error")).to_be_visible()

    def test_admin_is_branded(self):
        self.page.goto(self.url("/admin/login/"))
        expect(self.page.locator("#site-name")).to_have_text("Open Specimen")

    # ------------------------------------------------------------ accounts

    def guest_page(self):
        ctx = self.new_context(logged_in=False)
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        return page

    def test_public_pages_open_without_an_account(self):
        page = self.guest_page()
        for path in ["/", "/type/anybody/", "/faq/", "/errors/", "/health/"]:
            response = page.goto(self.url(path))
            self.assertEqual(response.status, 200, path)
            expect(page.locator(".assistant__launch")).to_be_visible()
        page.goto(self.url("/"))
        expect(page.get_by_role("link", name="Sign up").first).to_be_visible()
        expect(page.locator("[data-matcher]")).to_have_count(0)  # the matcher needs an account

    def test_account_only_pages_ask_guests_to_log_in(self):
        page = self.guest_page()
        page.goto(self.url("/submit/"))
        expect(page).to_have_url(re.compile(r"/login/\?next=/submit/"))
        expect(page.locator("h1")).to_have_text("Welcome back.")

    def test_sign_up_then_log_in_with_username(self):
        page = self.guest_page()
        password = secrets.token_urlsafe(14)
        page.goto(self.url("/signup/"))
        page.get_by_label("Name", exact=True).fill("Ada Lovelace")
        page.get_by_label("Email").fill("Ada@Example.test")
        page.get_by_label("Username").fill("ada")
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_label("Confirm password").fill(password)
        page.get_by_role("button", name="Create account").click()

        expect(page).to_have_url(self.url("/login/"))
        expect(page.locator(".notice")).to_contain_text("Log in with your username, ada")
        expect(page.get_by_label("Username")).to_have_value("ada")  # prefilled
        user = User.objects.get(username="ada")
        self.assertEqual((user.first_name, user.email), ("Ada Lovelace", "ada@example.test"))

        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Log in").click()
        expect(page).to_have_url(self.url("/"))
        expect(page.locator(".account__name")).to_have_text("ada")

        page.get_by_role("button", name="Log out").click()
        expect(page).to_have_url(self.url("/login/"))
        page.goto(self.url("/submit/"))
        expect(page).to_have_url(re.compile(r"/login/"))

    def test_sign_up_rejects_bad_details(self):
        page = self.guest_page()
        page.goto(self.url("/signup/"))
        page.get_by_label("Name", exact=True).fill("Copycat")
        page.get_by_label("Email").fill("TESTER@example.test")  # already used by self.user
        page.get_by_label("Username").fill("tester")
        page.get_by_label("Password", exact=True).fill("password")
        page.get_by_label("Confirm password").fill("different")
        page.get_by_role("button", name="Create account").click()
        expect(page.locator("#id_email_error")).to_contain_text("already exists")
        expect(page.locator("#id_username_error")).to_contain_text("already exists")
        expect(page.locator("#id_password2_error")).to_contain_text("password fields didn")
        self.assertEqual(User.objects.count(), 1)

    def test_wrong_password_is_explained(self):
        page = self.guest_page()
        page.goto(self.url("/login/"))
        page.get_by_label("Username").fill("tester")
        page.get_by_label("Password", exact=True).fill("not-the-password")
        page.get_by_role("button", name="Log in").click()
        expect(page.locator(".form-error")).to_contain_text("don't match")

    # ------------------------------------------------------------ font matcher

    def match(self, text):
        self.page.get_by_label("What are you setting, and how should it feel?").fill(text)
        self.page.get_by_role("button", name="Find a typeface").click()
        expect(self.page.locator("[data-result]")).to_be_visible()

    def test_matcher_picks_and_sets_a_typeface(self):
        self.page.goto(self.url("/"))
        self.match("Loud poster for a summer music festival")
        expect(self.page.locator('[data-r="face"]')).to_have_text("Anybody")
        expect(self.page.locator('[data-r="settings"]')).to_contain_text("wght 850")
        expect(self.page.locator('[data-r="reason"]')).to_contain_text("festival posters")
        expect(self.page.locator('[data-r="ms"]')).to_have_text(re.compile(r"^\d+(\.\d)? ms$"))
        sample = self.page.locator('[data-r="sample"]')
        expect(sample).to_have_text("Loud poster for a summer music festival")
        self.assertIn("Anybody", sample.evaluate("el => getComputedStyle(el).fontFamily"))
        # saved to this user's history and shown at the top of the list
        self.assertEqual(Match.objects.get().user, self.user)
        expect(self.page.locator(".recent__row").first).to_contain_text("Anybody")

    def test_matcher_examples_and_answers_fit_the_brief(self):
        expected = {
            "Menu for a relaxed wine bar": "Instrument Serif",
            "Theme for a code editor": "Recursive",
            "Long essays on a calm reading blog": "Newsreader",
        }
        self.page.goto(self.url("/"))
        for example, face in expected.items():
            self.page.get_by_role("button", name=example).click()
            expect(self.page.locator('[data-r="face"]')).to_have_text(face)
        expect(self.page.locator(".recent__row")).to_have_count(3)

    def test_matcher_is_fast(self):
        self.page.goto(self.url("/"))
        self.match("A fantasy novel")  # first call loads the model
        self.match("Tiny delicate jewellery label")
        ms = float(self.page.locator('[data-r="ms"]').text_content().split()[0])
        self.assertLess(ms, 200)

    def test_matcher_explains_short_input(self):
        self.page.goto(self.url("/"))
        self.page.get_by_label("What are you setting, and how should it feel?").fill("a")
        self.page.get_by_role("button", name="Find a typeface").click()
        expect(self.page.locator(".matcher__error")).to_contain_text("Add a few more words")
        self.assertFalse(Match.objects.exists())

    def test_open_in_tester_carries_the_settings(self):
        self.page.goto(self.url("/"))
        self.match("Theme for a code editor")
        self.page.get_by_role("link", name="Open in the tester").click()
        expect(self.page).to_have_url(re.compile(r"/type/recursive/\?"))
        expect(self.page.locator(".tester__text")).to_have_text("Theme for a code editor")
        expect(self.page.locator('[data-axis="MONO"]')).to_have_value("1")

    def test_matcher_works_without_javascript(self):
        ctx = self.new_context(java_script_enabled=False)
        page = ctx.new_page()
        page.goto(self.url("/"))
        page.get_by_label("What are you setting, and how should it feel?").fill("Train station signs")
        page.get_by_role("button", name="Find a typeface").click()
        expect(page.locator('[data-r="face"]')).to_have_text("Big Shoulders Display")
        ctx.close()

    def test_matches_are_private(self):
        other = User.objects.create_user("other", "other@example.test", secrets.token_urlsafe(16))
        theirs = Match.objects.create(user=other, query="secret brief", typeface=Typeface.objects.first(),
                                      reason="r")
        self.page.goto(self.url(f"/?m={theirs.pk}"))
        expect(self.page.locator("[data-result]")).to_be_hidden()
        expect(self.page.get_by_text("secret brief")).to_have_count(0)

    def test_match_endpoint_rejects_bad_requests(self):
        guest = Client()
        self.assertEqual(guest.post("/match/", {"q": "anything at all"}).status_code, 302)  # to login
        r = guest.post("/match/", {"q": "anything at all"}, HTTP_ACCEPT="application/json")
        self.assertEqual((r.status_code, r.json()["code"]), (401, "401"))
        member = Client()
        member.force_login(self.user)
        r = member.post("/match/", {"q": ""}, HTTP_ACCEPT="application/json")
        self.assertEqual((r.status_code, r.json()["code"]), (422, "OS-422"))  # the site-specific code
        self.assertIn("Describe", r.json()["error"])
        self.assertEqual(member.get("/match/").status_code, 405)

    # ------------------------------------------------------------ FAQ, error codes, assistant

    def open_assistant(self, page=None):
        page = page or self.page
        page.get_by_role("button", name="Ask the assistant").first.click()
        expect(page.get_by_role("dialog", name="Assistant")).to_be_visible()
        return page

    def chat(self, text, page=None):
        page = page or self.page
        bots = page.locator(".msg--bot:not(.msg--typing)")
        before = bots.count()
        page.get_by_label("Your question").fill(text)
        page.get_by_role("button", name="Send").click()
        expect(bots).to_have_count(before + 1)
        return bots.last

    def test_faq_page_lists_faqs_from_the_database(self):
        self.assertGreaterEqual(Faq.objects.count(), 10)
        self.page.goto(self.url("/faq/"))
        expect(self.page.locator("details.faq")).to_have_count(Faq.objects.count())
        first = self.page.locator("details.faq").first
        first.locator("summary").click()
        expect(first.locator(".faq__answer")).to_be_visible()

    def test_error_codes_page_lists_every_code(self):
        expected = {"400", "401", "403", "404", "429", "500", "503", "OS-422"}
        self.assertTrue(expected <= set(ErrorCode.objects.values_list("code", flat=True)))
        self.page.goto(self.url("/errors/"))
        expect(self.page.locator("li.code")).to_have_count(ErrorCode.objects.count())
        expect(self.page.locator("#code-OS-422 .code__tag")).to_have_text("This site")

    def test_chat_widget_is_on_every_page(self):
        for path in ["/", "/type/syne/", "/faq/", "/errors/", "/health/", "/login/", "/signup/", "/submit/",
                     "/no-such-page/"]:
            self.page.goto(self.url(path))
            expect(self.page.locator("[data-assistant]")).to_have_count(1)
        self.expected_errors = 1  # the browser logs the 404 response of /no-such-page/

    def test_assistant_answers_from_the_faq(self):
        self.page.goto(self.url("/faq/"))
        self.open_assistant()
        reply = self.chat("can I use these fonts commercially")
        expect(reply).to_contain_text("SIL Open Font License")
        expect(reply.locator(".msg__source")).to_have_text("Source: Are the fonts free to use?")
        log = documents.find("chat_logs")[0]  # stored in MongoDB
        self.assertEqual((log["kind"], log["matched"], log["user"]), ("faq", "Are the fonts free to use?", "tester"))

    def test_assistant_explains_error_codes(self):
        self.page.goto(self.url("/"))
        self.open_assistant()
        expect(self.chat("what does 429 mean?")).to_contain_text("Too many requests")
        expect(self.chat("I got error OS-422")).to_contain_text("Brief too short to match")
        expect(self.chat("page not found")).to_contain_text("404")
        expect(self.chat("error 418")).to_contain_text("doesn't return error 418")

    def test_assistant_opens_a_ticket_when_it_cannot_answer(self):
        page = self.guest_page()
        page.goto(self.url("/"))
        self.open_assistant(page)
        reply = self.chat("Who won the world cup in 1966?", page)
        expect(reply).to_contain_text("couldn't find that")
        reply.get_by_label("Your email").fill("guest@example.test")
        expect(reply.get_by_label("Your question")).to_have_value("Who won the world cup in 1966?")
        reply.get_by_role("button", name="Open a support ticket").click()
        expect(reply).to_contain_text(re.compile(r"Ticket T-\d{5} is open"))
        t = SupportTicket.objects.get()  # stored in SQL
        self.assertEqual((t.email, t.status, t.user), ("guest@example.test", "open", None))
        self.assertEqual(documents.find("chat_logs", {"kind": "ticket"})[0]["matched"], t.reference)

    def test_ticket_needs_a_valid_email(self):
        self.page.goto(self.url("/"))
        self.open_assistant()
        reply = self.chat("Can you design a logo for me?")
        reply.get_by_label("Your email").fill("not-an-email")
        reply.get_by_role("button", name="Open a support ticket").click()
        expect(reply.locator(".ticket__error")).to_contain_text("valid email")
        self.assertFalse(SupportTicket.objects.exists())

    def test_feedback_is_stored_in_mongodb(self):
        self.page.goto(self.url("/"))
        self.open_assistant()
        reply = self.chat("How do I download a typeface?")
        reply.get_by_role("button", name="Yes").click()
        expect(reply.locator(".msg__rate")).to_contain_text("Thanks!")
        rating = documents.find("feedback")[0]
        self.assertEqual((rating["helpful"], rating["log_id"]), (True, str(documents.find("chat_logs")[0]["_id"])))

    def test_conversation_follows_you_between_pages(self):
        self.page.goto(self.url("/"))
        self.open_assistant()
        self.chat("Do I need an account?")
        self.page.goto(self.url("/faq/"))
        expect(self.page.get_by_role("dialog", name="Assistant")).to_be_visible()
        expect(self.page.locator(".msg--user")).to_have_text("Do I need an account?")

    def test_404_page_has_ask_the_assistant(self):
        self.expected_errors = 1
        response = self.page.goto(self.url("/this/address/is/wrong"))
        self.assertEqual(response.status, 404)
        self.page.locator("main").get_by_role("button", name="Ask the assistant").click()
        expect(self.page.locator(".msg--bot").last).to_contain_text("Page not found")

    def test_500_page_has_ask_the_assistant(self):
        response = views.server_error(RequestFactory().get("/"))
        html = response.content.decode()
        self.assertEqual(response.status_code, 500)
        self.assertIn('data-ask="What does error 500 mean?"', html)
        self.assertIn("data-assistant", html)

    def test_custom_500_is_served_when_a_view_crashes(self):
        with mock.patch("myapp.views.Faq.objects.all", side_effect=RuntimeError("boom")):
            client = Client(raise_request_exception=False)
            r = client.get("/faq/")
        self.assertEqual(r.status_code, 500)
        self.assertIn("Something broke on our side.", r.content.decode())

    def test_chat_api_errors(self):
        c = Client()
        self.assertEqual(c.post("/api/chat/", "not json", content_type="application/json").status_code, 400)
        self.assertEqual(c.post("/api/chat/", {"message": ""}, content_type="application/json").json()["code"], "400")
        r = c.post("/api/chat/", {"message": "hi"}, content_type="application/json", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(c.get("/api/chat/").status_code, 405)
        for _ in range(20):
            self.assertEqual(c.post("/api/chat/", {"message": "hello"}, content_type="application/json").status_code, 200)
        r = c.post("/api/chat/", {"message": "hello"}, content_type="application/json")
        self.assertEqual((r.status_code, r.json()["code"]), (429, "429"))

    # ------------------------------------------------------------ operations

    def test_health_page_and_json(self):
        self.page.goto(self.url("/health/"))
        expect(self.page.locator(".check")).to_have_count(4)
        expect(self.page.locator(".check--ok .check__name")).to_contain_text(["SQL database", "MongoDB (chat logs)"])
        data = Client().get("/health.json").json()
        names = {c["name"]: c["status"] for c in data["checks"]}
        self.assertEqual((names["SQL database"], names["MongoDB (chat logs)"], names["GitHub API"]), ("ok", "ok", "ok"))
        self.assertIn(data["status"], ("ok", "degraded"))

    def test_health_reports_a_database_outage_with_503(self):
        with mock.patch("myapp.views.connection.cursor", side_effect=RuntimeError("database is down")):
            r = Client().get("/health.json")
        self.assertEqual((r.status_code, r.json()["status"]), (503, "down"))

    def test_requests_are_logged_with_an_id(self):
        with self.assertLogs("myapp.requests", level="INFO") as logs:
            r = Client().get("/faq/", HTTP_X_REQUEST_ID="abc123")
        self.assertEqual(r["X-Request-ID"], "abc123")
        self.assertRegex(logs.output[0], r"abc123 GET /faq/ 200 [\d.]+ms user=- ip=[0-9a-f]{12}")

    def test_github_history_shows_on_typeface_pages(self):
        self.page.goto(self.url("/type/anybody/"))
        expect(self.page.locator("[data-history-value]")).to_contain_text("Update family")
        _, kwargs = self.github_get.call_args
        self.assertEqual(kwargs["params"]["path"], "ofl/anybody")
        self.assertEqual(kwargs["timeout"], (1.5, 2.5))  # hard time limit on the third-party call

    def test_github_falls_back_when_it_times_out(self):
        self.github_get.side_effect = requests.Timeout("too slow")
        self.page.goto(self.url("/type/syne/"))
        expect(self.page.locator("[data-history-value]")).to_contain_text("didn't answer in time")
        # with an earlier answer saved, that answer stands in
        cache.set("gh-stale:syne", {"status": "ok", "date": "2025-01-02", "message": "Saved", "url": "https://github.com"})
        self.page.reload()
        expect(self.page.locator("[data-history-value]")).to_contain_text("saved copy")

    def test_mobile_widget_and_404(self):
        ctx = self.new_context(logged_in=False, viewport={"width": 375, "height": 740}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        self.assertEqual(page.goto(self.url("/missing-on-phone")).status, 404)
        expect(page.locator("h1")).to_have_text("There's no page at this address.")
        page.locator(".assistant__launch").click()
        panel = page.get_by_role("dialog", name="Assistant")
        expect(panel).to_be_visible()
        page.wait_for_timeout(500)  # let the opening animation finish
        box = panel.bounding_box()
        self.assertEqual((round(box["x"]), round(box["width"])), (0, 375))  # full-width sheet
        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
        ctx.close()
