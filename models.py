from datetime import datetime
from os.path import expanduser

from peewee import *

from pk_toml_config import PkTomlConfig

_config = PkTomlConfig().load_config()
_db = SqliteDatabase(expanduser(_config["cache"].get("database")))


class PdfFile(Model):
    """\
    This is a config cache of a not send PDF.
    """

    pk = AutoField()
    adler32 = CharField()
    filename = CharField()
    color = BooleanField(default=True)
    duplex = BooleanField(default=True)
    envelope = CharField(default="din_lang")
    distribution = CharField(default="auto")
    registered = CharField(default=None, null=True)
    payment_slip = CharField(default=None, null=True)
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField()

    class Meta:
        database = _db
        db_table = "pdf_file"

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(PdfFile, self).save(*args, **kwargs)


class Archive(Model):
    """\
    Archive of send letters.
    """

    pk = AutoField()
    adler32 = CharField()
    filename = CharField()
    color = BooleanField(default=True)
    duplex = BooleanField(default=True)
    envelope = CharField(default="din_lang")
    distribution = CharField(default="auto")
    registered = CharField(default=None, null=True)
    payment_slip = CharField(default=None, null=True)
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField()

    class Meta:
        database = _db
        db_table = "archive"

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(Archive, self).save(*args, **kwargs)


_db.create_tables([PdfFile, Archive])
