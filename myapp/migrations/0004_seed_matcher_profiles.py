from django.db import migrations

# What each typeface is good for, and how it feels. The font matcher compares a
# visitor's description against these phrases.
PROFILES = {
    "anybody": (
        "festival posters, gig and concert flyers, sports branding, event identities, "
        "headlines that must fit an exact space, magazine covers, streetwear",
        "loud, energetic, flexible, brutal, playful, modern",
    ),
    "bricolage-grotesque": (
        "café and bakery menus, food and drink packaging, startup brands, app interfaces, "
        "websites, restaurant signage, product labels",
        "friendly, quirky, warm, approachable, contemporary, characterful",
    ),
    "newsreader": (
        "newspapers, magazines, long articles, blogs, essays, reports, journalism, newsletters",
        "calm, trustworthy, editorial, intelligent, serious, classic",
    ),
    "recursive": (
        "code editors, programming, terminals, developer tools, documentation, dashboards, "
        "data tables, handwritten-style notes, casual comics",
        "technical, nerdy, versatile, precise, casual, friendly",
    ),
    "big-shoulders-display": (
        "street signage, wayfinding, sports teams, transport, construction, beer labels, "
        "factory and industrial branding, bold headlines",
        "tall, condensed, industrial, strong, urban, confident",
    ),
    "literata": (
        "books, novels, ebooks, poetry, literature, academic writing, libraries, long-form reading",
        "bookish, gentle, literary, comfortable, timeless, warm",
    ),
    "space-grotesk": (
        "technology products, science, space, fintech, software interfaces, portfolios, "
        "startups, conference branding",
        "modern, precise, futuristic, clean, neutral, slightly quirky",
    ),
    "syne": (
        "art galleries, museums, exhibitions, fashion lookbooks, cultural festivals, "
        "creative studios, experimental design",
        "avant-garde, artistic, expressive, strange, wide, bold",
    ),
    "instrument-serif": (
        "luxury brands, fashion, beauty, weddings, invitations, wine bars, fine dining, "
        "perfume, jewellery, elegant editorial headlines",
        "elegant, refined, sophisticated, romantic, chic, delicate",
    ),
    "unbounded": (
        "gaming, esports, playful tech brands, kids and toys, music releases, bold logos, crypto",
        "round, wide, punchy, fun, futuristic, friendly",
    ),
}


def seed(apps, schema_editor):
    Typeface = apps.get_model("myapp", "Typeface")
    for slug, (uses, mood) in PROFILES.items():
        Typeface.objects.filter(slug=slug).update(uses=uses, mood=mood)


def unseed(apps, schema_editor):
    apps.get_model("myapp", "Typeface").objects.update(uses="", mood="")


class Migration(migrations.Migration):
    dependencies = [("myapp", "0003_matcher")]
    operations = [migrations.RunPython(seed, unseed)]
