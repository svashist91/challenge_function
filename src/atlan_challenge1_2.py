# %% [markdown]
# # Atlan Challenge 1
# 
# #### Objective: 
# Ingest S3 objects in the given S3 bucket as assets on Atlan.
# 
# #### Solution:
# - Do necessary package installations and library installs.
# - Initialize a client for the Atlan API and setting up basic logging functionality.
# - Create connection asset.
#     - A check to see if the connection already exists. If it does, logging will raise an info.
#     - If the connection does not exist, create one.
# - Create S3 bucket asset.
#     - A check to see if the s3 bucket asset already exists for a particular connection. If it does, logging will raise an info.
#     - If the s3 bucket does not exist, create one.
# - Create S3 object asset.
#     - For every object inside aws s3 bucket, a check to see if the s3 object asset already exists for a particular s3 bucket and it's corresponding connection. If it does, logging will raise an info.
#     - If the s3 object does not exist, create one.
# 



# %% [markdown]
# # Atlan Challenge 2
# 
# #### Objective: 
# Establish upstream and downstream lineage to some Postgres and Snowflake assets. The required Postgres and Snowflake assets have already been ingested on the Atlan instance.
# 
# #### Solution:
# - Create  postgresql_tables dictionary that stores postgresql table names and their corresponsing GUIDs for given postgresql connection.
#     - Retrieve the connection qualified name for a postgresql connection name.
#     - Using connection detail fetch names and guids and create postgresql_tables dictionary to store s3 object names and their corresponsing GUIDs as a key value pair.
# 
# - Create  s3_objects dictionary that stores tables and their corresponsing GUIDs for given postgresql connection.
#     - Retrieve the connection qualified name for a s3 connection name.
#     - Using connection detail fetch names and guids and create s3_objects dictionary to store s3 objects and their corresponsing GUIDs as a key value pair.
# 
# - Create  snowflake_tables dictionary that stores snowflake table names and their corresponsing GUIDs for given postgresql connection.
#     - Retrieve the connection qualified name for a snowflake connection name.
#     - Using connection detail fetch names and guids and create snowflake_tables dictionary to store tables and their corresponsing GUIDs as a key value pair.
# 
# - Create Lineage Postgresql > S3 
#     - For every key existing in postgresql_tables dictionary, find name matching key in s3_objects dictionary and fetch corresponding GUIDs.
#     - Check existing lineage.
#     - Parameterized function creating lineage between postgresql tables and s3 objects.
# 
# - Creating Lineage S3 > Snowflake
#     - For every key existing in s3_objects dictionary, find name matching key in snowflake_tables dictionary and fetch corresponding GUIDs.
#     - Check existing lineage.
#     - Parameterized function creating lineage between postgresql tables and s3 objects.
# 





# ## Imports

# %%
import os
import logging
import datetime

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import ClientError

from pyatlan.client.atlan import AtlanClient
from pyatlan.cache.role_cache import RoleCache
from pyatlan.model.assets import (
    Connection,
    S3Bucket,
    S3Object,
    Process,
    Table,
    Asset,
)
from pyatlan.model.enums import AtlanConnectorType, LineageDirection
from pyatlan.errors import AtlanError, NotFoundError
from pyatlan.model.fluent_search import FluentSearch, CompoundQuery
from pyatlan.model.lineage import FluentLineage


# %% [markdown]
# ## Initiate Atlan client

# %%
class AtlanS3Manager:
    """
    A class to manage S3 assets in Atlan.
    """
    def __init__(self):
        """
        Initializes the AtlanS3Manager and the Atlan client.
        """

        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        try:
            self.client = AtlanClient(
                base_url=os.environ.get("ATLAN_BASE_URL"),
                api_key=os.environ.get("ATLAN_API_KEY"),
            )
            logging.info("Atlan client initialized")

        except AtlanError as e:
            logging.error(f"Atlan API Error: {e}")

        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")

# %% [markdown]
# ## Create Connection asset

