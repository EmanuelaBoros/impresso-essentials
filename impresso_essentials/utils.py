#!/usr/bin/env python
# coding: utf-8

import sys
import json
import os
import logging
import pathlib
import time
from typing import Any, Generator, Optional
from datetime import timedelta
from contextlib import ExitStack
import jsonschema
import importlib_resources
import numpy as np

from dask.bag.core import Bag
from dask.diagnostics import ProgressBar

logger = logging.getLogger(__name__)

KNOWN_JOURNALS = [
    "BDC",
    "CDV",
    "DLE",
    "EDA",
    "EXP",
    "IMP",
    "GDL",
    "JDF",
    "JDV",
    "LBP",
    "LCE",
    "LCG",
    "LCR",
    "LCS",
    "LES",
    "LNF",
    "LSE",
    "LSR",
    "LTF",
    "LVE",
    "EVT",
    "JDG",
    "LNQ",
    "NZZ",
    "FedGazDe",
    "FedGazFr",
    "FedGazIt",
    "arbeitgeber",
    "handelsztg",
    "actionfem",
    "armeteufel",
    "avenirgdl",
    "buergerbeamten",
    "courriergdl",
    "deletz1893",
    "demitock",
    "diekwochen",
    "dunioun",
    "gazgrdlux",
    "indeplux",
    "kommmit",
    "landwortbild",
    "lunion",
    "luxembourg1935",
    "luxland",
    "luxwort",
    "luxzeit1844",
    "luxzeit1858",
    "obermosel",
    "onsjongen",
    "schmiede",
    "tageblatt",
    "volkfreu1869",
    "waechtersauer",
    "waeschfra",
    "BLB",
    "BNN",
    "DFS",
    "DVF",
    "EZR",
    "FZG",
    "HRV",
    "LAB",
    "LLE",
    "MGS",
    "NTS",
    "NZG",
    "SGZ",
    "SRT",
    "WHD",
    "ZBT",
    "CON",
    "DTT",
    "FCT",
    "GAV",
    "GAZ",
    "LLS",
    "OIZ",
    "SAX",
    "SDT",
    "SMZ",
    "VDR",
    "VHT",
]
# TODO add new titles to this list


