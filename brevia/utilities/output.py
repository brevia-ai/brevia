import tempfile
import boto3
from brevia.settings import get_settings


class FileOutput:
    """
    A class to handle file output operations in Brevia that need a public link.
    """
    job_id = None

    def __init__(self, job_id):
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
        base_path = get_settings().file_output_base_path
        s3_path = base_path if base_path and base_path.startswith('s3://') else None
        if not base_path or s3_path:
            out_dir = tempfile.mkdtemp()
        self.output_path = f"{out_dir}/{filename}"

    def file_url(self, filename: str):
        """
        Generate the URL for the output file.

        :param filename: The name of the file.
        :return: The URL to access the file.
        """
        base_path = get_settings().file_output_base_path
        if base_path.startswith('s3://'):
            # Extract bucket name and object name from S3 path
            bucket_name = base_path.split('/')[2]
            if self.job_id:
                filename = f"{self.job_id}/{filename}"
            object_name = '/'.join(base_path.split('/')[3:]).lstrip('/')
            object_name += f"/{filename}"
            s3 = boto3.client('s3')
            s3.upload_file(self.output_path, bucket_name, object_name.lstrip('/'))

        # Generate the output URL
        base_url = get_settings().file_output_base_url
        return f'{base_url}/{filename}'

    def write(self, content: str, filename: str):
        """
        Write content to the file.

        :param content: The content to write to the file.
        :param filename: The name of the file to write to.
        """
        output_path = self.file_path(filename)
        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(content)

        return self.file_url(filename)
