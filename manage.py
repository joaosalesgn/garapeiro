#!/usr/bin/env python
"""Ponto de entrada do Django para o sistema local da pastelaria."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django não está instalado. Siga as instruções do README.md para preparar o ambiente."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
