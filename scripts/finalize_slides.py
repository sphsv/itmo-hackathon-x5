"""Update Ivan's editable PPTX without rebuilding his layout. Export PDF in Keynote."""
from __future__ import annotations
import json
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def main():
    metrics = json.loads((ROOT / "ai/out/eval.json").read_text())["summary"]
    rate = lambda system: f"{metrics['systems'][system]['observed_completion_rate_itt'] * 100:.1f}%".replace(".", ",")
    changes = {
        3: {"RuStore, 5 702: карта первой. Экономия по чеку. Ростомер после покупки":
            "RuStore: карта первой, экономия по чеку. Счётчики ресерча не переаудированы"},
        4: {"Семейная связка и кассовая печать замоканы в PoC":
            "Чеки работают. Связка и печать замоканы"},
        5: {"AI формулирует, правила считают": "Персонализатор выбирает, правила считают",
            "Текущий PoC работает без внешнего LLM API": "Рабочий локальный стенд без LLM API и реальных начислений X5",
            "СЕЙЧАС В POC": "СЕЙЧАС В КОДЕ", "Rule-based baseline": "Недельная политика",
            "восстанавливает заложенный синтетический тип": "использует 8 недель истории до назначения",
            "выбирает механику": "выбирает категории и достижимый порог",
            "формирует challenge JSON": "объясняет цель; есть fallback и отказ",
            "управляет antifraud и начислением": "обрабатывает дубли, возвраты и лимиты",
            "96,7% валидируют синтетическую классификацию, но не полезность или uplift":
            "Цель проверяется по чеку. Нет обученной нейросети; человеческая полезность ещё не измерена"},
        6: {"Что проверяет PoC": "Что проверяет рабочая версия",
            "Контур воспроизводится. Поведение покупателей ещё не измерено":
            "Временной replay на синтетике; это не измерение изменения поведения",
            "2 000": "510", "профилей всех сегментов": "целевых семей",
            "≈510 целевой профиль": "из 2 000 синтетических профилей",
            "41 191": "2 040", "чек": "эпизодов временного replay",
            "330 181": "25 тестов", "товарная позиция": "API, дубли, возвраты, лимиты",
            "96,7%": rate("personalized"), "против 36,7% baseline": f"против {rate('static')} static",
            "на 30 синтетических профилях": "выполнено на следующих чеках",
            "constraints pass rate": "проверки безопасности",
            "на том же синтетическом наборе": "на 2 040 временных эпизодах",
            "данные, правила и воспроизводимость": "правила и совместимость с корзиной",
            "спрос, полезность и изменение покупок": "спрос и uplift; review ещё впереди"},
        9: {"Команда и ближайший результат": "Команда и итоговая версия",
            "PRODUCT MANAGER": "PRODUCT MANAGER · активное",
            "ML ENGINEER": "ML ENGINEER · активное",
            "Один сквозной сценарий должен связать документы, код и демонстрацию":
            "Сквозной сценарий проверен в коде, API и браузере; человеческая оценка — следующий шаг",
            "Чековое событие, дубль, отмена, данные пилота": "Данные, target-когорта, качество, сценарии",
            "Eval, соответствие механики, antifraud-кейсы": "Персонализатор, baseline, eval, интеграция",
            "P0: подходящий чек закрывает цель, повтор не начисляет дважды, отмена возвращает состояние":
            "Готово: чек → цель → награда; повтор без дубля, возврат с пересчётом. Далее: human review и пилот",
            "AI ускорил исследование, синтез источников, документацию и сборку PoC. Продуктовые решения и границы доказательств оставались за командой":
            "Все трое активно участвовали; точные трудозатраты не измерялись. AI помог с исследованием, кодом, тестами и финальной интеграцией"},
    }
    source = ROOT / "output/presentation/PRESENTATION_FINAL_DRAFT.pptx"
    target = ROOT / "output/presentation/PRESENTATION_FINAL.pptx"
    with ZipFile(source) as old, ZipFile(target, "w") as new:
        for info in old.infolist():
            data = old.read(info.filename)
            if info.filename == "ppt/media/image.png":
                data = (ROOT / "output/demo/06_receipt.png").read_bytes()
            for index, replacements in changes.items():
                if info.filename == f"ppt/slides/slide{index}.xml":
                    text = data.decode()
                    for before, after in replacements.items():
                        needle = f"<a:t>{escape(before)}</a:t>"
                        if needle not in text:
                            raise ValueError(f"Missing text in slide {index}: {before}")
                        text = text.replace(needle, f"<a:t>{escape(after)}</a:t>")
                    data = text.encode()
            new.writestr(info, data)
    print(target)


if __name__ == "__main__":
    main()