# %%
    def check_existing_connection(self, connection_name: str) -> str | None:
        """
        Checks if a connection with the given name and connector type exists in Atlan.

        Args:
            connection_name (str): The name of the connection to check.

        Returns:
            str | None: The qualified name of the connection if it exists, otherwise None.
        """
        try:
            existing_connections = self.client.asset.find_connections_by_name(
                name=connection_name,
                connector_type=AtlanConnectorType.S3,
                attributes=[]
            )
            return existing_connections[0].qualified_name
        except NotFoundError:
            return None
        except AtlanError as e:
            logging.error(f"Atlan API Error checking for connection: {e}")
            return None
        

    def create_s3_connection(self, connection_name: str) -> str | None:
        """
        Creates an S3 connection in Atlan if it doesn't already exist.

        Args:
            connection_name (str): The name of the connection to create.

        Returns:
             str | None: The qualified name of the created connection, otherwise None.
        """
        try:
            admin_role_guid = RoleCache.get_id_for_name("$admin")
            connection = Connection.creator(
                name=connection_name,
                connector_type=AtlanConnectorType.S3,
                admin_roles=[admin_role_guid],
            )
            response = self.client.asset.save(connection)
            return response.assets_created(asset_type=Connection)[0].qualified_name
        except AtlanError as e:
            logging.error(f"Atlan API Error creating connection: {e}")
            return None
        


# %% [markdown]
# ## Create an S3 bucket asset

# %%
    def check_existing_bucket(self, bucket_name: str, connection_qualified_name: str) -> str | None:
        """
        Checks if an S3 bucket with the given name exists in Atlan.

        Args:
            bucket_name (str): The name of the bucket to check.
            connection_qualified_name (str): The qualified name of the connection.

        Returns:
            str | None: The qualified name of the bucket if it exists, otherwise None.
        """
        try:
            # Search for all S3 buckets using FluentSearch
            request = (
                FluentSearch()
                .where(CompoundQuery.asset_type(S3Bucket))
                .where(CompoundQuery.active_assets())
                .include_on_results(S3Bucket.CONNECTION_QUALIFIED_NAME)
                .page_size(1000)
            ).to_request()

            for result in self.client.asset.search(request):
                if isinstance(result, S3Bucket) and result.name == bucket_name and result.connection_qualified_name == connection_qualified_name:
                    return result.qualified_name  # Bucket found
            return None  # Bucket not found
        except AtlanError as e:
            logging.error(f"Atlan API Error checking for bucket: {e}")
            return None


    def create_s3_bucket(self, bucket_name: str, connection_qualified_name: str) -> str | None:
        """
        Creates an S3 bucket in Atlan if it doesn't already exist.

        Args:
            bucket_name (str): The name of the bucket to create.
            connection_qualified_name (str): The qualified name of the S3 connection.

        Returns:
            str | None: The qualified name of the created bucket, otherwise None.
        """
        try:
            s3_bucket = S3Bucket.creator(
                name=bucket_name,
                connection_qualified_name=connection_qualified_name,
            )
            response = self.client.asset.save(s3_bucket)
            return response.assets_created(asset_type=S3Bucket)[0].qualified_name
        except AtlanError as e:
            logging.error(f"Atlan API Error creating bucket: {e}")
            return None



    def s3_object_exists_atlan(self, connection_qualified_name: str, bucket_qualified_name: str, object_key: str):
        """
        Checks if an S3 object with the given key exists in Atlan for a specific connection and bucket.

        Args:
            object_key (str): The key of the S3 object to check.
            connection_qualified_name (str): The qualified name of the connection.
            bucket_qualified_name (str): The qualified name of the bucket.

        Returns:
            str | None: The qualified name of the S3 object if it exists, otherwise None.
        """
        try:
            # Search for all S3 objects using FluentSearch
            request = (
                FluentSearch()
                .where(CompoundQuery.asset_type(S3Object))
                .where(CompoundQuery.active_assets())
                .include_on_results(S3Object.CONNECTION_QUALIFIED_NAME)
                .include_on_results(S3Object.S3BUCKET_QUALIFIED_NAME)
                .page_size(1000)
            ).to_request()

            for result in self.client.asset.search(request):
                if isinstance(result, S3Object) and result.name == object_key and result.connection_qualified_name == connection_qualified_name and result.s3_bucket_qualified_name == bucket_qualified_name:
                    
                    s3_object = self.client.asset.get_by_qualified_name(
                        asset_type=S3Object,  # 
                        qualified_name=result.qualified_name
                    )
                                                   
                    return s3_object
            return None  # S3 object not found
        except AtlanError as e:
            logging.error(f"Atlan API Error checking for S3 object: {e}")
            return None



    def create_s3_object(self, object_key: str, connection_qualified_name: str, bucket_qualified_name: str) -> S3Object:
        """
        Creates an S3 object in Atlan.

        Args:
            object_key (str): The key of the S3 object to create.
            connection_qualified_name (str): The qualified name of the connection.
            bucket_qualified_name (str): The qualified name of the bucket.

        Returns:
            S3Object: The created S3 object.
        """
        aws_arn = f"{bucket_qualified_name}-{object_key}"
        s3object = S3Object.creator(
            name=object_key,
            connection_qualified_name=connection_qualified_name,
            aws_arn=aws_arn,
            s3_bucket_qualified_name=bucket_qualified_name
        )
        response = self.client.asset.save(s3object)
        return s3object

    def update_s3_object_metadata(self, s3object: S3Object, obj: dict, bucket_name: str, bucket_qualified_name: str):
        """
        Updates the metadata of an S3 object in Atlan.

        Args:
            s3object (S3Object): The S3 object to update.
            obj (dict): The object metadata from S3.
            bucket_name (str): The name of the bucket.
            bucket_qualified_name (str): The qualified name of the bucket.
        """
        s3object_update = S3Object.updater(
            qualified_name=s3object.attributes.qualified_name,
            name=s3object.attributes.name
        )
        s3object_update.s3_object_size = obj.get('Size')
        s3object_update.s3_bucket_name = bucket_name
        s3object_update.s3_bucket_qualified_name = bucket_qualified_name
        s3object_update.s3_object_last_modified_time = obj.get('LastModified')
        s3object_update.s3_object_storage_class = obj.get('StorageClass')
        s3object_update.s3_object_version_id = obj.get('ETag')
        s3object_update.s3_e_tag = obj.get('ETag')

        response = self.client.asset.update_merging_cm(s3object_update)
        logging.info(f"Updated metadata for S3Object asset: {s3object.attributes.name}")


