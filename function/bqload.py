from configparser import ConfigParser
from google.oauth2 import service_account
from google.cloud import storage
from google.cloud import bigquery

__version__ = "0.2"

# ToDo: add filetype (CSV, etc.) to config and implement logic in process task
# ToDo: add logic to handle hash verification of uploaded files
class LoadTaskList:
    def __init__(self, service_account_file_name='', config_name: str = 'bq_load.conf'):
        self.config_registry = {}
        if service_account_file_name:
            self.gcs = storage.Client.from_service_account_json(service_account_file_name)
            self.bq = bigquery.Client.from_service_account_json(service_account_file_name)
        else:
            self.gcs = storage.Client()
            self.bq = bigquery.Client()

        self.config_name = config_name

    def get_config(self, bucket_name: str, object_path: str):
        base_path = '/'.join( [bucket_name, *object_path.split('/')[:-1]] )
        if base_path in self.config_registry.keys():
            return( self.config_registry.get(base_path) )
        else:
            return self.read_config(bucket_name, object_path)

    def read_config(self, bucket_name: str, object_path: str):
        config_path = '/'.join( [*object_path.split('/')[:-1], 'bq_load.conf'] )

        bucket = self.gcs.get_bucket(bucket_name)
        config_blob = bucket.blob(config_path)
        config = ConfigParser()
        config.read_string(config_blob.download_as_string().decode())

        base_path = '/'.join( [bucket_name, *object_path.split('/')[:-1]] )

        self.config_registry[base_path] = config
        return(config)

    # ToDo: Support other filetypes besides CSV
    def process_task(self, bucket_name: str, object_path: str):
        # If the config file name appear at the end of the object_path then
        # the config file itself was written i.e. modified and we need to 
        # read it in case it was cached to avoid having stale entries in the
        # config_registry. No need to load any data so just return afer that.
        if object_path.endswith(self.config_name):
            self.read_config(bucket_name, object_path)
            return(0)

        bucket = self.gcs.get_bucket(bucket_name)
        blob = bucket.get_blob(object_path)
        if blob.content_type != 'text/csv':
            print(f"ERROR: {bucket_name}/{object_path} is not CSV file. Ignoring.")
            return(-1)

        config = self.get_config(bucket_name, object_path)

        dataset_ref = self.bq.dataset(config['load']['dataset'])
        table_ref = dataset_ref.table(config['load']['table'])
        job_config = bigquery.LoadJobConfig()
        job_config.skip_leading_rows = 1
        #ToDo: accomodate other formats than CSV
        job_config.source_format = bigquery.SourceFormat.CSV
        job_config.autodetect = True

        uri = f"gs://{bucket_name}/{object_path}"

        load_job = self.bq.load_table_from_uri(
            uri, table_ref, job_config=job_config
        )
        print(f"Starting job {load_job.job_id}")

        # for k in config['load']:
        #     print(k)
