from django.db import migrations

# Tuning after stress-testing the assistant with real questions.
USES = {
    "jetbrains-mono": "code editors, terminals, developer documentation, code samples, technical slides",
    "lora": "blogs, personal blogs, essays, poetry, novels, wedding websites, personal portfolios",
}
PHRASINGS = {
    "What line height should I use?": ["Line height for paragraphs", "Line spacing for body text",
                                        "How much space between lines?"],
    "Can you review my website's fonts?": ["Check my website", "Audit my site's typography",
                                           "Look at my site and tell me what to change"],
}


def seed(apps, schema_editor):
    Typeface = apps.get_model("myapp", "Typeface")
    Faq = apps.get_model("myapp", "Faq")
    for slug, uses in USES.items():
        Typeface.objects.filter(slug=slug).update(uses=uses)
    for question, lines in PHRASINGS.items():
        faq = Faq.objects.filter(question=question).first()
        if faq:
            existing = [p for p in faq.phrasings.splitlines() if p.strip() and p != "Suggest fonts for my website"]
            faq.phrasings = "\n".join(dict.fromkeys(existing + lines))
            faq.save(update_fields=["phrasings"])


class Migration(migrations.Migration):
    dependencies = [("myapp", "0010_typography_faqs")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
