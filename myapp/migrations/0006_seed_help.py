from django.db import migrations

FAQS = [
    ("About", "What is Open Specimen?",
     "Open Specimen is an index of ten open-source typefaces. Each one is shown in its own font, and you can try "
     "its variable settings, like weight and width, live in the tester on its page."),
    ("Licensing", "Are the fonts free to use?",
     "Yes. Every typeface here is licensed under the SIL Open Font License, so you can use it for free in personal "
     "and commercial work, including logos, websites, apps and printed products."),
    ("Licensing", "What does the Open Font License allow?",
     "The SIL Open Font License lets you use, study, change and share the fonts, including in work you sell. "
     "The one thing it doesn't allow is selling the font files on their own."),
    ("Fonts", "How do I download a typeface?",
     "Open the typeface's page and click 'Open on Google Fonts'. Google Fonts lets you download the files or "
     "copy the code to use the font on a website."),
    ("Fonts", "What are variable axes?",
     "A variable font holds a whole range of styles in one file. Each axis is one setting you can slide: weight "
     "(wght) for thin to bold, width (wdth) for narrow to wide, optical size (opsz) for small text to headlines, "
     "and some fonts have special ones like Recursive's Casual and Mono."),
    ("Fonts", "How do I use the type tester?",
     "On any typeface page, type your own words into the tester, then drag the sliders to change the size and "
     "each variable axis. The waterfall and the character grid below follow your settings. Reset brings back "
     "the defaults."),
    ("Matcher", "How does the font matcher work?",
     "Describe what you're making, like 'a menu for a relaxed wine bar'. A small AI model that runs on our own "
     "server compares your words with what each typeface is good for, picks the closest one and sets its "
     "weight and width to match. It answers in a few milliseconds."),
    ("Account", "Do I need an account?",
     "No account is needed to browse the typefaces, read the FAQ or use this assistant. You need a free account "
     "to use the font matcher, keep your match history and submit a typeface."),
    ("Account", "How do I sign up and log in?",
     "Click 'Sign up' at the top of the page and enter your name, email, a username and a password. After that, "
     "log in with your username and password."),
    ("Account", "I forgot my password. What can I do?",
     "There's no automatic password reset yet. Ask the assistant to create a support ticket with the email you "
     "signed up with, and we'll reset it for you."),
    ("Submissions", "How do I suggest a typeface for the index?",
     "Log in, open 'Submit' in the top bar, and send the typeface name, the designer, a link to the font files "
     "and your email. We only list fonts under the Open Font License and reply within two weeks."),
    ("Privacy", "What data do you store about me?",
     "For accounts we store your name, email, username and a scrambled (hashed) password. Chat messages and "
     "ratings are stored in our MongoDB database to improve answers, and support tickets keep the email you "
     "give us so we can reply. We never sell your data."),
    ("Support", "How do I contact support?",
     "Ask this assistant your question. If it can't answer, it offers to create a support ticket: leave your "
     "email and we'll reply there."),
    ("Support", "Does the site work on phones?",
     "Yes. Every page adapts to phones and tablets, and on touch screens you can drag across the big word on "
     "the home page to change its letters."),
    ("Support", "Is the site down or slow?",
     "The health page at /health/ shows whether the database, the chat log store, the assistant and the GitHub "
     "connection are working right now."),
]

ERRORS = [
    ("400", "Bad request",
     "The request reached us, but something in it was malformed, like a broken form or invalid data.",
     "Reload the page and try again. If you were sending a form, check every field.",
     "When a form or an assistant message arrives in a shape we can't read."),
    ("401", "Not logged in",
     "This action needs an account, and you're not logged in.",
     "Log in with your username and password, or sign up first, then try again.",
     "When the font matcher is used without logging in."),
    ("403", "Forbidden",
     "We understood the request but won't carry it out. On this site that's usually an expired security token "
     "on a form.",
     "Reload the page so it gets a fresh token, then submit the form again.",
     "When a form's security (CSRF) check fails, or you open admin pages without permission."),
    ("404", "Page not found",
     "There's no page at this address. The link may have a typo, or the page was removed.",
     "Check the address, or go back to the index and find the page from there.",
     "For any address that doesn't exist, including unknown typefaces."),
    ("405", "Method not allowed",
     "The page exists but doesn't accept this kind of request, for example opening a form-only address directly.",
     "Use the page's buttons and forms instead of typing the address.",
     "When a POST-only address like /match/ is opened directly."),
    ("429", "Too many requests",
     "You've sent a lot of requests in a short time, so we're pausing them briefly to keep the site fast for "
     "everyone.",
     "Wait a minute, then try again.",
     "When the assistant gets more than 20 messages a minute, or the matcher 30, from one visitor."),
    ("500", "Server error",
     "Something broke on our side while building the page. It's not caused by anything you did.",
     "Reload in a minute. If it keeps happening, ask the assistant to open a support ticket.",
     "When an unexpected error happens in our code."),
    ("503", "Service unavailable",
     "A part of the site we depend on, like the database, isn't responding right now.",
     "Try again in a few minutes. The health page shows which part is down.",
     "When the health check finds the database unreachable."),
    ("OS-422", "Brief too short to match",
     "This site's own code: the font matcher needs a few words to work with, and the description was empty or "
     "under three characters.",
     "Describe what you're making and how it should feel, like 'a menu for a relaxed wine bar'.",
     "When the font matcher receives an empty or very short description."),
]

GF_PATHS = {
    "anybody": "ofl/anybody",
    "bricolage-grotesque": "ofl/bricolagegrotesque",
    "newsreader": "ofl/newsreader",
    "recursive": "ofl/recursive",
    "big-shoulders-display": "ofl/bigshouldersdisplay",
    "literata": "ofl/literata",
    "space-grotesk": "ofl/spacegrotesk",
    "syne": "ofl/syne",
    "instrument-serif": "ofl/instrumentserif",
    "unbounded": "ofl/unbounded",
}


def seed(apps, schema_editor):
    Faq = apps.get_model("myapp", "Faq")
    ErrorCode = apps.get_model("myapp", "ErrorCode")
    Typeface = apps.get_model("myapp", "Typeface")
    for i, (category, question, answer) in enumerate(FAQS):
        Faq.objects.update_or_create(question=question, defaults={"answer": answer, "category": category, "order": i})
    for i, (code, title, meaning, fix, when) in enumerate(ERRORS):
        ErrorCode.objects.update_or_create(code=code, defaults={
            "title": title, "meaning": meaning, "fix": fix, "when": when,
            "site_specific": not code.isdigit(), "order": i,
        })
    for slug, path in GF_PATHS.items():
        Typeface.objects.filter(slug=slug).update(gf_path=path)


def unseed(apps, schema_editor):
    apps.get_model("myapp", "Faq").objects.filter(question__in=[f[1] for f in FAQS]).delete()
    apps.get_model("myapp", "ErrorCode").objects.filter(code__in=[e[0] for e in ERRORS]).delete()


class Migration(migrations.Migration):
    dependencies = [("myapp", "0005_assistant")]
    operations = [migrations.RunPython(seed, unseed)]
