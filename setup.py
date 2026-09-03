#!/usr/bin/env python3
"""
setup.py — Configuración de instalación para Teleprompter Pro.
"""

from setuptools import setup

setup(
    name="teleprompter-pro",
    version="1.0.0",
    author="Juan Salazar Flores",
    author_email="wachin@debian.org",
    description="Desktop teleprompter with remote control and voice sync",
    long_description=open("README.md", encoding="utf-8").read(),  # noqa: SIM115
    long_description_content_type="text/markdown",
    url="https://github.com/wachin/teleprompter",
    license="MIT",
    py_modules=[
        "main", "ui", "config", "remote_server", "speech_sync",
        "logging_setup", "paths", "project_service", "text_import",
        "templates_service", "main_window",
    ],
    python_requires=">=3.10",
    install_requires=[
        "PyQt6>=6.6.0",
        "flask>=3.0",
        "flask-socketio>=5.3.0",
        "qrcode[pil]>=7.4",
        "python-socketio[client]>=5.10.0",
        "vosk>=0.3.45",
        "sounddevice>=0.4.6",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pyinstaller>=6.0",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: X11 Applications",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Multimedia :: Presentation",
        "Topic :: Text Processing",
    ],
    entry_points={
        "console_scripts": [
            "teleprompter-pro=main:main",
        ],
    },
    package_data={
        "": [
            "scripts/*.txt",
            "templates/*.html",
            "resources/script_templates/*.txt",
            "resources/script_templates/*.json",
        ],
    },
    data_files=[
        ("share/teleprompter-pro/scripts", ["scripts/guion_actual.txt"]),
        ("share/teleprompter-pro/templates", ["templates/remote.html"]),
        ("share/teleprompter-pro/resources/script_templates",
         ["resources/script_templates/tutorial.txt",
          "resources/script_templates/tutorial.json",
          "resources/script_templates/presentation.txt",
          "resources/script_templates/presentation.json",
          "resources/script_templates/class.txt",
          "resources/script_templates/class.json",
          "resources/script_templates/news.txt",
          "resources/script_templates/news.json",
          "resources/script_templates/review.txt",
          "resources/script_templates/review.json",
          "resources/script_templates/ad.txt",
          "resources/script_templates/ad.json"]),
    ],
)