# %% [markdown]
# # Postgresql Dictionary

# %%


    def get_connection_qualified_name(self, connection_name: str, connector_type: AtlanConnectorType) -> str | None:
        """
        Retrieves the connection qualified name for a given connection name.

        Args:
            connection_name (str): The name of the connection.
            connector_type (AtlanConnectorType): The type of the connection.

        Returns:
            str | None: The connection qualified name if found, otherwise None.
        """
        try:
            connections = self.client.asset.find_connections_by_name(
                name=connection_name,
                connector_type=connector_type,
                attributes=[]
            )
            if connections:
                return connections[0].qualified_name
            else:
                return None
        except AtlanError as e:
            logging.error(f"Atlan API Error retrieving connection qualified name: {e}")
            return None


    def get_postgresql_tables(self, connection_qualified_name: str) -> dict:
        """
        Retrieves a dictionary of PostgreSQL table names and their corresponding GUIDs.

        Args:
            connection_qualified_name (str): The qualified name of the PostgreSQL connection.

        Returns:
            dict: A dictionary where keys are table names and values are table GUIDs.
        """
        try:
            index = (
                FluentSearch()
                .where(CompoundQuery.asset_type(Table))
                .where(CompoundQuery.active_assets())
                .where(Table.CONNECTION_QUALIFIED_NAME.eq(connection_qualified_name))
                .include_on_results(Asset.CONNECTION_NAME)
                .include_on_results(Asset.NAME)
            ).to_request()

            results = self.client.asset.search(index)

            postsql_dic = {}
            for asset in results:
                if isinstance(asset, Table):
                    table_name = asset.attributes.name
                    table_guid = asset.guid
                    postsql_dic[table_name] = table_guid
            return postsql_dic

        except AtlanError as e:
            logging.error(f"Atlan API Error retrieving PostgreSQL tables: {e}")
            return {}  # Return an empty dictionary in case of an error


