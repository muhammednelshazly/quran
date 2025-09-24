from django.core.management.base import BaseCommand
from apps.accounts.models import Halaqa

DEFAULTS = [
    "حلقة البقرة – الشيخ عبد الله الحربي",
    "حلقة النساء – الشيخ محمد القحطاني",
    "حلقة التوبة – الشيخ خالد الغامدي",
    "حلقة النحل – الشيخ فهد العتيبي",
    "حلقة الإسراء – الشيخ محمود الأنصاري",
    "حلقة طه – الشيخ علي الزهراني",
    "حلقة النمل – الشيخ ياسر البكري",
    "حلقة العنكبوت – الشيخ عبد الرحمن الزهراني",
    "حلقة لقمان – الشيخ إبراهيم السبيعي",
    "حلقة فاطر – الشيخ عمر الحربي",
]

class Command(BaseCommand):
    help = "Seed default Halaqas (10 base records)"

    def handle(self, *args, **options):
        created = 0
        for name in DEFAULTS:
            _, was_created = Halaqa.objects.get_or_create(name=name)
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Done. Created {created} halaqa(s)."))
