import sqlite3
import unittest

from dispatcher_sdk.execution_kernel import _sqlite_schema as schema
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError


class KernelPauseSchemaTests(unittest.TestCase):
    def test_historical_upgrade_chain_and_corrupt_v6_rejection(self):
        with sqlite3.connect(":memory:") as connection:
            connection.executescript(schema.KERNEL_SCHEMA_V4)
            schema.upgrade_kernel_schema_v4_to_v5(connection)
            schema.validate_kernel_schema_v5(connection)
            schema.upgrade_kernel_schema_v5_to_v6(connection)
            schema.validate_kernel_schema_v6(connection)
            connection.execute("CREATE TABLE kernel_unexpected (value TEXT)")
            with self.assertRaises(StorageIsolationError):
                schema.validate_kernel_schema_v6(connection)
            connection.execute("DROP TABLE kernel_unexpected")
            connection.commit()
            schema.upgrade_kernel_schema_v6_to_v7(connection)
            schema.validate_kernel_schema_v7(connection)
            schema.upgrade_kernel_schema_v7_to_v8(connection)
            schema.upgrade_kernel_schema_v8_to_v9(connection)
            schema.upgrade_kernel_schema_v9_to_v10(connection)
            schema.upgrade_kernel_schema_v10_to_v11(connection)
            schema.upgrade_kernel_schema_v11_to_v12(connection)
            connection.row_factory = sqlite3.Row
            schema.validate_schema(connection, schema.KERNEL_TABLES)