# %% [markdown]
# # S3 Dictionary

# %%


    def get_s3_objects(self, connection_qualified_name: str) -> dict:
        """
        Retrieves a dictionary of S3 object names (without .csv extension) and their corresponding GUIDs.

        Args:
            connection_qualified_name (str): The qualified name of the S3 connection.

        Returns:
            dict: A dictionary where keys are S3 object names and values are object GUIDs.
        """
        try:
            index = (
                FluentSearch()
                .where(CompoundQuery.asset_type(S3Object))
                .where(CompoundQuery.active_assets())
                .where(S3Object.CONNECTION_QUALIFIED_NAME.eq(connection_qualified_name))
                .include_on_results(Asset.CONNECTION_NAME)
                .include_on_results(Asset.NAME)
            ).to_request()

            results = self.client.asset.search(index)

            s3_dic = {}
            for asset in results:
                if isinstance(asset, S3Object):
                    object_name = asset.attributes.name.replace('.csv', '')
                    object_guid = asset.guid
                    s3_dic[object_name] = object_guid
            return s3_dic

        except AtlanError as e:
            logging.error(f"Atlan API Error retrieving S3 objects: {e}")
            return {}  # Return an empty dictionary in case of an error

# %% [markdown]
# # Snowflake Dictionary

# %%

    def get_snowflake_tables(self, connection_qualified_name: str) -> dict:
        """
        Retrieves a dictionary of Snowflake table names and their corresponding GUIDs.

        Args:
            connection_qualified_name (str): The qualified name of the Snowflake connection.

        Returns:
            dict: A dictionary where keys are table names and values are table GUIDs.
        """
        try:
            index = (
                FluentSearch()
                .where(CompoundQuery.asset_type(Table))
                .where(CompoundQuery.active_assets())
                .where(Table.CONNECTION_QUALIFIED_NAME.eq(connection_qualified_name))
                .include_on_results(Asset.CONNECTION_NAME)
                .include_on_results(Asset.NAME)
            ).to_request()

            results = self.client.asset.search(index)

            snow_dic = {}
            for asset in results:
                if isinstance(asset, Table):
                    table_name = asset.attributes.name
                    table_guid = asset.guid
                    snow_dic[table_name] = table_guid
            return snow_dic

        except AtlanError as e:
            logging.error(f"Atlan API Error retrieving Snowflake tables: {e}")
            return {}  # Return an empty dictionary in case of an error
        
# %% [markdown]
# # Creating Lineage Postgresql > S3 

# %%

    def lineage_exists(self, source_guid: str, target_guid: str) -> bool:
        """
        Checks if a lineage exists between a source and target asset.

        Args:
            source_guid (str): The GUID of the source asset.
            target_guid (str): The GUID of the target asset.

        Returns:
            bool: True if lineage exists, False otherwise.
        """
        # Prepare lineage request
        request = FluentLineage(
            starting_guid=source_guid,
            depth=1,  # Check only direct lineage
            direction=LineageDirection.DOWNSTREAM,
            size=10,
            includes_on_results=Asset.NAME,
        ).request

        # Retrieve lineage list
        response = self.client.asset.get_lineage_list(request)

        # Check if the target GUID exists in the lineage results
        for asset in response:
            if asset.guid == target_guid:
                return True  # Lineage exists

        return False  # Lineage does not exist


    def create_lineage(self, key: str, source_guid: str, target_guid: str, connection_qualified_name: str):
        """
        Creates a lineage between a source and target asset.

        Args:
            key (str): The key to be used in the lineage name.
            source_guid (str): The GUID of the source asset.
            target_guid (str): The GUID of the target asset.
            connection_qualified_name (str): The qualified name of the connection.
        """
        # Generate name
        name = f"postsql_{key} > s3_{key}"

        # Generate process_id with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        process_id = f"postsql_{key}_s3_{timestamp}"

        # Create process
        process = Process.creator(
            name=name,
            connection_qualified_name=connection_qualified_name,
            process_id=process_id,
            inputs=[
                Table.ref_by_guid(guid=source_guid)
            ],
            outputs=[
                Table.ref_by_guid(guid=target_guid)
            ],
        )

        # Save process
        response = self.client.asset.save(process)


        assert (processes := response.assets_created(Process))
        assert len(processes) == 1
        assert (tables := response.assets_updated(Table))
        assert len(tables) == 1

        # Print the GUID of the newly created lineage
        new_lineage_guid = processes[0].guid
        print(f"Newly created lineage GUID: {new_lineage_guid}")

        return response

