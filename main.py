#! /usr/bin/env python3

"""
Entry point for Postkutsche.
"""

import os
import sys
import zlib
import shutil
import asyncio
import logging
import subprocess
from os import listdir
from os.path import isfile, isdir, join, exists

import onlinebrief24
from guy import Guy
from guy import http
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pk_toml_config import PkTomlConfig

import models

if sys.platform.startswith("linux"):
    import notify2

CONFIG = PkTomlConfig().load_config()
ENV = Environment(
    loader=FileSystemLoader("templates"), autoescape=select_autoescape(["html", "xml"]),
)


class Main(Guy):
    def __init__(self):
        """\
        Initializes state for client.
        """
        if sys.platform.startswith("linux"):
            notify2.init("Postkutsche")
        elif sys.platform.startswith("darwin"):
            # TODO: Add the macos thing
            pass
        elif sys.platform.startswith("win"):
            # TODO: Add the windows thing
            pass
        super().__init__()

    def _render(self, path):
        """\
        Renders template for main page.
        """
        template = ENV.get_template("main.html")
        return template.render(pdf_files=[])

    def open_upload_folder(self):
        upload_folder = CONFIG["paths"].get("upload_folder", None)
        if isdir(upload_folder):
            if sys.platform.startswith("darwin"):
                subprocess.call(["open", upload_folder])
            elif sys.platform.startswith("win"):
                subprocess.call(["explorer", upload_folder])
            else:
                subprocess.call(["xdg-open", upload_folder])

    def send_files(self):
        """\
        Send PDF from upload_folder.
        """
        upload_folder = CONFIG["paths"].get("upload_folder", None)
        archive_folder = CONFIG["paths"].get("archive_folder", None)
        if not archive_folder:
            archive_folder = join(upload_folder, "archive")
            os.makedirs(archive_folder, exist_ok=True)
        username = CONFIG["onlinebrief24"].get("username", None)
        password = CONFIG["onlinebrief24"].get("password", None)
        if not username or not password:
            send_system_notification(
                "Logindaten werden benötigt",
                "Bitte unter 'Einstellungen' Benutzername und Passwort eintragen!",
                urgency="high"
            )
            return
        pdf_files = get_upload_files(upload_folder)
        if len(pdf_files) <= 0:
            send_system_notification(
                "Bitte Briefe hinzufügen",
                "Dazu können PDF in das Upload-Verzeichnis gespeichert werden.",
                urgency="high"
            )
            return
        # sending files with onlinebrief24.de
        with onlinebrief24.Client(username, password) as c:
            for pdf in pdf_files:
                logging.debug("sending: {}".format(pdf.filename))
                c.upload(join(upload_folder, pdf.filename),
                            duplex=pdf.duplex,
                            color=pdf.color,
                            envelope=pdf.envelope,
                            distribution=pdf.distribution,
                            registered=pdf.registered,
                            payment_slip=pdf.payment_slip)
                shutil.move(
                    join(upload_folder, pdf.filename), join(archive_folder, pdf.filename)
                )
                models.Archive.create(
                    adler32=pdf.adler32,
                    filename=pdf.filename,
                    color=pdf.color,
                    duplex=pdf.duplex,
                    envelope=pdf.envelope,
                    distribution=pdf.distribution,
                    registered=pdf.registered,
                    payment_slip=pdf.payment_slip,
                )
                # Delete entry after it was moved to the archive
                pdf.delete().execute()

        send_system_notification(
            "Briefe hochgeladen",
            "{} Briefe wurden zu onlinebrief24 hochgeladen und werden jetzt verarbeitet.".format(
                len(pdf_files))
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.emit("reload_pdf_files"))

    def openPdfSettings(self, pdf_hash, filename):
        """\
        Opens PDF settings in modal overlay.
        """
        return PdfSettings(pdf_hash=pdf_hash, filename=filename)

    def open_archive_file(self, filename):
        """\
        Opens an archived file via xdg-open (linux), explorer (win) or open (macos).
        """
        archive_folder = CONFIG["paths"].get("archive_folder", None)
        archive_file = join(archive_folder, filename)
        if exists(archive_file):
            if sys.platform.startswith("darwin"):
                subprocess.call(["open", archive_file])
            elif sys.platform.startswith("win"):
                subprocess.call(["explorer", archive_file])
            else:
                subprocess.call(["xdg-open", archive_file])
        else:
            logging.critical("'%s' seems to be not existing!", archive_file)


class Archive(Guy):
    def _render(self, path):
        """\
        Renders template for archive page.
        """
        template = ENV.get_template("archive.html")
        return template.render(pdf_files=[])


class Settings(Guy):
    def _render(self, path):
        """\
        Renders template for settings page.
        """
        template = ENV.get_template("settings.html")
        context = {
            "username": CONFIG["onlinebrief24"].get("username", ""),
            "password": CONFIG["onlinebrief24"].get("password", ""),
            "upload_folder": CONFIG["paths"].get("upload_folder", ""),
            "archive_folder": CONFIG["paths"].get("archive_folder", ""),
        }
        return template.render(**context)