def user_confirmation(question: str, default: str | None = None) -> bool:
    """Ask a yes/no question via raw_input() and return their answer.

    Args:
        question (str): String question presented to the user.
        default (str | None, optional): Presumed answer if the user just hits <Enter>.
            Should be one of "yes", "no" and None. Defaults to None.

    Raises:
        ValueError: The default value provided is not valid.

    Returns:
        bool: User's answer to the asked question.
    """
    valid = {"yes": True, "y": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        err_msg = f"Invalid default answer: '{default}'"
        raise ValueError(err_msg)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        if choice in valid:
            return valid[choice]
        sys.stdout.write("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")


def user_question(variable_to_confirm: str) -> None:
    """Ask the user if the identified variable is correct.

    Args:
        variable_to_confirm (str): Variable to be checked by the user.
    """
    answer = user_confirmation(
        f"\tIs the following the correct item to work with?\n  {variable_to_confirm}",
        None,
    )

    if not answer:
        logger.info("Variable not confirmed, exiting.")
        sys.exit()
    else:
        logger.info("Variable confirmed.")


def timestamp(ts_format: str = "%Y-%m-%dT%H:%M:%SZ", with_space: bool = False) -> str:
    """Return an iso-formatted timestamp.

    Args:
        ts_format (str, optional): Timestamp format to use for the returned timestamp.
            Defaults to "%Y-%m-%dT%H:%M:%SZ".
        with_space (bool, optional): Format the timestamp with spaces. If True, the
            format used will be "%Y-%m-%d %H:%M:%S". Defaults to False.

    Returns:
        str: Timestamp formatted according to a provided format.
    """
    if with_space:
        ts_format = "%Y-%m-%d %H:%M:%S"
    return time.strftime(ts_format)


class Timer:
    """Basic timer"""

    def __init__(self):
        self.start = time.time()
        self.intermediate = time.time()

    def tick(self) -> str:
        """Perform a tick with the timer.

        Returns:
            str: Elapsed time since last tick in seconds.
        """
        elapsed_time = time.time() - self.intermediate
        self.intermediate = time.time()
        return str(timedelta(seconds=elapsed_time))

    def stop(self) -> str:
        """Stop the timer.

        Returns:
            str: Elapsed time since the start tick in seconds.
        """
        elapsed_time = time.time() - self.start
        return str(timedelta(seconds=elapsed_time))


def chunk(l_to_chunk: list, chunksize: int) -> Generator:
    """Yield successive n-sized chunks from list.

    Args:
        l_to_chunk (list): List to chunk down.
        chunksize (int): Size of each chunk.

    Yields:
        Generator: Each chunk of the list.
    """
    for i in range(0, len(l_to_chunk), chunksize):
        yield l_to_chunk[i : i + chunksize]


def get_pkg_resource(
    file_manager: ExitStack, path: str, package: str = "impresso_commons"
) -> pathlib.PosixPath:
    """Return the resource at `path` in `package`, using a context manager.

    Note:
        The context manager `file_manager` needs to be instantiated prior to
        calling this function and should be closed once the package resource
        is no longer of use.

    Args:
        file_manager (contextlib.ExitStack): Context manager.
        path (str): Path to the desired resource in given package.
        package (str, optional): Package name. Defaults to "impresso_commons".

    Returns:
        pathlib.PosixPath: Path to desired managed resource.
    """
    ref = importlib_resources.files(package) / path
    return file_manager.enter_context(importlib_resources.as_file(ref))


def init_logger(
    level: int = logging.INFO, file: Optional[str] = None
) -> logging.RootLogger:
    """Initialises the root logger.

    Args:
        level (int, optional): desired level of logging. Defaults to logging.INFO.
        file (str | None, optional): _description_. Defaults to None.

    Returns:
        logging.RootLogger: the initialised logger
    """
    # Initialise the logger
    root_logger = logging.getLogger("")
    root_logger.setLevel(level)

    if file is not None:
        handler = logging.FileHandler(filename=file, mode="w")
    else:
        handler = logging.StreamHandler()

    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.info("Logger successfully initialised")

    return root_logger


def validate_against_schema(
    json_to_validate: dict[str, Any],
    path_to_schema: str = "schemas/json/versioning/manifest.schema.json",
) -> None:
    """Validate a dict corresponding to a JSON against a provided JSON schema.

    Args:
        json (dict[str, Any]): JSON data to validate against a schema.
        path_to_schema (str, optional): Path to the JSON schema to validate against.
            Defaults to "impresso-schemas/json/versioning/manifest.schema.json".

    Raises:
        e: The provided JSON could not be validated against the provided schema.
    """
    file_manager = ExitStack()
    schema_path = get_pkg_resource(file_manager, path_to_schema)
    with open(os.path.join(schema_path), "r", encoding="utf-8") as f:
        json_schema = json.load(f)

    try:
        jsonschema.validate(json_to_validate, json_schema)
    except Exception as e:
        logger.error(
            "The provided JSON could not be validated against its schema: %s.",
            json_to_validate,
        )
        raise e


def bytes_to(bytes_nb: int, to_unit: str, bsize: int = 1024) -> float:
    """Convert bytes to the specified unit.

    Supported target units:
    - 'k' (kilobytes), 'm' (megabytes),
    - 'g' (gigabytes), 't' (terabytes),
    - 'p' (petabytes), 'e' (exabytes).

    Args:
        bytes_nb (int): The number of bytes to be converted.
        to_unit (str): The target unit for conversion.
        bsize (int, optional): The base size used for conversion (default is 1024).

    Returns:
        float: The converted value in the specified unit.

    Raises:
        KeyError: If the specified target unit is not supported.
    """
    units = {"k": 1, "m": 2, "g": 3, "t": 4, "p": 5, "e": 6}
    return float(bytes_nb) / (bsize ** units[to_unit])


def get_list_intersection(list1: list, list2: list) -> list:
    """Compute the intersection between two lists.

    Args:
        list1 (list): First list to intersect.
        list2 (list): First list to intersect.

    Returns:
        list: List of intersection of both arguments.
    """
    return list(set(list1).intersection(list2))


def partitioner(bag: Bag, path: str, nb_partitions: int) -> None:
    """
    Partition a Dask bag into n partitions and write each to a separate file.

    Args:
        bag (dask.bag.core.Bag): The Dask bag to be partitioned.
        path (str): Directory path where partitioned files will be saved.
        nb_partitions (int): Number of partitions to create.

    Returns:
        None: The function writes partitioned files to the specified path.
    """
    grouped_items = bag.groupby(
        lambda x: np.random.randint(500), npartitions=nb_partitions
    )
    items = grouped_items.map(lambda x: x[1]).flatten()
    path = os.path.join(path, "*.jsonl.bz2")
    with ProgressBar():
        items.to_textfiles(path)