# %% [markdown]
# # Creating Lineage S3 > Snowflake

# %%

    def lineage_exists(self, source_guid: str, target_guid: str) -> bool:
        """
        Checks if a lineage exists between a source and target asset.

        Args:
            source_guid (str): The GUID of the source asset.
            target_guid (str): The GUID of the target asset.

        Returns:
            bool: True if lineage exists, False otherwise.
        """
        # Prepare lineage request
        request = FluentLineage(
            starting_guid=source_guid,
            depth=1,  # Check only direct lineage
            direction=LineageDirection.DOWNSTREAM,
            size=10,
            includes_on_results=Asset.NAME,
        ).request

        # Retrieve lineage list
        response = self.client.asset.get_lineage_list(request)

        # Check if the target GUID exists in the lineage results
        for asset in response:
            if asset.guid == target_guid:
                return True  # Lineage exists

        return False  # Lineage does not exist


    def create_lineage(self, key: str, source_guid: str, target_guid: str, connection_qualified_name: str):
        """
        Creates a lineage between a source and target asset.

        Args:
            key (str): The key to be used in the lineage name.
            source_guid (str): The GUID of the source asset.
            target_guid (str): The GUID of the target asset.
            connection_qualified_name (str): The qualified name of the connection.
        """
        # Generate name
        name = f"s3_{key} > snowflake_{key}"

        # Generate process_id with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        process_id = f"s3_{key}_snowflake_{timestamp}"

        # Create process
        process = Process.creator(
            name=name,
            connection_qualified_name=connection_qualified_name,
            process_id=process_id,
            inputs=[
                Table.ref_by_guid(guid=source_guid)
            ],
            outputs=[
                Table.ref_by_guid(guid=target_guid)
            ],
        )

        # Save process
        response = self.client.asset.save(process)

        assert (processes := response.assets_created(Process))
        assert len(processes) == 1
        assert (tables := response.assets_updated(Table))
        assert len(tables) == 1

        # Debugging print statement to check table count
        print(f"Number of updated tables: {len(tables)}")

        # Print the GUID of the newly created lineage
        new_lineage_guid = processes[0].guid
        print(f"Newly created lineage GUID: {new_lineage_guid}")

        return response



