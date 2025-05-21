"""File output utilities"""
import tempfile
import os
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

        if self.job_id:
            filename = f"{self.job_id}/{filename}"
        base_path = get_settings().file_output_base_path
        if base_path.startswith('s3://'):
            # Extract bucket name and object name from S3 path
            bucket_name = base_path.split('/')[2]
            object_name = '/'.join(base_path.split('/')[3:]).lstrip('/')
            object_name += f"/{filename}"
            self._s3_upload(output_path, bucket_name, object_name.lstrip('/'))
            # Remove the local temp file
            os.unlink(output_path)

        return self.file_url(filename)
