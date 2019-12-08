import toml

import os
import sys
import logging
from pathlib import Path

from shutil import copyfile


class PkTomlConfig(object):
    """\
    Toml config writer and loader.
    """

    def __init__(self):
        self.config_path = self.get_config_path()

    def write_default_config(self):
        """\
        Write default config depending on OS.
        """
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            copyfile("default_config.toml", self.config_path)
        except IOError as e:
            logging.critical(
                "'%s' cannot be written. Please check permissions.", self.config_path
            )
            sys.exit(3)

    def get_config_path(self):
        """\
        Determines config path based on OS.
        """
        home = str(Path.home())
        if sys.platform.startswith("linux") or sys.platform.startswith("darwin"):
            return os.path.join(home, ".config", "postkutsche/postkutsche.toml")
        else:
            # TODO: Implement me! @win
            pass

    def load_config(self):
        """\
        Load config from file.
        """
        # write default config if there is none
        if not os.path.isfile(self.config_path):
            self.write_default_config()
        # load and return config
        return toml.load(self.config_path)

    def write_config(self, toml_config):
        """\
        Write modified config back to file
        """
        try:
            with open(self.config_path, "w") as f:
                toml.dump(toml_config, f)
        except IOError as _:
            logging.critical(
                "'%s' cannot be written. Please check permissions.", self.config_path
            )
            sys.exit(3)
