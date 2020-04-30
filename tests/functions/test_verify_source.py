import json
import subprocess

import mock

from exodus_lambda.functions.verify_source import lambda_handler

TEST_EVENT = {
    "CodePipeline.job": {
        "id": "43b9fac8-610a-4cc3-bc96-648fbc674469",
        "data": {
            "actionConfiguration": {
                "configuration": {
                    "UserParameters": json.dumps(
                        {
                            "repo_url": "https://github.com/owner/repo.git",
                            "repo_branch": "test-branch",
                            "commit_id": "1da3f3bbd48cb160347a38cf0bfdc8e2",
                            "whitelist": {
                                "user1": "9qPWgffbYWEyfTupUvL//R7Dbair/yKY",
                                "user2": "NfkfmElYBQJeTYPfAhsDBQsJCAcCBhUK",
                                "user3": "g8X/Wpso9Oat+d31lKkPDZsuhteUCTUW",
                            },
                        }
                    )
                }
            }
        },
    }
}


@mock.patch("boto3.client")
@mock.patch("subprocess.run")
@mock.patch("os.chdir")
def test_verify_source(mocked_chdir, mocked_run, mocked_client):
    mocked_chdir.return_value = None
    mocked_run.return_value = mock.MagicMock(stdout="v1.1.1")
    mocked_client.return_value = mock.MagicMock()
    mocked_client.put_job_success_result.return_value = mock.MagicMock()

    lambda_handler(event=TEST_EVENT, context=None)

    # Should've imported concatenated public keys
    expected_run = mock.call(["gpg", "--import", mock.ANY], check=True)
    assert mocked_run.call_args_list[0] == expected_run

    # Should've cloned this repo, checking out the deploy branch
    expected_run = mock.call(
        [
            "git",
            "clone",
            "https://github.com/owner/repo.git",
            "-b",
            "test-branch",
        ],
        check=True,
    )
    assert mocked_run.call_args_list[1] == expected_run

    # Should've extracted git tag
    expected_run = mock.call(
        [
            "git",
            "describe",
            "--exact-match",
            "1da3f3bbd48cb160347a38cf0bfdc8e2",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert mocked_run.call_args_list[2] == expected_run

    # Should've verified git tag
    expected_run = mock.call(["git", "verify-tag", "v1.1.1"], check=True)
    assert mocked_run.call_args_list[3] == expected_run

    # Should've reported success to the pipeline
    mocked_client().put_job_success_result.assert_called()


@mock.patch("boto3.client")
@mock.patch("subprocess.run")
@mock.patch("os.chdir")
def test_verify_no_tag(mocked_chdir, mocked_run, mocked_client):
    mocked_chdir.return_value = None
    mocked_run.side_effect = [
        None,
        None,
        subprocess.CalledProcessError(
            cmd=[
                "git",
                "describe",
                "--exact-match",
                "1da3f3bbd48cb160347a38cf0bfdc8e2",
            ],
            returncode=128,
        ),
    ]
    mocked_client.return_value = mock.MagicMock()
    mocked_client.put_job_failure_result.return_value = mock.MagicMock()

    lambda_handler(event=TEST_EVENT, context=None)

    # Should've reported failure to the pipeline
    mocked_client().put_job_failure_result.assert_called()
