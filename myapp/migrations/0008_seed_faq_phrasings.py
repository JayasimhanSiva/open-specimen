from django.db import migrations

PHRASINGS = {
    "What is Open Specimen?": ["What is this website?", "What is this site for?", "What can I do here?"],
    "Are the fonts free to use?": ["How much does it cost?", "Do I have to pay?", "Can I use the fonts commercially?"],
    "What does the Open Font License allow?": ["Can I sell something I made with these fonts?", "Can I modify a font?",
                                               "What is the OFL?"],
    "How do I download a typeface?": ["Where can I get the font files?", "How do I install a font?",
                                      "How do I use a font on my website?"],
    "What are variable axes?": ["What is a variable font?", "What do wght and wdth mean?", "What is optical size?"],
    "How do I use the type tester?": ["How do the sliders work?", "How do I preview my own text?",
                                      "How do I change the font size?"],
    "How does the font matcher work?": ["How does the AI pick a font?", "How does the font picker work?",
                                        "Can you recommend a font for my project?"],
    "Do I need an account?": ["Do I have to register?", "Can I use the site without logging in?"],
    "How do I sign up and log in?": ["How do I create an account?", "How do I register?", "Where do I log in?"],
    "I forgot my password. What can I do?": ["How do I reset my password?", "I can't log in"],
    "How do I suggest a typeface for the index?": ["How can I add a font?", "Can you add a typeface?",
                                                   "Is a font missing from the index?"],
    "What data do you store about me?": ["Is my data safe?", "Do you store my chats?", "Privacy policy"],
    "How do I contact support?": ["How do I talk to a person?", "How do I report a bug?", "I need help"],
    "Does the site work on phones?": ["Is there a mobile app?", "Does it work on a tablet?"],
    "Is the site down or slow?": ["Is something broken?", "Why isn't the site loading?", "Status page"],
}


def seed(apps, schema_editor):
    Faq = apps.get_model("myapp", "Faq")
    for question, lines in PHRASINGS.items():
        Faq.objects.filter(question=question).update(phrasings="\n".join(lines))


def unseed(apps, schema_editor):
    apps.get_model("myapp", "Faq").objects.update(phrasings="")


class Migration(migrations.Migration):
    dependencies = [("myapp", "0007_faq_phrasings")]
    operations = [migrations.RunPython(seed, unseed)]
