# Asynchronous Jobs

Brevia provides a built-in system to handle asynchronous jobs that can be particulary useful when dealing with long running tasks.

Internally these jobs are persistend in the `async_jobs` table (see [database](database.md) for more details), while the background processes are handled using [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).

Asynchronous jobs are used internally in analysis endpoints like [`/upload_summarize`](endpoints_overview.md#post-upload_summarize) and [`/upload_analyze`](endpoints_overview.md#post-upload_analyze) where files are uploaded and analyzed using built-in or custom [services](analyze_services.md).

These endpoints will simply return a job id as response like this:

```json
{"job": "7ca33644-5ddb-4747-84c0-8818715a65f8"}
```

After that you can:

- Check the async job status calling [`GET /jobs/{uuid}`](endpoints_overview.md#get-jobsuuid) to retrieve the job results as it ends
- List all jobs with optional filtering using [`GET /jobs`](endpoints_overview.md#get-jobs) to see all your async jobs with pagination and filtering capabilities

The `/jobs` endpoint supports various filters such as completion status, service type, date ranges, and pagination parameters to help you manage and monitor your asynchronous tasks effectively.