class PdfSettings(Guy):
    def __init__(self, *args, **kwargs):
        self.pdf_hash = kwargs["pdf_hash"]
        self.pdf_filename = kwargs["filename"]
        super().__init__(*args, **kwargs)

    def _render(self, path, includeGuyJs=False):
        template = ENV.get_template("_pdf_settings.html")
        pdf = (
            models.PdfFile.select()
            .where(
                models.PdfFile.adler32 == self.pdf_hash,
                models.PdfFile.filename == self.pdf_filename,
            )
            .limit(1)
            .execute()[0]
        )
        logging.debug(
            "PDF file::: filename: {}, color: {}, duplex: {}, envelope: {}, distri: {}, registered: {}, payment_slip: {}".format(
                pdf.filename,
                pdf.color,
                pdf.duplex,
                pdf.envelope,
                pdf.distribution,
                pdf.registered,
                pdf.payment_slip,
            )
        )
        return template.render(pdf=pdf)

def send_system_notification(subject, text, urgency=None, ttl=None):
    """\
    Sends notification with the OS native framework.
    """
    if sys.platform.startswith("linux"):
        notification = notify2.Notification(
            subject,
            text,
            "notification-message-im",
        )
        if urgency:
            notification.set_urgency(notify2.URGENCY_CRITICAL)
        notification.show()

def get_upload_files(upload_folder):
    """\
    Fetches PDF file list from upload folder.
    """
    pdf_files = [
        (f, get_file_hash(join(upload_folder, f)))
        for f in listdir(upload_folder)
        if isfile(join(upload_folder, f)) and f.endswith(".pdf")
    ]

    db_files = []
    for pdf in pdf_files:
        db_file, created = models.PdfFile.get_or_create(adler32=pdf[1], filename=pdf[0])
        db_files.append(db_file)
    return db_files


def get_archive_files():
    """\
    Fetches archived files from database.
    """
    return models.Archive.select().order_by(models.Archive.created_at.desc())


def get_file_hash(file_with_path):
    """\
    Generates adler32 hash for given file in upload_folder.
    """
    with open(file_with_path, "rb") as f:
        return zlib.adler32(b"".join(f.readlines()))


@http("/pdf_files")
def get_pdf_files(web):
    upload_folder = CONFIG["paths"].get("upload_folder")
    pdf_files = get_upload_files(upload_folder)
    template = ENV.get_template("_pdf_table.html")
    web.write(template.render(pdf_files=pdf_files))


@http("/file-upload")
def file_upload(web):
    """PDF upload aka adding PDF via drag and drop."""
    pdf_file = web.request.files.get("file")[0]
    if pdf_file.get("content_type") != "application/pdf":
        web.write("No PDF")
    else:
        upload_folder = CONFIG["paths"].get("upload_folder")
        filename = pdf_file.get("filename")
        content = pdf_file.get("body")
        with open(os.path.join(upload_folder, filename), "wb") as new_file:
            new_file.write(content)
        web.write("success")


@http("/archive")
def get_archive_pdf_files(web):
    pdf_files = get_archive_files()
    template = ENV.get_template("_archive_table.html")
    web.write(template.render(pdf_files=pdf_files))


@http("/settings_save")
def save_settings(web):
    form = web.request.body_arguments
    # TODO: Validate arguments
    # TOML is not able to handle byte-strings, so we have to decode them
    CONFIG["paths"]["upload_folder"] = form.get("upload_folder")[0].decode()
    CONFIG["paths"]["archive_folder"] = form.get("archive_folder")[0].decode()
    CONFIG["onlinebrief24"]["username"] = form.get("username")[0].decode()
    CONFIG["onlinebrief24"]["password"] = form.get("password")[0].decode()
    PkTomlConfig().write_config(CONFIG)
    web.redirect("/Settings?success")


@http("/pdf_settings_save")
def save_pdf_settings(web):
    form = web.request.body_arguments
    pdf = (
        models.PdfFile.select()
        .where(
            models.PdfFile.adler32 == form["adler32"],
            models.PdfFile.filename == form["filename"],
        )
        .limit(1)
        .execute()[0]
    )

    # color
    if form.get("color", None)[0].decode() == "true":
        pdf.color = True
    else:
        pdf.color = False
    # duplex
    if form.get("duplex", None)[0].decode() == "true":
        pdf.duplex = True
    else:
        pdf.duplex = False
    # envelope
    envelope = form.get("envelope", None)[0].decode()
    if envelope:
        pdf.envelope = envelope
    # distribution
    distribution = form.get("distribution", None)[0].decode()
    if distribution:
        pdf.distribution = distribution
    # registered
    registered = form.get("registered", None)[0].decode()
    if registered == "None":
        pdf.registered = None
    else:
        pdf.registered = registered
    # payment_slip
    payment_slip = form.get("payment_slip", None)[0].decode()
    if payment_slip == "None":
        pdf.payment_slip = None
    else:
        pdf.payment_slip = payment_slip

    pdf.save()

    logging.debug(
        "pdf setting:::  color: {}, duplex: {}, envelope: {}, distri: {}, registered: {}, payment_slip: {}".format(
            pdf.color,
            pdf.duplex,
            pdf.envelope,
            pdf.distribution,
            pdf.registered,
            pdf.payment_slip,
        )
    )
    web.redirect("/Main")


if __name__ == "__main__":
    app = Main()
    app.run()
