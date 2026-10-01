#!/usr/bin/env python3
"""
setup.py — Installation configuration for Teleprompter Pro.
"""

from setuptools import setup

from app_info import APP_VERSION, AUTHORS, LICENSE_NAME, REPOSITORY_URL

setup(
    name="teleprompter-pro",
    version=APP_VERSION,
    author=", ".join(name for name, _email in AUTHORS),
    author_email=AUTHORS[0][1],
    description="Desktop teleprompter with camera, recording and remote control",
    long_description=open("README.md", encoding="utf-8").read(),  # noqa: SIM115
    long_description_content_type="text/markdown",
    url=REPOSITORY_URL,
    license=LICENSE_NAME,
    py_modules=[
        "about_dialog", "app_info", "audio_service", "branding_model",
        "branding_view", "camera_preview", "camera_service", "config",
        "edit_model", "editor_view", "export_profiles", "export_view",
        "ffmpeg_tools", "logging_setup", "main", "main_window",
        "overlay_model", "paths", "project_service", "recording_service",
        "remote_server", "render_pipeline", "review_view", "scroll_engine",
        "speech_sync", "subtitle_model", "subtitle_service", "subtitle_view",
        "teleprompter_overlay", "templates_service", "text_import", "ui",
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
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: POSIX :: Linux",
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
            "resources/icons/*.svg",
            "resources/script_templates/*.txt",
            "resources/script_templates/*.json",
            "translations/*.qm",
        ],
    },
    data_files=[
        ("share/teleprompter-pro/scripts", ["scripts/guion_actual.txt"]),
        ("share/teleprompter-pro/templates", ["templates/remote.html"]),
        ("share/teleprompter-pro/resources/icons",
         ["resources/icons/teleprompter-pro.svg"]),
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
