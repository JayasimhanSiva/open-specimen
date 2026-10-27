from django.db import migrations

# Typography advice the assistant can answer from, shown on the FAQ page under "Typography".
FAQS = [
    ("What font size should body text be?",
     "Use 16 to 18 px for body text on websites, and never below 16 px on phones. Make headings step up by a "
     "steady ratio, such as 1.25 or 1.333, so the sizes feel related: 16, 20, 25, 31 px and so on.",
     ["How big should my text be?", "What is a good font size for a website?", "Font size for paragraphs"]),
    ("What line height should I use?",
     "Body text reads best with a line height of about 1.4 to 1.6, written in CSS as line-height: 1.5. "
     "Headings need less, around 1.05 to 1.2, so the lines of a long title stay together.",
     ["What is good line spacing?", "My lines of text feel cramped", "Leading for paragraphs"]),
    ("How long should a line of text be?",
     "Aim for 45 to 75 characters per line, about 66 is ideal. In CSS, set max-width: 65ch on paragraphs so "
     "lines don't stretch across wide screens.",
     ["My paragraphs are too wide", "What is a good line length?", "Measure for body text"]),
    ("How many fonts should a website use?",
     "One or two families is usually enough: one for headings and one for body text, or a single family in "
     "a few weights. More than three families tends to look messy and slows the page down.",
     ["Is it okay to use many fonts?", "How many typefaces should I use?", "Too many fonts on my site"]),
    ("How do I pair two fonts?",
     "Pair fonts that contrast in style but share proportions, like a characterful serif for headings with a "
     "calm sans for body text. Ask me 'what goes with Fraunces?' or any typeface in the index and I'll "
     "suggest a partner.",
     ["What fonts go well together?", "Font pairing tips", "Which heading and body fonts match?"]),
    ("How do I make my text more readable and accessible?",
     "Keep body text at 16 px or more, line height near 1.5 and lines under 75 characters. Use a contrast "
     "ratio of at least 4.5:1 between text and background, avoid long passages in all caps or italics, and "
     "consider typefaces built for legibility like Atkinson Hyperlegible or Lexend.",
     ["My text is hard to read", "How do I improve readability?", "Accessible typography", "Font for dyslexia"]),
    ("How do I make web fonts load fast?",
     "Load only the families and weights you use, prefer one variable font over many static files, add "
     "font-display: swap so text shows immediately, and preconnect to the font host. Self-hosting WOFF2 "
     "files is fastest of all.",
     ["My fonts load slowly", "Font loading performance", "Why does my text flash?"]),
    ("What's the difference between serif and sans-serif?",
     "Serif typefaces have small strokes at the ends of letters and often feel classic, literary or "
     "trustworthy. Sans-serifs drop those strokes and feel cleaner and more modern. Both work for body text "
     "on today's screens; choose by the tone you want.",
     ["Serif or sans serif?", "Should I use a serif font?", "What is a sans serif?"]),
    ("Which font is best for code?",
     "Use a monospace: JetBrains Mono and Fira Code are made for code and have ligatures for operators like "
     "=> and !=. Recursive can switch between monospace and proportional in one file.",
     ["Font for programming", "Best monospace font", "Font for my code editor"]),
    ("Should I use all caps or letter-spacing?",
     "All caps works for short labels and buttons, not for paragraphs. When you use caps, add a little "
     "letter-spacing, about 0.05em, because capitals sit too tight by default. Don't add letter-spacing to "
     "lowercase body text.",
     ["Uppercase headings", "Letter spacing tips", "Tracking for capitals"]),
    ("What font sizes work on mobile?",
     "Keep body text at 16 px or larger so iPhones don't zoom into form fields, and scale headings down "
     "on small screens with CSS clamp(), for example font-size: clamp(2rem, 6vw, 4rem).",
     ["Responsive font sizes", "Text too small on phone", "Font size for mobile"]),
    ("Can you review my website's fonts?",
     "Yes. Paste your site's address into the assistant, like https://example.com, and ask for advice. I'll "
     "open the page, check which fonts, sizes and line heights it uses, and tell you what to change, where "
     "and why, with CSS you can copy.",
     ["Check my website", "Audit my site's typography", "Suggest fonts for my website"]),
]


def seed(apps, schema_editor):
    Faq = apps.get_model("myapp", "Faq")
    start = Faq.objects.count()
    for i, (question, answer, phrasings) in enumerate(FAQS):
        Faq.objects.update_or_create(question=question, defaults={
            "answer": answer, "category": "Typography", "order": start + i, "phrasings": "\n".join(phrasings)})


def unseed(apps, schema_editor):
    apps.get_model("myapp", "Faq").objects.filter(question__in=[f[0] for f in FAQS]).delete()


class Migration(migrations.Migration):
    dependencies = [("myapp", "0009_more_typefaces")]
    operations = [migrations.RunPython(seed, unseed)]
