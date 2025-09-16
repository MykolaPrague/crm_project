from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from beauty.models import Service

DATA = {
    # група: [ {name, code?, price, duration}, ... ]
    # python manage.py seed_services команда для майбутнього апдейту/ініціалізації
    # --deactivate-missing для деактивації відсутніх
    "hair": [
        {"name": "Стрижка чоловіча", "code": "HAIR-M-CUT-30", "price": 300, "duration": 30},
        {"name": "Стрижка жіноча",   "code": "HAIR-W-CUT-45", "price": 500, "duration": 45},
        {"name": "Фарбування",       "code": "HAIR-COLOR-90", "price": 1200, "duration": 90},
        {"name": "Укладка",          "code": "HAIR-STYLE-30", "price": 350, "duration": 30},
    ],
    "nails": [
        {"name": "Манікюр класичний", "code": "NAILS-CLASS-60", "price": 400, "duration": 60},
        {"name": "Гель-лак",          "code": "NAILS-GEL-90",   "price": 700, "duration": 90},
        {"name": "Педикюр",           "code": "NAILS-PEDI-90",  "price": 800, "duration": 90},
    ],
    "cosmet": [
        {"name": "Чистка обличчя",    "code": "COS-CLEAN-60",   "price": 900, "duration": 60},
        {"name": "Пілінг",            "code": "COS-PEEL-45",    "price": 800, "duration": 45},
        {"name": "Маски доглядові",   "code": "COS-MASK-30",    "price": 500, "duration": 30},
    ],
    "barber": [
        {"name": "Стрижка барбер",    "code": "BARBER-CUT-40",  "price": 400, "duration": 40},
        {"name": "Гоління небезпечною бритвою", "code": "BARBER-SHAVE-30", "price": 350, "duration": 30},
        {"name": "Стрижка бороди",    "code": "BARBER-BEARD-20","price": 250, "duration": 20},
    ],
}

class Command(BaseCommand):
    help = "Створює/оновлює стандартні послуги за групами (hair/nails/cosmet/barber). Ідемпотентно."

    def add_arguments(self, parser):
        parser.add_argument("--group", choices=list(DATA.keys()), help="Обмежити однією групою")
        parser.add_argument("--deactivate-missing", action="store_true",
                            help="Деактивувати послуги, яких нема у словнику для цієї групи")

    @transaction.atomic
    def handle(self, *args, **opts):
        groups = [opts["group"]] if opts.get("group") else DATA.keys()
        total_created = 0
        total_updated = 0
        total_deactivated = 0

        for grp in groups:
            payloads = DATA[grp]
            codes_in_payload = set()

            for item in payloads:
                name = item["name"].strip()
                code = (item.get("code") or "").strip()
                price = Decimal(str(item.get("price", 0)))
                duration = int(item.get("duration") or 30)

                # ключ ідемпотентності: code якщо є, інакше name+group
                if code:
                    obj, created = Service.objects.update_or_create(
                        code=code,
                        defaults={
                            "name": name, "group": grp,
                            "base_price": price, "duration_min": duration, "is_active": True,
                        }
                    )
                    key = ("code", code)
                else:
                    obj, created = Service.objects.update_or_create(
                        name=name, group=grp,
                        defaults={
                            "code": "", "base_price": price, "duration_min": duration, "is_active": True,
                        }
                    )
                    key = ("name", name)

                codes_in_payload.add(key)
                if created:
                    total_created += 1
                    self.stdout.write(self.style.SUCCESS(f"[+] {grp}: {name}"))
                else:
                    total_updated += 1
                    self.stdout.write(self.style.WARNING(f"[~] {grp}: {name} (оновлено)"))

            if opts.get("deactivate-missing"):
                # деактивуємо ті, що не в списку
                qs = Service.objects.filter(group=grp, is_active=True)
                for s in qs:
                    key = ("code", s.code) if s.code else ("name", s.name)
                    if key not in codes_in_payload:
                        s.is_active = False
                        s.save(update_fields=["is_active"])
                        total_deactivated += 1
                        self.stdout.write(self.style.NOTICE(f"[-] деактивовано: {grp} / {s.name}"))

        self.stdout.write(self.style.SUCCESS(
            f"Готово: створено {total_created}, оновлено {total_updated}, деактивовано {total_deactivated}."
        ))
