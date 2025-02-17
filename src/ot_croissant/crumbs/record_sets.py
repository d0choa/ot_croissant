"""Class to create the croissant recordset metadata for the Open Targets Platform."""

from __future__ import annotations

from pyspark.sql import SparkSession, types as t
import mlcroissant as mlc
from ot_croissant.constants import typeDict
from ot_croissant.curation import DistributionCuration
import logging


class PlatformOutputRecordSets:
    """Class to  in the Open Targets Platform data."""

    record_sets: list[mlc.RecordSet]
    DISTRIBUTION_ID: str
    spark: SparkSession

    def __init__(self: PlatformOutputRecordSets) -> None:
        self.record_sets = []
        self.spark = SparkSession.builder.getOrCreate()
        super().__init__()  # <- What is the parent class here?

    def get_metadata(self: PlatformOutputRecordSets) -> list[mlc.RecordSet]:
        """Return the distribution metadata."""
        return self.record_sets

    def add_assets_from_paths(self: PlatformOutputRecordSets, paths: list[str]):
        """Add files from a list to the distribution."""
        for path in paths:
            self.DISTRIBUTION_ID = path.split("/")[-1]
            record_set = self.get_fileset_recordset(path)

            # Append the recordset to the record sets list:
            self.record_sets.append(record_set)

        return self

    def get_fileset_recordset(
        self: PlatformOutputRecordSets, path: str
    ) -> mlc.RecordSet:
        """Returns the recordset for a fileset."""
        # Get the schema from the recordset:
        schema = self.spark.read.parquet(path).schema

        record_set = mlc.RecordSet(
            id=self.DISTRIBUTION_ID,
            name=self.DISTRIBUTION_ID,
            fields=[self.parse_spark_field(field) for field in schema],
        )
        # Add primary key to recordset, if available:
        primary_key = DistributionCuration().get_curation(
            distribution_id=self.DISTRIBUTION_ID, key="key"
        )
        if primary_key:
            record_set.key = primary_key
        # Return record set
        return record_set

    def parse_spark_field(
        self: PlatformOutputRecordSets, field: t.StructField, parent: str | None = None
    ) -> mlc.Field:

        def get_field_description(parent: str | None, field: t.StructField) -> str:
            metadata: dict[str, str] | None = field.metadata

            if metadata and "description" in metadata:
                return metadata["description"]
            else:
                logging.warning(
                    f"[RecordSets]: Field {get_field_id(parent, field)} has no description."
                )
                return f"PLACEHOLDER for {field.name} description"

        def get_field_id(
            parent: str | None,
            field: t.StructField,
            include_distribution_id: bool = True,
        ) -> str:
            """Get the field id."""
            column_id: str
            if parent:
                column_id = f"{parent}/{field.name}"
            else:
                column_id = field.name
            if include_distribution_id:
                column_id = f"{self.DISTRIBUTION_ID}/{column_id}"
            return column_id

        field_type: str = field.dataType.typeName()
        column_description: str = get_field_description(parent, field)
        # Initialise field:
        croissant_field = mlc.Field(
            id=get_field_id(parent, field),
            name=field.name,
            description=column_description,
            data_types=typeDict.get(field_type, mlc.DataType.TEXT),
            source=mlc.Source(
                file_set=self.DISTRIBUTION_ID + "-fileset",
                extract=mlc.Extract(column=get_field_id(parent, field, False)),
            ),
        )
        # Test if the field is a list:
        if field_type == "array":
            croissant_field.repeated = True
            # A list of struct:
            if field.dataType.elementType.typeName() == "struct":
                croissant_field.sub_fields = [
                    self.parse_spark_field(subfield, get_field_id(parent, field, False))
                    for subfield in field.dataType.elementType
                ]
        # Test if the field is a struct:
        elif field_type == "struct":
            croissant_field.sub_fields = [
                self.parse_spark_field(subfield, get_field_id(parent, field, False))
                for subfield in field.dataType
            ]

        return croissant_field
