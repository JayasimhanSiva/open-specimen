from django.db import migrations

# Extra jobs each typeface suits, so the matcher and assistant cover more kinds of businesses.
MORE_USES = {
    "nunito": "yoga studios, wellness apps, children's picture books, nurseries, pet care, dental clinics",
    "lora": "spas, florists, bookshops, yoga retreats, counselling and therapy practices",
    "dm-sans": "wellness apps, meditation apps, health startups, real estate listings, online courses",
    "cormorant-garamond": "spas, beauty salons, boutique hotels, florists, interior design studios",
    "fraunces": "children's books, ice cream shops, farmers markets, craft breweries, toy shops",
    "rubik": "children's games, kids apps, birthday parties, toy shops, schools",
    "playfair-display": "real estate, interior design, architecture portfolios, hotels, photography portfolios",
    "work-sans": "photography portfolios, architecture studios, nonprofits, conferences",
    "montserrat": "gyms, sports clubs, construction companies, logistics, travel agencies",
    "source-sans-3": "schools, universities, hospitals, insurance, nonprofits, charities",
    "merriweather": "churches, nonprofits, local news, community groups, history societies",
    "outfit": "logos, travel apps, food delivery apps, ecommerce stores",
    "plus-jakarta-sans": "ecommerce stores, travel booking, real estate apps, SaaS marketing sites",
    "archivo": "automotive brands, sports results, transport, logistics dashboards",
    "bebas-neue": "barbershops, gyms, boxing clubs, streetwear, festival lineups",
    "caveat": "florists, bakeries' chalkboards, wedding planners, scrapbooks, teachers' notes",
    "atkinson-hyperlegible": "elderly care, pharmacies, insurance forms, government services",
    "lexend": "schools, learning platforms, e-learning courses, kids reading apps",
    "inter": "ecommerce checkouts, admin panels, banking apps, productivity tools",
    "ibm-plex-sans": "insurance, banking, consulting, cybersecurity, AI products",
    "space-grotesk": "AI startups, robotics, web3 projects, design agencies",
    "unbounded": "nightclubs, DJ events, streetwear drops, game studios",
    "syne": "fashion brands, architecture biennales, design festivals, record labels",
    "instrument-serif": "cocktail bars, art galleries, magazines, architecture studios",
    "bodoni-moda": "beauty brands, cosmetics, fashion houses, luxury real estate",
    "eb-garamond": "universities, law firms, publishing houses, wine labels",
}


REPLACE_USES = {
    "space-mono": "retro computing zines, sci-fi book covers, code-themed editorial captions, tech portfolios",
}


def seed(apps, schema_editor):
    Typeface = apps.get_model("myapp", "Typeface")
    for slug, uses in REPLACE_USES.items():
        Typeface.objects.filter(slug=slug).update(uses=uses)
    for slug, extra in MORE_USES.items():
        face = Typeface.objects.filter(slug=slug).first()
        if face and extra not in face.uses:
            face.uses = f"{face.uses}, {extra}"
            face.save(update_fields=["uses"])


class Migration(migrations.Migration):
    dependencies = [("myapp", "0011_tune_advice_data")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
