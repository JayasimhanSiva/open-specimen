from django.db import migrations


def ax(tag, name, lo, hi, default):
    return {"tag": tag, "name": name, "min": lo, "max": hi, "default": default}


WGHT = lambda lo, hi, d=400: ax("wght", "Weight", lo, hi, d)  # noqa: E731

FACES = [
    dict(name="Anybody", slug="anybody", designer="Etcetera Type Co", year=2021,
         classification="display", gf_query="Anybody:wdth,wght@50..150,100..900",
         axes=[ax("wdth", "Width", 50, 150, 100), WGHT(100, 900)],
         sample="Stretch it to a hairline or squash it into a brick.",
         description="A grotesque with a width axis so wide it runs from ultra-condensed to ultra-expanded in one file. Built for headlines that have to fit a space exactly."),
    dict(name="Bricolage Grotesque", slug="bricolage-grotesque", designer="Mathieu Triay", year=2023,
         classification="sans", gf_query="Bricolage Grotesque:opsz,wdth,wght@12..96,75..100,200..800",
         axes=[ax("opsz", "Optical size", 12, 96, 14), ax("wdth", "Width", 75, 100, 100), WGHT(200, 800)],
         sample="Ink traps open up as the size goes down.",
         description="French grotesque roots with a quirky streak. The optical size axis swaps in deeper ink traps and looser spacing at text sizes, and tightens everything for display."),
    dict(name="Newsreader", slug="newsreader", designer="Production Type", year=2020,
         classification="serif", gf_query="Newsreader:opsz,wght@6..72,200..800",
         axes=[ax("opsz", "Optical size", 6, 72, 16), WGHT(200, 800)],
         sample="Long reads, short headlines, and footnotes in one family.",
         description="Drawn for continuous reading on screens. Optical sizes cover captions at six points through to headlines at seventy-two without changing the family's voice."),
    dict(name="Recursive", slug="recursive", designer="Arrow Type", year=2019,
         classification="mono", gf_query="Recursive:slnt,wght,CASL,CRSV,MONO@-15..0,300..1000,0..1,0..1,0..1",
         axes=[ax("MONO", "Monospace", 0, 1, 1), ax("CASL", "Casual", 0, 1, 0), WGHT(300, 1000), ax("slnt", "Slant", -15, 0, 0)],
         sample="const brush = { casual: true, mono: 1 };",
         description="One family that moves from a proportional sans to a monospace, and from linear to a brush-drawn casual style. Useful for code, interfaces and expressive display alike."),
    dict(name="Big Shoulders Display", slug="big-shoulders-display", designer="Patric King", year=2019,
         classification="display", gf_query="Big Shoulders Display:wght@100..900",
         axes=[WGHT(100, 900, 700)],
         sample="CONDENSED, CONFIDENT, BUILT FOR SIGNAGE",
         description="A condensed display face drawn for the City of Chicago's design programme, with the city's industrial lettering and sign painting in its bones."),
    dict(name="Literata", slug="literata", designer="TypeTogether", year=2020,
         classification="serif", gf_query="Literata:opsz,wght@7..72,200..900",
         axes=[ax("opsz", "Optical size", 7, 72, 12), WGHT(200, 900)],
         sample="Chapter one began, as they often do, with weather.",
         description="Commissioned as the reading face for Google Play Books. Sturdy, warm, and comfortable on low-resolution screens across hundreds of pages."),
    dict(name="Space Grotesk", slug="space-grotesk", designer="Florian Karsten", year=2018,
         classification="sans", gf_query="Space Grotesk:wght@300..700",
         axes=[WGHT(300, 700)],
         sample="Derived from a monospace, it kept the odd details.",
         description="A proportional sans adapted from Colophon's Space Mono. The quirks of the monospace survive in the a, the G and the numerals."),
    dict(name="Syne", slug="syne", designer="Bonjour Monde", year=2017,
         classification="display", gf_query="Syne:wght@400..800",
         axes=[WGHT(400, 800)],
         sample="Wide at the bottom of the axis, heavy at the top.",
         description="Made for the identity of an art centre, Syne grows wider and stranger as it gets heavier. The extra-bold is closer to a logotype than a text face."),
    dict(name="Instrument Serif", slug="instrument-serif", designer="Instrument", year=2023,
         classification="serif", gf_query="Instrument Serif",
         axes=[],
         sample="A condensed serif for headlines with some nerve.",
         description="A tightly spaced, slightly condensed display serif from the Instrument studio. A single regular weight, meant to be set large."),
    dict(name="Unbounded", slug="unbounded", designer="NaN", year=2022,
         classification="display", gf_query="Unbounded:wght@200..900",
         axes=[WGHT(200, 900)],
         sample="Round, wide, and happiest at enormous sizes.",
         description="An extended, rounded display family with a long weight range. At the light end it reads technical; at the black end it turns into pure shape."),
]


def seed(apps, schema_editor):
    Typeface = apps.get_model("myapp", "Typeface")
    for i, f in enumerate(FACES):
        Typeface.objects.update_or_create(slug=f["slug"], defaults={**f, "order": i})


def unseed(apps, schema_editor):
    apps.get_model("myapp", "Typeface").objects.filter(slug__in=[f["slug"] for f in FACES]).delete()


class Migration(migrations.Migration):
    dependencies = [("myapp", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
