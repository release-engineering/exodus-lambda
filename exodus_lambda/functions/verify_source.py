import json
import os
import subprocess
import tempfile

import boto3


def lambda_handler(event, context):
    """Verifies the commit delivered to the pipeline by GitHub has a
    tag signed by a trusted entity.

    Receives the commit ID from the pipeline via UserParameters.

    This function must be manually deployed prior to pipeline creation.
    """
    # pylint: disable=unused-argument

    job_id = event["CodePipeline.job"]["id"]
    job_data = event["CodePipeline.job"]["data"]
    job_params = json.loads(
        job_data["actionConfiguration"]["configuration"]["UserParameters"],
        strict=False,
    )

    pipeline_client = boto3.client("codepipeline")

    try:
        # Import whitelisted GPG keys
        tmp_dir = tempfile.TemporaryDirectory()
        os.environ["GNUPGHOME"] = tmp_dir.name
        for _, pub_key in job_params["whitelist"].items():
            tmp = tempfile.NamedTemporaryFile(
                mode="w+", delete=False, dir=tmp_dir.name
            )
            tmp.write(pub_key)
            tmp.close()

            subprocess.run(["gpg", "--import", tmp.name], check=True)

        # Clone exodus-lambda and checkout deploy branch
        subprocess.run(
            [
                "git",
                "clone",
                job_params["repo_url"],
                "-b",
                job_params["repo_branch"],
            ],
            check=True,
        )

        # Retrieve tag for given commit
        os.chdir("exodus-lambda")
        complete_process = subprocess.run(
            ["git", "describe", "--exact-match", job_params["commit_id"]],
            check=True,
            text=True,
            capture_output=True,
        )

        # Verify tag of given commit
        subprocess.run(
            ["git", "verify-tag", complete_process.stdout], check=True
        )

        # Report success to pipeline
        pipeline_client.put_job_success_result(jobId=job_id)
    except subprocess.CalledProcessError as err:
        # Report failure to pipeline
        pipeline_client.put_job_failure_result(
            jobId=job_id,
            failureDetails={"type": "JobFailed", "message": str(err)},
        )
