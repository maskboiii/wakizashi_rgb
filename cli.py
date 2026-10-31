"""Command line interface for the Wakizashi V2 / AULA F87 Pro RGB control."""

import argparse
import sys
import time

import kb


def parse_color(text):
    value = text.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("Цвет должен быть в формате RRGGBB (например ff0000)")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Управление подсветкой Wakizashi V2 / AULA F87 Pro")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--detect", action="store_true", help="вывести ID модели")
    action.add_argument("--color", metavar="RRGGBB", help="сплошной цвет с keepalive до Ctrl+C")
    action.add_argument("--off", action="store_true", help="выключить подсветку")

    args = parser.parse_args(argv)

    try:
        keyboard = kb.Keyboard()
    except kb.KbError as exc:
        print(f"[ошибка] {exc}", file=sys.stderr)
        return 1

    try:
        if args.detect:
            model = keyboard.get_model_id()
            if model is None:
                print("[ошибка] не удалось получить Model ID (ответ слишком короткий)", file=sys.stderr)
                return 1
            name = kb.MODEL_NAMES.get(model, "неизвестная модель")
            print(f"Model ID: 0x{model:02X} ({name})")
            return 0

        if args.off:
            keyboard.set_off()
            print("Подсветка выключена.")
            return 0

        try:
            r, g, b = parse_color(args.color)
        except ValueError as exc:
            print(f"[ошибка] {exc}", file=sys.stderr)
            return 1

        print(f"Цвет #{args.color.strip().lstrip('#').upper()}, Ctrl+C для остановки...")
        try:
            while True:
                keyboard.set_solid_color(r, g, b)
                time.sleep(kb.KEEPALIVE_S)
        except KeyboardInterrupt:
            print("\nОстановлено. Клавиатура вернётся к заводскому режиму.")
        return 0
    except (kb.KbError, OSError, ValueError) as exc:
        print(f"[ошибка] {exc}", file=sys.stderr)
        return 1
    finally:
        keyboard.close()


if __name__ == "__main__":
    sys.exit(main())
