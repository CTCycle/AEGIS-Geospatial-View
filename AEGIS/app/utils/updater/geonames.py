from __future__ import annotations

import io
import os
import urllib.request
import zipfile
from collections.abc import Iterator
from logging import Logger
from typing import Any

from AEGIS.app.constants import SOURCES_PATH
from AEGIS.app.utils.repository.serializer import (
    DataSerializer,
    GEONAMES_COLUMNS,
)
from AEGIS.app.logger import logger

GEONAMES_BASE_URL = "https://download.geonames.org/export/dump"
DEFAULT_DATASET = "allCountries.zip"


###############################################################################
class GeonamesDatasetDownloader:
    def __init__(
        self,
        base_url: str,
        dataset: str,
        target_dir: str,
        chunk_size: int = 1024 * 1024,
        logger_instance: Logger | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dataset = dataset
        self.target_dir = target_dir
        self.chunk_size = chunk_size
        self.logger = (
            logger_instance
            if logger_instance is not None
            else logger.getChild("GeonamesDatasetDownloader")
        )

    # -----------------------------------------------------------------------------
    def download(self) -> str:
        os.makedirs(self.target_dir, exist_ok=True)
        archive_path = os.path.join(self.target_dir, self.dataset)
        url = f"{self.base_url}/{self.dataset}"
        self.logger.info(
            "Starting download of %s from %s", self.dataset, self.base_url
        )
        with urllib.request.urlopen(url) as response, open(archive_path, "wb") as file:
            total_size = int(response.headers.get("content-length", "0"))
            downloaded = 0
            while True:
                chunk = response.read(self.chunk_size)
                if not chunk:
                    break
                file.write(chunk)
                downloaded += len(chunk)
                self.display_progress(downloaded, total_size)
        self.display_progress(downloaded, total_size, finished=True)
        self.logger.info("Finished downloading %s to %s", self.dataset, archive_path)
        return archive_path

    # -----------------------------------------------------------------------------
    def display_progress(self, downloaded: int, total_size: int, finished: bool = False) -> None:
        if total_size > 0:
            percentage = min(int(downloaded * 100 / total_size), 100)
            message = (
                f"Downloading {self.dataset}: {percentage}% "
                f"({downloaded}/{total_size} bytes)"
            )
        else:
            message = f"Downloading {self.dataset}: {downloaded} bytes"
        if finished:
            self.logger.info(message)
        else:
            self.logger.debug(message)


###############################################################################
class GeonamesArchiveReader:
    def __init__(self, archive_path: str) -> None:
        self.archive_path = archive_path

    # -----------------------------------------------------------------------------
    def iterate_lines(self) -> Iterator[str]:
        with zipfile.ZipFile(self.archive_path) as archive:
            member_name = self.get_primary_member(archive)
            with archive.open(member_name) as binary_stream:
                text_stream = io.TextIOWrapper(binary_stream, encoding="utf-8")
                for line in text_stream:
                    yield line.rstrip("\r\n")

    # -----------------------------------------------------------------------------
    def get_primary_member(self, archive: zipfile.ZipFile) -> str:
        for member in archive.namelist():
            if member.endswith(".txt"):
                return member
        return archive.namelist()[0]


###############################################################################
class GeonamesArchiveParser:
    def __init__(
        self,
        serializer: DataSerializer,
        batch_size: int = 5000,
        logger_instance: Logger | None = None,
    ) -> None:
        self.serializer = serializer
        self.batch_size = batch_size
        self.logger = (
            logger_instance
            if logger_instance is not None
            else logger.getChild("GeonamesArchiveParser")
        )

    # -----------------------------------------------------------------------------
    def parse(self, archive_path: str) -> None:
        reader = GeonamesArchiveReader(archive_path)
        batch: list[dict[str, Any]] = []
        total_records = 0
        self.logger.info("Parsing geonames archive %s", archive_path)
        for line in reader.iterate_lines():
            record = self.create_record(line)
            if record is None:
                continue
            batch.append(record)
            total_records += 1
            if len(batch) >= self.batch_size:
                self.flush_batch(batch)
                batch.clear()
                self.logger.debug("Stored %s geonames records", total_records)
        if batch:
            self.flush_batch(batch)
        self.logger.info("Stored %s geonames records", total_records)

    # -----------------------------------------------------------------------------
    def flush_batch(self, batch: list[dict[str, Any]]) -> None:
        self.serializer.upsert_geonames_records(batch)

    # -----------------------------------------------------------------------------
    def create_record(self, line: str) -> dict[str, Any] | None:
        values = line.split("\t")
        if len(values) < len(GEONAMES_COLUMNS):
            return None
        geoname_id = self.parse_int(values[0])
        if geoname_id is None:
            return None
        record: dict[str, Any] = {
            "geonameid": geoname_id,
            "name": self.parse_text(values[1]),
            "asciiname": self.parse_text(values[2]),
            "alternatenames": self.parse_nullable_text(values[3]),
            "latitude": self.parse_float(values[4]),
            "longitude": self.parse_float(values[5]),
            "feature_class": self.parse_text(values[6]),
            "feature_code": self.parse_text(values[7]),
            "country_code": self.parse_text(values[8]),
            "cc2": self.parse_nullable_text(values[9]),
            "admin1_code": self.parse_text(values[10]),
            "admin2_code": self.parse_text(values[11]),
            "admin3_code": self.parse_text(values[12]),
            "admin4_code": self.parse_text(values[13]),
            "population": self.parse_int(values[14]),
            "elevation": self.parse_int(values[15]),
            "dem": self.parse_int(values[16]),
            "timezone": self.parse_text(values[17]),
            "modification_date": self.parse_text(values[18]),
        }
        return record

    # -----------------------------------------------------------------------------
    def parse_int(self, value: str) -> int | None:
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None

    # -----------------------------------------------------------------------------
    def parse_float(self, value: str) -> float | None:
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None

    # -----------------------------------------------------------------------------
    def parse_text(self, value: str) -> str | None:
        stripped = value.strip()
        return stripped or None

    # -----------------------------------------------------------------------------
    def parse_nullable_text(self, value: str) -> str | None:
        return self.parse_text(value)


###############################################################################
class GeonamesUpdater:
    def __init__(
        self,
        serializer: DataSerializer | None = None,
        base_url: str = GEONAMES_BASE_URL,
        dataset: str = DEFAULT_DATASET,
        storage_dir: str | None = None,
        batch_size: int = 5000,
        logger_instance: Logger | None = None,
    ) -> None:
        self.serializer = serializer or DataSerializer()
        self.base_url = base_url
        self.dataset = dataset
        self.storage_dir = storage_dir or os.path.join(SOURCES_PATH, "geonames")
        self.batch_size = batch_size
        self.logger = (
            logger_instance
            if logger_instance is not None
            else logger.getChild("GeonamesUpdater")
        )

    # -----------------------------------------------------------------------------
    def update(self) -> None:
        self.logger.info("Starting geonames updater for dataset %s", self.dataset)
        downloader = GeonamesDatasetDownloader(
            base_url=self.base_url,
            dataset=self.dataset,
            target_dir=self.storage_dir,
            logger_instance=self.logger.getChild("GeonamesDatasetDownloader"),
        )
        archive_path = downloader.download()
        parser = GeonamesArchiveParser(
            self.serializer,
            batch_size=self.batch_size,
            logger_instance=self.logger.getChild("GeonamesArchiveParser"),
        )
        parser.parse(archive_path)
        self.logger.info("Completed geonames updater for dataset %s", self.dataset)

