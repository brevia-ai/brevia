"""File output utilities"""
import tempfile
import os
import shutil
from brevia.settings import get_settings


class LinkedFileOutput:
    """
    A class to handle file output operations in Brevia that need a download link.
    """
    job_id = None

    def __init__(self, job_id: str = None):
        """
        Initialize the FileOutput object with a job ID.

        :param job_id: The job ID to associate with this output.
        """
        self.job_id = job_id

    def file_path(self, filename: str):
        """
        Generate the file path for the output file.

        :param filename: The name of the file.
        :return: The full path to the file.
        """
        out_dir = get_settings().file_output_base_path
        if out_dir.startswith('s3://'):
            with tempfile.NamedTemporaryFile(prefix="brevia_", delete=False) as t_file:
                return t_file.name
        if self.job_id:
            out_dir = f"{out_dir}/{self.job_id}"
            os.makedirs(out_dir, exist_ok=True)

        return f"{out_dir}/{filename}"

    def file_url(self, filename: str):
        """
        Generate the URL for the output file.

        :param filename: The name of the file.
        :return: The URL to access the file.
        """
        # Generate the output URL
        base_url = get_settings().file_output_base_url
        if self.job_id:
            base_url = f"{base_url}/{self.job_id}"

        return f'{base_url}/{filename}'

    def _s3_upload(self, file_path: str, bucket_name: str, object_name: str):
        """
        Upload the file to S3.

        :param file_path: The path to the file to upload.
        :param bucket_name: The name of the S3 bucket.
        :param object_name: The S3 object name.
        """
        try:
            import boto3  # pylint: disable=import-outside-toplevel
            s3 = boto3.client('s3')
            return s3.upload_file(file_path, bucket_name, object_name)
        except ModuleNotFoundError:
            raise ImportError('Boto3 is not installed!')

    def write(self, content: str, filename: str):
        """
        Write content of the file to the specified filename.
        Returns the URL of the file.

        :param content: The content to write to the file.
        :param filename: The name of the file to write to.
        """
        output_path = self.file_path(filename)
        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(content)

        base_path = get_settings().file_output_base_path
        if base_path.startswith('s3://'):
            # Extract bucket name and object name from S3 path
            bucket_name = base_path.split('/')[2]
            object_name = '/'.join(base_path.split('/')[3:]).lstrip('/')
            if self.job_id:
                object_name += f"/{self.job_id}"
            object_name += f"/{filename}"
            self._s3_upload(output_path, bucket_name, object_name.lstrip('/'))
            # Remove the local temp file
            os.unlink(output_path)

        return self.file_url(filename)

    def _s3_delete_objects(self, bucket_name: str, prefix: str):
        """
        Delete all objects in S3 with the specified prefix.

        :param bucket_name: The name of the S3 bucket.
        :param prefix: The prefix to match objects for deletion.
        """
        try:
            import boto3  # pylint: disable=import-outside-toplevel
            s3 = boto3.client('s3')

            # List all objects with the prefix
            response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

            if 'Contents' not in response:
                return  # No objects found

            # Prepare objects for deletion
            objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]

            # Delete objects in batches (S3 allows max 1000 objects per delete request)
            for i in range(0, len(objects_to_delete), 1000):
                batch = objects_to_delete[i:i + 1000]
                s3.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': batch}
                )

        except ModuleNotFoundError:
            raise ImportError('Boto3 is not installed!')

    def cleanup_job_files(self):
        """
        Remove all files in the job folder, including the folder itself.
        Handles both local filesystem and S3 storage.

        :raises ValueError: If no job_id is set.
        """
        if not self.job_id:
            raise ValueError("No job_id set. Cannot cleanup files without a job_id.")

        base_path = get_settings().file_output_base_path

        if base_path.startswith('s3://'):
            # S3 cleanup
            bucket_name = base_path.split('/')[2]
            base_prefix = '/'.join(base_path.split('/')[3:]).lstrip('/')

            # Build the prefix for this job's files
            if base_prefix:
                job_prefix = f"{base_prefix}/{self.job_id}/"
            else:
                job_prefix = f"{self.job_id}/"

            self._s3_delete_objects(bucket_name, job_prefix)

        else:
            # Local filesystem cleanup
            job_dir = f"{base_path}/{self.job_id}"

            if os.path.exists(job_dir) and os.path.isdir(job_dir):
                shutil.rmtree(job_dir)