# ---  Execution starts here ---
# if __name__ == "__main__":
def execute_atlan_script(connection_name, bucket_name_atlan): 
    manager = AtlanS3Manager()

    # Check if the connection already exists
    connection_qualified_name = manager.check_existing_connection(connection_name)

    if connection_qualified_name:
        logging.info(f"Connection '{connection_name}' already exists with qualified name: {connection_qualified_name}")
    else:
        # Create the connection if it doesn't exist
        connection_qualified_name = manager.create_s3_connection(connection_name)
        if connection_qualified_name:
            logging.info(f"Created connection: {connection_qualified_name}")
        else:
            logging.error(f"Failed to create connection: {connection_name}")


    # Check if the bucket already exists
    bucket_qualified_name = manager.check_existing_bucket(bucket_name_atlan, connection_qualified_name)

    if bucket_qualified_name:
        logging.info(f"S3 Bucket '{bucket_name_atlan}' already exists with qualified name: {bucket_qualified_name}")
    else:
        # Create the bucket if it doesn't exist
        bucket_qualified_name = manager.create_s3_bucket(bucket_name_atlan, connection_qualified_name)
        if bucket_qualified_name:
            logging.info(f"Created S3 Bucket: {bucket_qualified_name}")
        else:
            logging.error(f"Failed to create bucket: {bucket_name_atlan}")

    # Configure boto3 to access the public S3 bucket
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    bucket_name = "atlan-tech-challenge"


    # List objects in the bucket
    objects = s3.list_objects_v2(Bucket=bucket_name, Prefix='')['Contents']  # Directly access 'Contents'

    for obj in objects:
        object_key = obj['Key']

        try:
            # Check if the S3 object exists in Atlan
            existing_s3_object = manager.s3_object_exists_atlan(connection_qualified_name, bucket_qualified_name, object_key)
            if existing_s3_object:
                # If the object exists, update metadata
                manager.update_s3_object_metadata(existing_s3_object, obj, bucket_name, bucket_qualified_name)
                logging.info(f"Updated existing S3Object asset for: {object_key}")
            else:
                # If the object does not exist, create it
                new_s3object = manager.create_s3_object(object_key, connection_qualified_name, bucket_qualified_name)
                logging.info(f"Created S3Object asset for: {object_key}")
                manager.update_s3_object_metadata(new_s3object, obj, bucket_name, bucket_qualified_name)
                

        except AtlanError as e:
            logging.error(f"Error processing S3Object asset for {object_key}: {e}")


    connection_name = "postgres-sv" 
    connector_type = AtlanConnectorType.POSTGRES  # Set the connector type to POSTGRES

    Postgresql_connection_qualified_name = manager.get_connection_qualified_name(connection_name, connector_type)

    # Get the dictionary of PostgreSQL tables
    postgresql_tables = manager.get_postgresql_tables(Postgresql_connection_qualified_name)

    # Print the dictionary to verify
    print(postgresql_tables)

    connection_name = "aws-s3-connection-tech-challenge-sv"  
    connector_type = AtlanConnectorType.S3  

    s3_connection_qualified_name = manager.get_connection_qualified_name(connection_name, connector_type)

    # Get the dictionary of S3 objects
    s3_objects = manager.get_s3_objects(s3_connection_qualified_name)

    # Print the dictionary to verify
    print(s3_objects)    

    connection_name = "snowflake-sv" 
    connector_type = AtlanConnectorType.SNOWFLAKE  # Set the connector type to Snowflake

    snowflake_connection_qualified_name = manager.get_connection_qualified_name(connection_name, connector_type)

    # Get the dictionary of Snowflake tables
    snowflake_tables = manager.get_snowflake_tables(snowflake_connection_qualified_name)

    # Print the dictionary to verify
    print(snowflake_tables)

    # Delete Lineage postgres > s3
    for key, guid_postsql in postgresql_tables.items():
        if key in s3_objects:
            guid_s3 = s3_objects[key]

            # Check lineage
            if manager.lineage_exists(guid_postsql, guid_s3):
                print(f"Lineage already exists between {key} in PostgreSQL ({guid_postsql}) and S3 ({guid_s3})")
            else:
                print(f"Creating lineage between {key} in PostgreSQL ({guid_postsql}) and S3 ({guid_s3})")
                manager.create_lineage(key, guid_postsql, guid_s3, Postgresql_connection_qualified_name) 

    # Delete Lineage s3 > Snowflake
    for key, guid_s3 in s3_objects.items():
        if key in snowflake_tables:
            guid_snow = snowflake_tables[key]

            # Check lineage
            if manager.lineage_exists(guid_s3, guid_snow):
                print(f"Lineage already exists between {key} in Snowflake ({guid_snow}) and S3 ({guid_s3})")
            else:
                print(f"Creating lineage between {key} in Snowflake ({guid_snow}) and S3 ({guid_s3})")
                manager.create_lineage(key, guid_s3, guid_snow, s3_connection_qualified_name)